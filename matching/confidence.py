"""
Composite confidence band computation.

Combines multiple signals to produce a final confidence assessment:
1. Self-consistency agreement (from Agent 3 sampling)
2. Embedding similarity coverage (how well the profile fits the taxonomy)
3. Input completeness (which sources were provided)

Maps to qualitative bands: high, moderate, low.
"""
import logging
from typing import Any

from config import get_tuning

logger = logging.getLogger(__name__)


def compute_confidence_band(
    agreement_ratio: float,
    embedding_similarity: float,
    source_coverage: dict[str, bool],
) -> dict[str, Any]:
    """Compute composite confidence for a role assessment.

    Args:
        agreement_ratio: Fraction of self-consistency paths that agreed (0-1)
        embedding_similarity: Best embedding similarity score for this role (0-1)
        source_coverage: Which input sources were provided (resume, linkedin, coursework)

    Returns:
        {
            "band": "high" | "moderate" | "low",
            "score": float (0-1),
            "factors": {
                "self_consistency": {"value": float, "assessment": str},
                "embedding_coverage": {"value": float, "assessment": str},
                "input_completeness": {"value": float, "assessment": str},
            },
            "warnings": [str],
        }
    """
    confidence_cfg = get_tuning("confidence") or {}
    high_agreement = confidence_cfg.get("high_agreement", 0.80)
    moderate_agreement = confidence_cfg.get("moderate_agreement", 0.60)
    structural_gap = confidence_cfg.get("structural_gap_threshold", 0.35)

    warnings = []

    # Factor 1: Self-consistency
    if agreement_ratio >= high_agreement:
        sc_assessment = "strong"
        sc_score = 1.0
    elif agreement_ratio >= moderate_agreement:
        sc_assessment = "moderate"
        sc_score = 0.6
    else:
        sc_assessment = "weak"
        sc_score = 0.3
        warnings.append(
            f"Low self-consistency ({agreement_ratio:.0%} agreement). "
            "Multiple reasoning paths produced different assessments."
        )

    emb_coverage_threshold = confidence_cfg.get("embedding_coverage_threshold", 0.60)
    input_good = confidence_cfg.get("input_completeness_good", 0.66)
    input_partial = confidence_cfg.get("input_completeness_partial", 0.33)
    weights = confidence_cfg.get("weights", {})
    w_sc = weights.get("self_consistency", 0.50)
    w_emb = weights.get("embedding_coverage", 0.30)
    w_inp = weights.get("input_completeness", 0.20)
    band_thresholds = confidence_cfg.get("band_thresholds", {})
    band_high = band_thresholds.get("high", 0.75)
    band_moderate = band_thresholds.get("moderate", 0.50)

    # Factor 2: Embedding coverage
    if embedding_similarity >= emb_coverage_threshold:
        emb_assessment = "strong"
        emb_score = 1.0
    elif embedding_similarity >= structural_gap:
        emb_assessment = "moderate"
        emb_score = 0.6
    else:
        emb_assessment = "weak"
        emb_score = 0.2
        warnings.append(
            f"Low embedding match ({embedding_similarity:.2f}). "
            "This profile may not fit standard role categories well."
        )

    # Factor 3: Input completeness
    provided = sum(1 for v in source_coverage.values() if v)
    total = len(source_coverage) if source_coverage else 3
    completeness = provided / total
    if completeness >= input_good:
        input_assessment = "good"
        input_score = 1.0
    elif completeness >= input_partial:
        input_assessment = "partial"
        input_score = 0.6
        warnings.append("Limited input sources. More data would improve accuracy.")
    else:
        input_assessment = "minimal"
        input_score = 0.3
        warnings.append("Very limited input. Results are based on incomplete data.")

    # Composite: weighted average (self-consistency matters most)
    composite = sc_score * w_sc + emb_score * w_emb + input_score * w_inp

    if composite >= band_high:
        band = "high"
    elif composite >= band_moderate:
        band = "moderate"
    else:
        band = "low"

    return {
        "band": band,
        "score": round(composite, 3),
        "factors": {
            "self_consistency": {"value": agreement_ratio, "assessment": sc_assessment},
            "embedding_coverage": {"value": embedding_similarity, "assessment": emb_assessment},
            "input_completeness": {"value": completeness, "assessment": input_assessment},
        },
        "warnings": warnings,
    }


def assess_structural_gap(best_similarity: float) -> dict[str, Any] | None:
    """Check if the profile doesn't fit any role in the taxonomy.

    Returns a warning dict if below threshold, None otherwise.
    """
    threshold = get_tuning("confidence", "structural_gap_threshold") or 0.35
    if best_similarity < threshold:
        return {
            "warning": "structural_gap",
            "message": (
                f"Your profile's best role match ({best_similarity:.2f}) is below "
                f"the structural gap threshold ({threshold}). This may mean your "
                "background doesn't map well to standard MBA role categories. "
                "Consider whether your target roles are captured in the taxonomy, "
                "or whether your profile represents a novel combination."
            ),
            "best_similarity": best_similarity,
            "threshold": threshold,
        }
    return None
