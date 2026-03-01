"""
Agent 4: Gap Analyzer (Phi-4 14B)

For each role comparison result, quantifies specific gaps:
- Hard skill gaps (missing required/preferred skills)
- Market signal gaps (missing industry experience, brand signals)
- Narrative coherence gaps (story doesn't support the pivot)

Produces composite gap severity score and actionable leverage moves.
"""
import json
import logging
from typing import Any

import ollama
from pydantic import BaseModel, Field

from config import get_tuning, reasoning_model, reasoning_options

logger = logging.getLogger(__name__)


class GapItem(BaseModel):
    """A single identified gap."""
    gap_type: str = Field(description="hard_skills, market_signals, or narrative_coherence")
    description: str = Field(description="What is missing and why it matters")
    severity: float = Field(description="0-1 how critical this gap is", ge=0.0, le=1.0)
    addressability: str = Field(description="quick_win, semester_project, or long_term")
    leverage_move: str | None = Field(
        default=None,
        description="Specific action to close this gap (if addressable)",
    )
    evidence_source: str = Field(
        default="",
        description="Specific data point proving this gap (overlap data, skills list, or profile text)",
    )


class RoleGapAnalysis(BaseModel):
    """Full gap analysis for a single role."""
    role_id: str
    role_name: str
    gaps: list[GapItem] = Field(default_factory=list)
    composite_severity: float = Field(ge=0.0, le=1.0)
    severity_band: str = Field(description="low, moderate, high, or extreme")
    pivot_viable: bool = Field(description="Whether pivoting to this role is recommended")
    pivot_rationale: str = Field(description="Why pivot is or isn't viable")
    top_leverage_moves: list[str] = Field(
        default_factory=list,
        description="Ranked list of highest-impact actions to improve fit",
    )


GAP_ANALYSIS_PROMPT = """You are an expert career gap analyst for MBA students. You identify specific, actionable gaps between a candidate's current profile and a target role.

TASK: Analyze the gaps between this candidate and the target role.

CRITICAL RULES — READ BEFORE ANALYZING:
1. VERIFY BEFORE CLAIMING A GAP: The DETERMINISTIC SKILL OVERLAP section below lists exactly which required and preferred skills are MISSING. Start with those. Do NOT claim a skill is a gap if it appears in "Matched required" or "Matched preferred".
2. CHECK THE FIT ASSESSMENT: The fit assessment scored this candidate {fit_band_label} ({fit_composite:.0%} composite). Your gap analysis must be consistent with that assessment. A "strong" fit cannot have "extreme" gap severity. A candidate scoring 85%+ fit should have mostly low-to-moderate gaps, not high/extreme ones.
3. GAPS MUST BE SPECIFIC: Each gap must reference a specific role requirement the candidate genuinely lacks. Do not list vague gaps like "lacks technical fluency" when the candidate has technical skills listed.
4. DO NOT HALLUCINATE GAPS: If you cannot find clear evidence that the candidate lacks something, do not invent a gap.
5. EVIDENCE REQUIRED: Every gap MUST include "evidence_source" — the specific data point proving the candidate lacks this. Reference the skill overlap data, the candidate skills list, or a specific absence in the profile text. If you cannot cite evidence, the gap is not real.

GAP TYPES:
1. hard_skills: Missing technical or functional skills from the role's REQUIRED or PREFERRED list that are NOT present in the candidate's skills
2. market_signals: Missing industry experience, relevant company brands, or domain expertise that the role expects
3. narrative_coherence: The career story doesn't naturally lead to this role

GAP SEVERITY (0-1):
- 0.0-0.25 (Low): Minor gap, addressable in weeks with focused effort.
- 0.26-0.50 (Moderate): Real gap requiring a semester of investment.
- 0.51-0.75 (High): Significant barrier requiring sustained effort over 6+ months.
- 0.76-1.0 (Extreme): Fundamental misalignment. Only use this for skills/experience the candidate has zero background in AND that are core requirements for the role.

ADDRESSABILITY:
- "quick_win": Can address in 2-4 weeks (online cert, side project, targeted networking)
- "semester_project": Needs a semester (course, internship, major project)
- "long_term": Needs 1+ years of focused experience

LEVERAGE MOVES: For each gap, suggest the single most impactful action. Requirements:
- Tailor the recommendation to THIS candidate's specific background and context
- Reference the candidate's existing strengths that could accelerate gap-closing
- Be specific about what to do (name a concrete action, not a generic course)
- Different gaps should have DIFFERENT recommendations (no repeating the same suggestion)

PIVOT VIABILITY: If composite severity > {pivot_cutoff}, recommend AGAINST pivoting. Explain why.

Return max {max_gaps} gaps (highest severity first). Only include GENUINE gaps — fewer is better than padding with false ones.

Return ONLY valid JSON:
{{
  "role_id": "string",
  "role_name": "string",
  "gaps": [
    {{
      "gap_type": "hard_skills|market_signals|narrative_coherence",
      "description": "string",
      "severity": 0.0,
      "addressability": "quick_win|semester_project|long_term",
      "leverage_move": "string or null",
      "evidence_source": "SKILL OVERLAP: 'X' in missing_required; not found in candidate skills list"
    }}
  ],
  "composite_severity": 0.0,
  "severity_band": "low|moderate|high|extreme",
  "pivot_viable": true,
  "pivot_rationale": "string",
  "top_leverage_moves": ["move1", "move2", "move3"]
}}

--- CANDIDATE PROFILE ---
{profile_json}

--- CANDIDATE SKILLS (the candidate HAS these — do NOT list any of these as gaps) ---
{skills_json}

--- DETERMINISTIC SKILL OVERLAP (pre-computed — use as the primary source of hard skill gaps) ---
{overlap_section}

IMPORTANT: Your gaps list should START with skills in "Missing required" (they are verified gaps).
You may identify additional gaps (market_signals, narrative_coherence) but do NOT contradict the overlap data.
If a skill is in "Matched required" or "Matched preferred", it is NOT a gap.

--- TARGET ROLE ---
{role_json}

--- FIT ASSESSMENT (your analysis must be consistent with this) ---
{fit_json}
"""


def _format_overlap_for_gap_prompt(skill_overlap: dict | None) -> str:
    """Format skill overlap data for the gap analysis prompt."""
    if not skill_overlap:
        return "No deterministic overlap data available."
    matched_req = skill_overlap.get("matched_required", [])
    missing_req = skill_overlap.get("missing_required", [])
    matched_pref = skill_overlap.get("matched_preferred", [])
    missing_pref = skill_overlap.get("missing_preferred", [])
    lines = [
        f"Matched required: {', '.join(matched_req) if matched_req else 'none'}",
        f"Missing required: {', '.join(missing_req) if missing_req else 'none'}",
        f"Matched preferred: {', '.join(matched_pref) if matched_pref else 'none'}",
        f"Missing preferred: {', '.join(missing_pref) if missing_pref else 'none'}",
        f"Required coverage: {skill_overlap.get('required_coverage', 0):.0%}",
    ]
    return "\n".join(lines)


def analyze_gaps(
    profile: dict[str, Any],
    skills: list[dict[str, Any]],
    role: dict[str, Any],
    fit_result: dict[str, Any],
    skill_overlap: dict | None = None,
) -> RoleGapAnalysis:
    """Run gap analysis for a single role.

    Args:
        profile: CandidateProfile as dict
        skills: Flat list of normalized skills as dicts
        role: Role definition from taxonomy
        fit_result: AggregatedRoleFit as dict (from Agent 3)

    Returns:
        RoleGapAnalysis with scored gaps and leverage moves
    """
    gap_cfg = get_tuning("gap_analysis") or {}
    output_cfg = get_tuning("output") or {}

    severity_bands = gap_cfg.get("severity_bands", {})
    gap_weights = gap_cfg.get("gap_type_weights", {})
    pivot_cutoff = gap_cfg.get("pivot_viability_cutoff", 0.75)
    max_gaps = gap_cfg.get("max_gaps_per_role", 5)
    max_moves = output_cfg.get("max_leverage_moves", 3)

    max_skills = gap_cfg.get("max_skills_for_context", 50)

    # Extract fit context for consistency constraint
    fit_band_label = fit_result.get("fit_band", "unknown")
    fit_composite = fit_result.get("composite_score", 0.0)

    prompt = GAP_ANALYSIS_PROMPT.format(
        pivot_cutoff=pivot_cutoff,
        max_gaps=max_gaps,
        fit_band_label=fit_band_label,
        fit_composite=fit_composite,
        profile_json=json.dumps(profile, indent=2),
        skills_json=json.dumps(skills[:max_skills], indent=2),
        overlap_section=_format_overlap_for_gap_prompt(skill_overlap),
        role_json=json.dumps(role, indent=2),
        fit_json=json.dumps(fit_result, indent=2),
    )

    try:
        response = ollama.chat(
            model=reasoning_model(),
            messages=[{"role": "user", "content": prompt}],
            format=RoleGapAnalysis.model_json_schema(),
            options=reasoning_options({"num_predict": 3072}),
        )
        content = response["message"]["content"]
        analysis = RoleGapAnalysis.model_validate_json(content)

        # Deterministic dedup: remove any gap the LLM listed that is actually matched
        if skill_overlap:
            matched = {s.lower() for s in (
                skill_overlap.get("matched_required", []) +
                skill_overlap.get("matched_preferred", [])
            )}
            analysis.gaps = [
                g for g in analysis.gaps
                if g.description.lower() not in matched
            ]

        # Recompute composite severity using tuning weights
        if analysis.gaps:
            type_scores: dict[str, list[float]] = {}
            for gap in analysis.gaps:
                type_scores.setdefault(gap.gap_type, []).append(gap.severity)

            weighted_sum = 0.0
            total_weight = 0.0
            for gap_type, scores in type_scores.items():
                weight = gap_weights.get(gap_type, 0.33)
                avg_score = sum(scores) / len(scores)
                weighted_sum += avg_score * weight
                total_weight += weight

            if total_weight > 0:
                analysis.composite_severity = round(weighted_sum / total_weight, 3)

        # Apply severity band thresholds
        sev = analysis.composite_severity
        if sev <= severity_bands.get("low", 0.25):
            analysis.severity_band = "low"
        elif sev <= severity_bands.get("moderate", 0.50):
            analysis.severity_band = "moderate"
        elif sev <= severity_bands.get("high", 0.75):
            analysis.severity_band = "high"
        else:
            analysis.severity_band = "extreme"

        # Apply pivot viability cutoff
        analysis.pivot_viable = analysis.composite_severity <= pivot_cutoff

        # Cap leverage moves
        analysis.top_leverage_moves = analysis.top_leverage_moves[:max_moves]

        return analysis

    except Exception as e:
        logger.error("Gap analysis failed for role %s: %s", role.get("role_id"), e)
        raise


def analyze_gaps_batch(
    profile: dict[str, Any],
    skills: list[dict[str, Any]],
    roles: list[dict[str, Any]],
    fit_results: list[dict[str, Any]],
    skill_overlaps: dict[str, dict] | None = None,
) -> list[RoleGapAnalysis]:
    """Run gap analysis for multiple roles."""
    results = []
    for role, fit in zip(roles, fit_results):
        try:
            overlap = (skill_overlaps or {}).get(role.get("role_id", ""))
            result = analyze_gaps(profile, skills, role, fit, skill_overlap=overlap)
            results.append(result)
        except Exception as e:
            logger.error("Gap analysis batch: skipping role %s: %s", role.get("role_id"), e)
    return results
