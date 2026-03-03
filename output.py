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
from datetime import date, timedelta
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
    tally_context: dict | None = None,
) -> dict[str, Any]:
    """Build the full output structure for the Streamlit UI.

    Returns a dict with keys for each section, plus metadata.
    """
    output_cfg = get_tuning("output") or {}
    max_win_now = output_cfg.get("max_win_now_roles", 3)
    max_pivot = output_cfg.get("max_pivot_roles", 2)

    result = {
        "section_1_snapshot": _build_snapshot(profile, motivation, tally_context),
        "section_2_skills": _build_skill_profile(skills_flat, profile),
        "section_3_win_now": [],
        "section_4_pivot": [],
        "section_5_gaps": [],
        "section_6_strategic": {},
        "section_7_cross_role": cross_role or {},
        "section_8_decision_sprint": {},
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

    # Section 8: Decision Sprint card
    result["section_8_decision_sprint"] = build_decision_sprint(result)

    return result


def _build_snapshot(
    profile: dict[str, Any] | None,
    motivation: dict[str, Any] | None,
    tally_context: dict | None = None,
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

    # Tally intake metadata (CMF-005) — present when submission came via form
    if tally_context:
        snapshot["tally_intake"] = {
            "name": tally_context.get("name", ""),
            "email": tally_context.get("email", ""),
            "stated_target_role": tally_context.get("target_role_text", ""),
            "stated_industry": tally_context.get("target_industry", ""),
            "geography": tally_context.get("geography", ""),
            "optimization_priorities": tally_context.get("optimization_priorities", []),
            "self_assessment_score": tally_context.get("self_assessment_score"),
            "self_assessment_reason": tally_context.get("self_assessment_reason", ""),
            "desired_output": tally_context.get("desired_output", []),
        }

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


def build_decision_sprint(result_bundle: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic Decision Sprint card from computed pipeline outputs only."""
    roles = (result_bundle.get("section_3_win_now", []) or []) + (result_bundle.get("section_4_pivot", []) or [])
    if not roles:
        return {}

    cfg = get_tuning("decision_sprint") or {}
    fit_w = cfg.get("fit_weight", 0.45)
    conf_w = cfg.get("confidence_weight", 0.30)
    effort_w = cfg.get("effort_weight", 0.25)
    checkpoint_days = cfg.get("checkpoint_days", 28)

    effort_values = [
        (r.get("role") or {}).get("effort_to_fit")
        for r in roles if isinstance((r.get("role") or {}).get("effort_to_fit"), (int, float))
    ]
    effort_min = min(effort_values) if effort_values else 0.0
    effort_max = max(effort_values) if effort_values else 1.0

    scored = []
    for idx, entry in enumerate(roles):
        fit = entry.get("fit") or {}
        conf = entry.get("confidence") or {}
        role = entry.get("role") or {}

        fit_score = float(fit.get("composite_score", 0.0))
        conf_score = float(conf.get("composite_score", 0.0))
        effort = role.get("effort_to_fit")
        if isinstance(effort, (int, float)) and effort_max > effort_min:
            effort_norm = (float(effort) - effort_min) / (effort_max - effort_min)
        else:
            effort_norm = 0.5

        decision_score = fit_w * fit_score + conf_w * conf_score + effort_w * (1 - effort_norm)
        scored.append((decision_score, idx, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    top_idx = 0
    snapshot = result_bundle.get("section_1_snapshot", {}) or {}
    # CMF P0: read optimization priorities from tally_intake path first
    # with backward-compatible fallback to legacy top-level location.
    top_constraints = {
        c for c in (
            ((snapshot.get("tally_intake") or {}).get("optimization_priorities", []))
            or snapshot.get("optimization_priorities", [])
            or []
        )
        if isinstance(c, str)
    }
    for i, (_, _, entry) in enumerate(scored):
        fit = entry.get("fit") or {}
        role = entry.get("role") or {}
        motivation = role.get("motivation_fit") or {}
        role_constraints = {c for c in motivation.get("constraints", []) if isinstance(c, str) and c}
        if top_constraints and role_constraints and role_constraints.isdisjoint(top_constraints):
            if i + 1 < len(scored):
                top_idx = i + 1
            break
        top_idx = i
        break

    _, _, target = scored[top_idx]
    target_fit = target.get("fit") or {}
    target_role = target.get("role") or {}
    conf_band = (target.get("confidence") or {}).get("confidence_band", "moderate").title()

    low_conf = conf_band.lower() == "low"
    action_verb = "Explore" if low_conf else "Commit"

    role_name = target_fit.get("role_name", "Target Role")
    role_cat = (target_role.get("category") or "general").lower()

    shared_gaps = result_bundle.get("section_7_cross_role", {}).get("shared_gaps", []) or []
    gap_candidates = []
    for gap in shared_gaps:
        skill = gap.get("skill", "")
        if not skill:
            continue
        gap_candidates.append({
            "skill": skill,
            "gap_severity": float(gap.get("avg_severity", 0.0)),
            "cross_role_frequency": float(gap.get("leverage_multiplier", 1.0)),
            "leverage_weight": 1.0 + 0.2 * float(gap.get("leverage_multiplier", 1.0) - 1),
            "roles_unlocked": gap.get("roles_affected", []),
        })

    gap_candidates.sort(
        key=lambda g: g["gap_severity"] * g["cross_role_frequency"] * g["leverage_weight"],
        reverse=True,
    )
    top2 = gap_candidates[:2]

    loop_templates = {
        "product": ("Build one product teardown or feature spec tied to user pain.", "Reach out to 2 PM/CS contacts for role-calibrated feedback.", "Submit 3 targeted applications and complete 1 interview prep drill."),
        "finance": ("Create one investment memo or model artifact each week.", "Do 2 informational calls with operators/investors in target vertical.", "Apply to 3 roles and rehearse 1 technical case/interview block."),
        "healthcare": ("Publish one process-improvement or digital-health analysis artifact.", "Connect with 2 healthcare operators/product leaders per week.", "Apply to 2-3 roles and prep one domain-specific story set."),
        "technology": ("Ship one mini project/case artifact demonstrating execution.", "Run 2 networking conversations with target-team practitioners.", "Apply to 3 roles and rehearse 1 behavioral + 1 case set."),
        "general": ("Produce one tangible artifact that proves role-relevant capability.", "Have 2 focused conversations with people in your target role.", "Apply to 3 curated roles and run 1 structured prep session."),
    }
    project_block, market_block, pipeline_block = loop_templates.get(role_cat, loop_templates["general"])

    go_criteria = [
        "At least 2 positive market signals (referrals, recruiter screens, or strong networking pulls).",
        "Completion of 4 weekly artifacts aligned to target-role skill gaps.",
    ]
    pivot_criteria = [
        "No interview progression after 4 weeks despite consistent execution.",
        "Repeated feedback indicates a single high-severity gap not closing fast enough.",
    ]

    return {
        "role_bet": {
            "target_role": role_name,
            "decision_mode": "explore" if low_conf else "commit",
            "rationale": f"{action_verb} {role_name} for the next 90 days because it balances current fit, confidence, and effort-to-fit better than alternatives.",
            "confidence_band": conf_band,
        },
        "skill_closures": top2,
        "weekly_execution_loop": {
            "project_block": project_block,
            "market_block": market_block,
            "pipeline_block": pipeline_block,
        },
        "go_pivot_checkpoint": {
            "checkpoint_date": (date.today() + timedelta(days=checkpoint_days)).isoformat(),
            "go_criteria": go_criteria,
            "pivot_criteria": pivot_criteria,
        },
        "copy_text": _render_decision_sprint_text(role_name, conf_band, low_conf, top2, project_block, market_block, pipeline_block, checkpoint_days),
    }


def _render_decision_sprint_text(role_name: str, conf_band: str, low_conf: bool, top2: list[dict[str, Any]],
                                 project_block: str, market_block: str, pipeline_block: str, checkpoint_days: int) -> str:
    mode = "Explore" if low_conf else "Commit"
    lines = [
        f"Decision Sprint ({checkpoint_days}-Day Checkpoint)",
        f"1) 90-day role bet: {mode} on {role_name} ({conf_band} confidence).",
        "2) Top-2 skill closures:",
    ]
    if top2:
        for i, skill in enumerate(top2, 1):
            unlocked = ", ".join(skill.get("roles_unlocked", [])[:3]) or "adjacent target roles"
            lines.append(f"   {i}. {skill.get('skill', 'N/A')} -> unlocks {unlocked}")
    else:
        lines.append("   1. No high-severity shared gaps detected; continue depth-building in target-role skills.")

    lines.extend([
        "3) Weekly execution loop:",
        f"   - Project: {project_block}",
        f"   - Market: {market_block}",
        f"   - Pipeline: {pipeline_block}",
        f"4) Go/Pivot checkpoint: Reassess at day {checkpoint_days} based on interview traction + gap closure velocity.",
    ])
    return "\n".join(lines)
