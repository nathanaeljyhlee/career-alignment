"""
Output Builder for Candidate-Market Fit Engine.

Formats pipeline results into the 6 PRD sections + strategic decision module:
  Section 1: Candidate Snapshot (profile summary)
  Section 2: Skill Profile (clusters + O*NET grounding)
  Section 3: Win Now Roles (strong + competitive fits)
  Section 4: Invest to Pivot Roles (developmental with viable pivots)
  Section 5: Gap Analysis (per-role gaps + leverage moves)
  Section 6: Strategic Decision (Win Now vs Invest to Pivot recommendation)
"""
from typing import Any

from config import get_tuning


def build_output(
    profile: dict[str, Any] | None,
    motivation: dict[str, Any] | None,
    fit_results: list[dict[str, Any]] | None,
    gap_results: list[dict[str, Any]] | None,
    confidence_results: list[dict[str, Any]] | None,
    matched_roles: list[dict[str, Any]] | None,
    skills_flat: list[dict[str, Any]] | None,
    structural_gap_warning: dict | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    stage_timings: dict[str, float] | None = None,
    cross_role: dict | None = None,
) -> dict[str, Any]:
    """Build the full output structure for the Streamlit UI.

    Returns a dict with keys for each section, plus metadata.
    """
    output_cfg = get_tuning("output") or {}
    max_win_now = output_cfg.get("max_win_now_roles", 3)
    max_pivot = output_cfg.get("max_pivot_roles", 2)

    result = {
        "section_1_snapshot": _build_snapshot(profile, motivation),
        "section_2_skills": _build_skill_profile(skills_flat, profile),
        "section_3_win_now": [],
        "section_4_pivot": [],
        "section_5_gaps": [],
        "section_6_strategic": {},
        "section_7_cross_role": cross_role or {},
        "metadata": {
            "errors": errors or [],
            "warnings": warnings or [],
            "stage_timings": stage_timings or {},
            "structural_gap_warning": structural_gap_warning,
        },
    }

    if not fit_results:
        return result

    # Classify roles into Win Now vs Invest to Pivot
    win_now = []
    pivot = []
    for i, fit in enumerate(fit_results):
        gap = gap_results[i] if gap_results and i < len(gap_results) else None
        conf = confidence_results[i] if confidence_results and i < len(confidence_results) else None
        role = matched_roles[i] if matched_roles and i < len(matched_roles) else None

        entry = {
            "fit": fit,
            "gap": gap,
            "confidence": conf,
            "role": role,
        }

        if fit.get("fit_band") in ("strong", "competitive"):
            win_now.append(entry)
        else:
            # Only include as pivot if viable
            if gap and gap.get("pivot_viable", False):
                pivot.append(entry)

    result["section_3_win_now"] = win_now[:max_win_now]
    result["section_4_pivot"] = pivot[:max_pivot]

    # Section 5: All gap analyses
    result["section_5_gaps"] = gap_results or []

    # Section 6: Strategic recommendation
    result["section_6_strategic"] = _build_strategic_decision(win_now, pivot)

    return result


def _build_snapshot(
    profile: dict[str, Any] | None,
    motivation: dict[str, Any] | None,
) -> dict[str, Any]:
    """Section 1: Candidate Snapshot."""
    if not profile:
        return {"available": False}

    snapshot = {
        "available": True,
        "narrative_summary": profile.get("narrative_summary", ""),
        "narrative_coherence": profile.get("narrative_coherence_band", ""),
        "years_experience": profile.get("years_total_experience", 0),
        "highest_education": profile.get("highest_education", ""),
        "industry_signals": profile.get("industry_signals", []),
        "source_coverage": profile.get("source_coverage", {}),
    }

    if motivation:
        snapshot["primary_driver"] = motivation.get("primary_driver", "")
        snapshot["secondary_driver"] = motivation.get("secondary_driver", "")
        snapshot["why_quality"] = motivation.get("why_quality", "")
        snapshot["motivation_summary"] = motivation.get("summary", "")

    return snapshot


def _build_skill_profile(
    skills: list[dict[str, Any]] | None,
    profile: dict[str, Any] | None,
) -> dict[str, Any]:
    """Section 2: Skill Profile."""
    if not skills:
        return {"available": False, "clusters": [], "total_skills": 0}

    # Separate by match method
    onet_matched = [s for s in skills if s.get("onet_skill_id")]
    unmatched = [s for s in skills if not s.get("onet_skill_id")]

    clusters = profile.get("skill_clusters", []) if profile else []

    return {
        "available": True,
        "clusters": clusters,
        "total_skills": len(skills),
        "onet_matched": len(onet_matched),
        "unmatched": len(unmatched),
        "top_skills": [
            {"name": s.get("canonical_name", ""), "confidence": s.get("confidence", 0),
             "type": s.get("skill_type", "")}
            for s in skills[:15]
        ],
    }


def _format_role_list(entries: list[dict]) -> str:
    """Format a list of role entries as 'Role1 (85%), Role2 (74%)'."""
    parts = []
    for entry in entries:
        fit = entry.get("fit", {})
        name = fit.get("role_name", "Unknown")
        score = fit.get("composite_score", 0)
        parts.append(f"{name} ({score:.0%})")
    return ", ".join(parts)


def _build_strategic_decision(
    win_now: list[dict],
    pivot: list[dict],
) -> dict[str, Any]:
    """Section 6: Strategic Decision Module."""
    if not win_now and not pivot:
        return {
            "recommendation": "insufficient_data",
            "summary": "Not enough role matches to generate a strategic recommendation.",
        }

    # Build role name lists for all paths
    win_now_names = _format_role_list(win_now)
    pivot_names = _format_role_list(pivot)

    if win_now and not pivot:
        best = win_now[0]
        return {
            "recommendation": "win_now",
            "summary": (
                f"Focus your applications on these roles where you can compete now: "
                f"{win_now_names}. "
                f"Your strongest match is {best['fit'].get('role_name', 'Unknown')} "
                f"({best['fit'].get('fit_band', '')}, {best['fit'].get('composite_score', 0):.0%} fit)."
            ),
            "win_now_roles": win_now_names,
            "win_now_count": len(win_now),
            "pivot_count": 0,
        }

    if pivot and not win_now:
        return {
            "recommendation": "invest_to_pivot",
            "summary": (
                "No strong or competitive matches found in current profile. "
                f"Consider these pivot roles: {pivot_names}. "
                "Each requires significant investment to become competitive."
            ),
            "pivot_roles": pivot_names,
            "win_now_count": 0,
            "pivot_count": len(pivot),
        }

    # Both exist
    best_win = win_now[0]
    return {
        "recommendation": "dual_track",
        "summary": (
            f"Apply now to: {win_now_names}. "
            f"Your strongest match is {best_win['fit'].get('role_name', 'Unknown')} "
            f"({best_win['fit'].get('composite_score', 0):.0%} fit). "
            f"Viable pivot role(s): {pivot_names}. "
            "Apply to Win Now roles while investing in gap-closing for pivots."
        ),
        "win_now_roles": win_now_names,
        "pivot_roles": pivot_names,
        "win_now_count": len(win_now),
        "pivot_count": len(pivot),
    }
