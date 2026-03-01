"""
Agent 1: Profile Synthesizer (Qwen 7B)

Takes structured skill data + raw resume/LinkedIn sections and produces
a unified candidate profile with:
- Skill clusters (grouped by domain)
- Industry/domain signals
- Narrative coherence assessment
- Source attribution (which evidence came from where)
"""
import json
import logging
from typing import Any

import ollama
from pydantic import BaseModel, Field

from config import OLLAMA_TIMEOUT, get_tuning, extraction_model, extraction_options

logger = logging.getLogger(__name__)


# --- Output schemas ---

class SkillCluster(BaseModel):
    """A group of related skills with evidence."""
    cluster_name: str = Field(description="Domain label, e.g. 'Product Management', 'Data & Analytics'")
    skills: list[str] = Field(description="Canonical skill names in this cluster")
    strength: str = Field(description="strong, moderate, or emerging")
    evidence_summary: str = Field(description="Brief summary of supporting evidence")


class IndustrySignal(BaseModel):
    """An industry or domain the candidate has experience in."""
    industry: str
    years_approximate: float = Field(description="Estimated years of experience", ge=0)
    recency: str = Field(description="current, recent (1-3 years), or historical (3+ years)")
    evidence: str


class CandidateProfile(BaseModel):
    """The synthesized candidate profile output from Agent 1."""
    skill_clusters: list[SkillCluster] = Field(description="Grouped skill clusters — must contain at least one entry")
    industry_signals: list[IndustrySignal] = Field(description="Industry/domain signals from experience — must contain at least one entry")
    narrative_coherence_score: float = Field(
        description="0-1 score: how well the career story holds together", ge=0.0, le=1.0
    )
    narrative_coherence_band: str = Field(description="strong, moderate, or fragmented")
    narrative_summary: str = Field(description="2-3 sentence career narrative synthesis")
    years_total_experience: float = Field(ge=0)
    highest_education: str
    source_coverage: dict[str, bool] = Field(
        default_factory=dict,
        description="Which sources were available: resume, linkedin, coursework",
    )


SYNTHESIS_PROMPT = """You are a career profile synthesizer for MBA students. You receive structured skill data and resume/LinkedIn sections, and produce a unified candidate profile.

INSTRUCTIONS:
1. Group the extracted skills into meaningful clusters (e.g., "Product Management", "Data & Analytics", "Leadership", "Technical"). Max {max_clusters} clusters, max {max_per_cluster} skills each.
2. Identify industry/domain signals from the experience sections.
3. Assess narrative coherence: does the career story make sense? Is there a clear thread, or is it fragmented across unrelated domains?
4. Estimate total years of experience and highest education level.

COHERENCE SCORING:
- 0.75-1.0 (Strong): Clear career progression, consistent theme, logical MBA pivot
- 0.45-0.74 (Moderate): Some career pivots but explainable, reasonable connections between roles
- 0.00-0.44 (Fragmented): Unrelated roles, no clear thread, hard to explain

SOURCE WEIGHTS for conflicting signals:
- Resume: {w_resume} (primary — hard evidence)
- LinkedIn: {w_linkedin} (supplementary — self-reported)
- Coursework: {w_coursework} (reinforcing — academic signal)

--- EXTRACTED SKILLS ---
{skills_json}

--- RESUME SECTIONS ---
{resume_text}

--- LINKEDIN SECTIONS ---
{linkedin_text}

---
Analyze the above and produce a unified candidate profile. You MUST include all of these fields:
- skill_clusters: list of skill groups (cluster_name, skills list, strength, evidence_summary)
- industry_signals: list of industries (industry, years_approximate, recency, evidence)
- narrative_coherence_score: float 0.0-1.0
- narrative_coherence_band: "strong", "moderate", or "fragmented"
- narrative_summary: 2-3 sentence career narrative
- years_total_experience: float (total years across all roles)
- highest_education: string (e.g., "MBA", "Bachelor's in Computer Science")
- source_coverage: dict with keys "resume", "linkedin", "coursework" (true/false)
"""


def synthesize_profile(
    skills_data: list[dict[str, Any]],
    resume_sections: dict[str, str] | None = None,
    linkedin_sections: dict[str, str] | None = None,
) -> CandidateProfile:
    """Run profile synthesis agent.

    Args:
        skills_data: Flat list of normalized skills (from skills.get_flat_skills)
        resume_sections: Section dict from parsers.parse_resume
        linkedin_sections: Section dict from parsers.parse_linkedin

    Returns:
        CandidateProfile with structured clusters and assessments
    """
    # Load tuning params
    synthesis_cfg = get_tuning("profile_synthesis") or {}
    source_weights = synthesis_cfg.get("source_weights", {})
    max_per_cluster = synthesis_cfg.get("max_skills_per_cluster", 8)
    coherence_bands = synthesis_cfg.get("narrative_coherence_bands", {})

    # Format skills for prompt
    skills_json = json.dumps(
        [{"name": s.get("canonical_name", s.get("skill_name", "")),
          "type": s.get("skill_type", ""),
          "confidence": s.get("confidence", 0)}
         for s in skills_data],
        indent=2,
    )

    # Format sections
    resume_text = ""
    if resume_sections:
        resume_text = "\n\n".join(
            f"[{name.upper()}]\n{text}" for name, text in resume_sections.items() if text
        )

    linkedin_text = ""
    if linkedin_sections:
        linkedin_text = "\n\n".join(
            f"[{name.upper()}]\n{text}" for name, text in linkedin_sections.items() if text
        )

    if not resume_text and not linkedin_text:
        linkedin_text = "(No LinkedIn data provided)"
    if not resume_text:
        resume_text = "(No resume data provided)"

    prompt = SYNTHESIS_PROMPT.format(
        max_clusters=8,
        max_per_cluster=max_per_cluster,
        w_resume=source_weights.get("resume", 0.50),
        w_linkedin=source_weights.get("linkedin", 0.35),
        w_coursework=source_weights.get("coursework", 0.15),
        skills_json=skills_json,
        resume_text=resume_text,
        linkedin_text=linkedin_text,
    )

    try:
        response = ollama.chat(
            model=extraction_model(),
            messages=[{"role": "user", "content": prompt}],
            format=CandidateProfile.model_json_schema(),
            options=extraction_options({"num_predict": 4096}),
        )
        content = response["message"]["content"]
        profile = CandidateProfile.model_validate_json(content)

        # Apply coherence band thresholds from tuning
        strong_threshold = coherence_bands.get("strong", 0.75)
        moderate_threshold = coherence_bands.get("moderate", 0.45)
        score = profile.narrative_coherence_score
        if score >= strong_threshold:
            profile.narrative_coherence_band = "strong"
        elif score >= moderate_threshold:
            profile.narrative_coherence_band = "moderate"
        else:
            profile.narrative_coherence_band = "fragmented"

        return profile

    except Exception as e:
        logger.error("Profile synthesis failed: %s", e)
        raise
