"""
Agent 3: Role Comparator (Phi-4 14B)

Compares candidate profile against pre-filtered roles (top-K from embedding match).
Uses self-consistency sampling: runs N independent reasoning paths and takes majority vote.

Outputs: fit classification, evidence, confidence bands per role.
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import ollama
from pydantic import BaseModel, Field

from config import get_tuning, reasoning_model, reasoning_options

logger = logging.getLogger(__name__)


class EvidenceItem(BaseModel):
    """A single evidence item within a fit dimension."""
    claim: str = Field(description="The specific claim being made")
    source: str = Field(description="Reference to specific resume text, skill list, or overlap data")
    score_impact: str = Field(description="e.g. '+0.15' or '-0.10'")
    direction: str = Field(description="supporting or gap")


class RoleFitEvidence(BaseModel):
    """Evidence for a specific fit dimension."""
    dimension: str = Field(description="structural_fit or motivation_alignment")
    score: float = Field(ge=0.0, le=1.0)
    evidence_chain: list[EvidenceItem] = Field(default_factory=list)


class RoleFitResult(BaseModel):
    """Fit assessment for a single role from a single reasoning path."""
    role_id: str
    role_name: str
    structural_fit_score: float = Field(ge=0.0, le=1.0)
    motivation_alignment_score: float = Field(ge=0.0, le=1.0)
    composite_score: float = Field(ge=0.0, le=1.0)
    fit_band: str = Field(description="strong, competitive, or developmental")
    evidence: list[RoleFitEvidence] = Field(default_factory=list)
    reasoning: str = Field(description="2-3 sentence explanation of the fit assessment")


class AggregatedRoleFit(BaseModel):
    """Aggregated fit result after self-consistency voting."""
    role_id: str
    role_name: str
    composite_score: float = Field(ge=0.0, le=1.0)
    fit_band: str
    confidence_band: str = Field(description="high, moderate, or low")
    agreement_ratio: float = Field(description="Fraction of paths that agree on fit_band", ge=0.0, le=1.0)
    structural_fit_score: float = Field(ge=0.0, le=1.0)
    motivation_alignment_score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence: list[RoleFitEvidence] = Field(default_factory=list)


COMPARISON_PROMPT = """You are an expert career advisor assessing candidate-role fit for MBA students.

TASK: Assess how well this candidate fits the target role based on structural qualifications and motivational alignment.

SCORING:
- structural_fit_score (0-1): How well the candidate's skills, experience, and background match the role's requirements. Consider: required skills coverage, industry relevance, experience level, barrier conditions.
- motivation_alignment_score (0-1): How well the candidate's motivational profile matches what the role demands. Consider: impact orientation, autonomy preference, innovation draw, stability preference.
- composite_score: structural_fit * {w_structural} + motivation_alignment * {w_motivation}

FIT BANDS:
- "strong" (>= {t_strong}): Ready to compete now. No major gaps.
- "competitive" (>= {t_competitive}): Real shot with focused effort. Some gaps but addressable.
- "developmental" (< {t_competitive}): Significant gaps. Would require substantial pivot investment.

--- DETERMINISTIC SKILL OVERLAP (pre-computed, use as scoring anchor) ---
{overlap_section}

IMPORTANT: Your structural_fit_score should be anchored to the overlap score above.
If overlap is 0.85, structural_fit should be in the 0.75-0.95 range (LLM adjusts for quality/depth, but cannot wildly deviate from the deterministic base).
If overlap is 0.30, structural_fit should be in the 0.20-0.45 range.
The overlap score is a floor/ceiling anchor, not a replacement for your judgment.

EVIDENCE RULES:
- Every claim MUST have a "source" that references specific text from the candidate profile, skills list, or deterministic overlap data
- Every claim MUST have a "score_impact" showing how much it moves the score (e.g. "+0.15" or "-0.10")
- Sum of all score_impacts should approximately equal the dimension score
- If you cannot cite a specific source for a claim, do not include it

{optimization_priorities_section}Be specific. Reference actual skills, experiences, and motivation dimensions. Don't inflate scores.

Return ONLY valid JSON:
{{
  "role_id": "string",
  "role_name": "string",
  "structural_fit_score": 0.0,
  "motivation_alignment_score": 0.0,
  "composite_score": 0.0,
  "fit_band": "strong|competitive|developmental",
  "evidence": [
    {{
      "dimension": "structural_fit",
      "score": 0.0,
      "evidence_chain": [
        {{
          "claim": "string",
          "source": "RESUME: specific quote or SKILL OVERLAP: matched_required contains X",
          "score_impact": "+0.15",
          "direction": "supporting"
        }},
        {{
          "claim": "string",
          "source": "SKILL OVERLAP: missing_required contains X",
          "score_impact": "-0.10",
          "direction": "gap"
        }}
      ]
    }},
    {{
      "dimension": "motivation_alignment",
      "score": 0.0,
      "evidence_chain": [
        {{
          "claim": "string",
          "source": "MOTIVATION: primary_driver or specific dimension",
          "score_impact": "+0.10",
          "direction": "supporting"
        }}
      ]
    }}
  ],
  "reasoning": "string"
}}

--- CANDIDATE PROFILE ---
{profile_json}

--- CANDIDATE MOTIVATION ---
{motivation_json}

--- TARGET ROLE ---
{role_json}
"""


def _format_overlap_section(skill_overlap: dict | None) -> str:
    """Format skill overlap data for inclusion in the prompt."""
    if not skill_overlap:
        return "No deterministic overlap data available."
    req_cov = skill_overlap.get("required_coverage", 0)
    pref_cov = skill_overlap.get("preferred_coverage", 0)
    overlap_score = skill_overlap.get("overlap_score", 0)
    matched_req = skill_overlap.get("matched_required", [])
    missing_req = skill_overlap.get("missing_required", [])
    matched_pref = skill_overlap.get("matched_preferred", [])
    missing_pref = skill_overlap.get("missing_preferred", [])

    lines = [
        f"Required skills coverage: {req_cov:.0%} ({len(matched_req)}/{len(matched_req) + len(missing_req)})",
        f"Matched required: {', '.join(matched_req) if matched_req else 'none'}",
        f"Missing required: {', '.join(missing_req) if missing_req else 'none'}",
        f"Preferred skills coverage: {pref_cov:.0%} ({len(matched_pref)}/{len(matched_pref) + len(missing_pref)})",
        f"Missing preferred: {', '.join(missing_pref) if missing_pref else 'none'}",
        f"Overall overlap score: {overlap_score:.2f}",
    ]
    return "\n".join(lines)


def _single_comparison(
    profile_json: str,
    motivation_json: str,
    role_json: str,
    weights: dict[str, float],
    thresholds: dict[str, float],
    temperature: float,
    skill_overlap: dict | None = None,
    optimization_priorities: list[str] | None = None,
    sample_profile: dict[str, Any] | None = None,
) -> RoleFitResult | None:
    """Run a single reasoning path for role comparison."""
    # Build optional optimization priorities block (from Tally intake)
    if optimization_priorities:
        priorities_str = ", ".join(optimization_priorities)
        optimization_priorities_section = (
            f"--- CANDIDATE'S STATED PRIORITIES ---\n"
            f"They are optimizing for: {priorities_str}\n"
            f"Factor these into motivation_alignment_score: roles that deliver on their "
            f"priorities should score higher on motivation alignment.\n\n"
        )
    else:
        optimization_priorities_section = ""

    prompt = COMPARISON_PROMPT.format(
        w_structural=weights.get("structural_fit", 0.65),
        w_motivation=weights.get("motivation_alignment", 0.35),
        t_strong=thresholds.get("strong", 0.70),
        t_competitive=thresholds.get("competitive", 0.45),
        overlap_section=_format_overlap_section(skill_overlap),
        optimization_priorities_section=optimization_priorities_section,
        profile_json=profile_json,
        motivation_json=motivation_json,
        role_json=role_json,
    )

    prompt_token_estimate = max(1, len(prompt) // 4)
    total_start = time.perf_counter()

    try:
        llm_start = time.perf_counter()
        response = ollama.chat(
            model=reasoning_model(),
            messages=[{"role": "user", "content": prompt}],
            format=RoleFitResult.model_json_schema(),
            options=reasoning_options({"temperature": temperature, "num_predict": 2048}),
        )
        llm_elapsed = time.perf_counter() - llm_start
        content = response["message"]["content"]
        output_token_estimate = max(1, len(content) // 4)
        result = RoleFitResult.model_validate_json(content)

        # Enforce composite score calculation from tuning weights
        result.composite_score = (
            result.structural_fit_score * weights.get("structural_fit", 0.65)
            + result.motivation_alignment_score * weights.get("motivation_alignment", 0.35)
        )

        # Enforce fit band from tuning thresholds
        if result.composite_score >= thresholds.get("strong", 0.70):
            result.fit_band = "strong"
        elif result.composite_score >= thresholds.get("competitive", 0.45):
            result.fit_band = "competitive"
        else:
            result.fit_band = "developmental"

        if sample_profile is not None:
            total_elapsed = time.perf_counter() - total_start
            sample_profile.update(
                {
                    "status": "ok",
                    "llm_time_s": round(llm_elapsed, 3),
                    "total_time_s": round(total_elapsed, 3),
                    "python_time_s": round(max(0.0, total_elapsed - llm_elapsed), 3),
                    "tokens_in": response.get("prompt_eval_count") or prompt_token_estimate,
                    "tokens_out": response.get("eval_count") or output_token_estimate,
                    "tokens_in_estimate": prompt_token_estimate,
                    "tokens_out_estimate": output_token_estimate,
                }
            )

        return result

    except Exception as e:
        logger.error("Single comparison failed: %s", e)
        if sample_profile is not None:
            sample_profile.update(
                {
                    "status": "error",
                    "error": str(e),
                    "total_time_s": round(time.perf_counter() - total_start, 3),
                    "tokens_in_estimate": prompt_token_estimate,
                }
            )
        return None


def compare_role(
    profile: dict[str, Any],
    motivation: dict[str, Any],
    role: dict[str, Any],
    mba_year: str = "1y_internship",
    skill_overlap: dict | None = None,
    optimization_priorities: list[str] | None = None,
    profiler: dict[str, Any] | None = None,
) -> AggregatedRoleFit:
    """Compare candidate against a single role with self-consistency sampling.

    Args:
        profile: CandidateProfile as dict
        motivation: MotivationProfile as dict
        role: Role definition from taxonomy
        mba_year: "1y_internship" or "2y_fulltime" (determines weight balance)

    Returns:
        AggregatedRoleFit with confidence band from self-consistency
    """
    matching_cfg = get_tuning("role_matching") or {}
    confidence_cfg = get_tuning("confidence") or {}

    n_samples = matching_cfg.get("self_consistency_samples", 3)
    sc_temperature = matching_cfg.get("self_consistency_temperature", 0.7)
    fit_weights = matching_cfg.get("fit_weights", {}).get(mba_year, {})
    fit_bands = matching_cfg.get("fit_bands", {})

    profile_json = json.dumps(profile, indent=2)
    motivation_json = json.dumps(motivation, indent=2)
    role_json = json.dumps(role, indent=2)

    role_start = time.perf_counter()

    # Run N independent reasoning paths
    results: list[RoleFitResult] = []
    sample_profiles: list[dict[str, Any]] = []
    for i in range(n_samples):
        sample_profile: dict[str, Any] = {"sample_index": i, "temperature": sc_temperature}
        result = _single_comparison(
            profile_json, motivation_json, role_json,
            fit_weights, fit_bands, sc_temperature,
            skill_overlap=skill_overlap,
            optimization_priorities=optimization_priorities,
            sample_profile=sample_profile,
        )
        sample_profiles.append(sample_profile)
        if result:
            results.append(result)

    if not results:
        raise RuntimeError(f"All {n_samples} comparison paths failed for role {role.get('role_id', '?')}")

    # Aggregate via majority vote on fit_band
    band_votes: dict[str, int] = {}
    for r in results:
        band_votes[r.fit_band] = band_votes.get(r.fit_band, 0) + 1
    majority_band = max(band_votes, key=band_votes.get)
    agreement_ratio = band_votes[majority_band] / len(results)

    # Average scores across paths
    avg_structural = sum(r.structural_fit_score for r in results) / len(results)
    avg_motivation = sum(r.motivation_alignment_score for r in results) / len(results)
    avg_composite = sum(r.composite_score for r in results) / len(results)

    # Confidence band from agreement ratio
    high_threshold = confidence_cfg.get("high_agreement", 0.80)
    moderate_threshold = confidence_cfg.get("moderate_agreement", 0.60)
    if agreement_ratio >= high_threshold:
        confidence_band = "high"
    elif agreement_ratio >= moderate_threshold:
        confidence_band = "moderate"
    else:
        confidence_band = "low"

    # Use the result closest to the average composite as the representative
    representative = min(results, key=lambda r: abs(r.composite_score - avg_composite))

    aggregate = AggregatedRoleFit(
        role_id=role.get("role_id", ""),
        role_name=role.get("role_name", ""),
        composite_score=round(avg_composite, 3),
        fit_band=majority_band,
        confidence_band=confidence_band,
        agreement_ratio=round(agreement_ratio, 2),
        structural_fit_score=round(avg_structural, 3),
        motivation_alignment_score=round(avg_motivation, 3),
        reasoning=representative.reasoning,
        evidence=representative.evidence,
    )

    if profiler is not None:
        llm_time = sum(s.get("llm_time_s", 0.0) for s in sample_profiles if s.get("status") == "ok")
        sample_total_time = sum(s.get("total_time_s", 0.0) for s in sample_profiles)
        profiler.update({
            "status": "ok",
            "role_id": role.get("role_id", ""),
            "role_name": role.get("role_name", ""),
            "n_samples": n_samples,
            "successful_samples": len(results),
            "agreement_ratio": round(agreement_ratio, 3),
            "fit_band": majority_band,
            "composite_score": round(avg_composite, 3),
            "total_time_s": round(time.perf_counter() - role_start, 3),
            "sample_time_s": round(sample_total_time, 3),
            "llm_time_s": round(llm_time, 3),
            "python_time_s": round(max(0.0, sample_total_time - llm_time), 3),
            "tokens_in": sum(s.get("tokens_in", 0) for s in sample_profiles if s.get("status") == "ok"),
            "tokens_out": sum(s.get("tokens_out", 0) for s in sample_profiles if s.get("status") == "ok"),
            "samples": sample_profiles,
        })

    return aggregate


def compare_roles(
    profile: dict[str, Any],
    motivation: dict[str, Any],
    roles: list[dict[str, Any]],
    mba_year: str = "1y_internship",
    skill_overlaps: dict[str, dict] | None = None,
    optimization_priorities: list[str] | None = None,
    agent3_profile: dict[str, Any] | None = None,
) -> list[AggregatedRoleFit]:
    """Compare candidate against multiple roles in parallel. Returns sorted by composite score."""
    matching_cfg = get_tuning("role_matching") or {}
    max_workers = matching_cfg.get("parallel_workers", 3)

    results: list[AggregatedRoleFit] = []
    role_profiles: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_role: dict[Any, dict[str, Any]] = {}
        future_to_profile: dict[Any, dict[str, Any]] = {}
        for role in roles:
            profiler: dict[str, Any] = {}
            future = executor.submit(
                compare_role, profile, motivation, role, mba_year,
                (skill_overlaps or {}).get(role.get("role_id", "")),
                optimization_priorities,
                profiler,
            )
            future_to_role[future] = role
            future_to_profile[future] = profiler

        for future in as_completed(future_to_role):
            role = future_to_role[future]
            profiler = future_to_profile[future]
            try:
                result = future.result()
                results.append(result)
                role_profiles.append(profiler)
            except Exception as e:
                profiler.update({
                    "status": "error",
                    "role_id": role.get("role_id", ""),
                    "role_name": role.get("role_name", ""),
                    "error": str(e),
                })
                role_profiles.append(profiler)
                logger.error("Failed to compare role %s: %s", role.get("role_id"), e)

    if agent3_profile is not None:
        role_profiles.sort(key=lambda r: r.get("total_time_s", 0.0), reverse=True)
        total_time = sum(r.get("total_time_s", 0.0) for r in role_profiles)
        total_llm = sum(r.get("llm_time_s", 0.0) for r in role_profiles)
        total_python = sum(r.get("python_time_s", 0.0) for r in role_profiles)
        agent3_profile.update({
            "num_roles": len(roles),
            "parallel_workers": max_workers,
            "total_agent3_time_s": round(total_time, 3),
            "inference_time_est_s": round(total_llm, 3),
            "python_time_est_s": round(total_python, 3),
            "estimated_parallel_wall_clock_s": round(max((r.get("total_time_s", 0.0) for r in role_profiles), default=0.0), 3),
            "tokens_in_total": sum(r.get("tokens_in", 0) for r in role_profiles),
            "tokens_out_total": sum(r.get("tokens_out", 0) for r in role_profiles),
            "time_per_role": role_profiles,
        })

    results.sort(key=lambda r: r.composite_score, reverse=True)
    return results
