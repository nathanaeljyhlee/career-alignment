"""
Output Builder for Candidate-Market Fit Engine.

Formats pipeline results into core sections plus strategic action modules:
  Section 1: Candidate Snapshot (profile summary)
  Section 2: Skill Profile (clusters + O*NET grounding)
  Section 3: Win Now Roles (strong + competitive fits)
  Section 4: Invest to Pivot Roles (developmental with viable pivots)
  Section 5: Gap Analysis (per-role gaps + leverage moves)
  Section 6: Strategic Decision (Win Now vs Invest to Pivot recommendation)
  Section 7: Cross-Role Analysis (shared gaps, leverage, effort ranking)
  Section 8: Decision Sprint (single prioritized 90-day plan)
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
    """Build the full output structure for the Streamlit UI."""
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

    win_now: list[dict[str, Any]] = []
    pivot: list[dict[str, Any]] = []
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
        elif gap and gap.get("pivot_viable", False):
            pivot.append(entry)

    result["section_3_win_now"] = win_now[:max_win_now]
    result["section_4_pivot"] = pivot[:max_pivot]
    result["section_5_gaps"] = gap_results or []
    result["section_6_strategic"] = _build_strategic_decision(win_now, pivot)
    result["section_8_decision_sprint"] = _build_decision_sprint(
        win_now=win_now,
        pivot=pivot,
        gap_results=gap_results or [],
        cross_role=cross_role or {},
        motivation=motivation or {},
    )

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
            {
                "name": s.get("canonical_name", ""),
                "confidence": s.get("confidence", 0),
                "type": s.get("skill_type", ""),
            }
            for s in skills[:15]
        ],
    }


def _format_role_list(entries: list[dict]) -> str:
    parts = []
    for entry in entries:
        fit = entry.get("fit", {})
        name = fit.get("role_name", "Unknown")
        score = fit.get("composite_score", 0)
        parts.append(f"{name} ({score:.0%})")
    return ", ".join(parts)


def _build_strategic_decision(win_now: list[dict], pivot: list[dict]) -> dict[str, Any]:
    """Section 6: Strategic Decision Module."""
    if not win_now and not pivot:
        return {
            "recommendation": "insufficient_data",
            "summary": "Not enough role matches to generate a strategic recommendation.",
        }

    win_now_names = _format_role_list(win_now)
    pivot_names = _format_role_list(pivot)

    if win_now and not pivot:
        best = win_now[0]
        return {
            "recommendation": "win_now",
            "summary": (
                f"Focus your applications on these roles where you can compete now: {win_now_names}. "
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


def _confidence_score(confidence: dict[str, Any] | None) -> float:
    if not confidence:
        return 0.5
    if isinstance(confidence.get("score"), (int, float)):
        return max(0.0, min(1.0, float(confidence["score"])))
    band = str(confidence.get("band", "moderate")).lower()
    return {"high": 0.9, "moderate": 0.6, "low": 0.3}.get(band, 0.5)


def _motivation_penalty(role_name: str, motivation: dict[str, Any]) -> tuple[float, str]:
    """Light guardrail: penalize highly volatile roles when stability preference is strong."""
    themes = motivation.get("themes") or []
    if not isinstance(themes, list):
        return 0.0, ""

    stability_pref = None
    for theme in themes:
        if isinstance(theme, dict) and theme.get("dimension") == "stability_vs_volatility":
            try:
                stability_pref = 1.0 - float(theme.get("score", 0.5))
            except (TypeError, ValueError):
                stability_pref = None
            break

    if stability_pref is None or stability_pref < 0.7:
        return 0.0, ""

    volatile_tokens = ("startup", "venture", "entrepreneur")
    if any(tok in role_name.lower() for tok in volatile_tokens):
        return 0.08, "Role de-prioritized slightly due to strong stability preference in motivation profile."

    return 0.0, ""


def _build_decision_sprint(
    win_now: list[dict[str, Any]],
    pivot: list[dict[str, Any]],
    gap_results: list[dict[str, Any]],
    cross_role: dict[str, Any],
    motivation: dict[str, Any],
) -> dict[str, Any]:
    cfg = (get_tuning("output", "decision_sprint") or {})
    weights = cfg.get("weights") or {}
    w_fit = float(weights.get("fit_score", 0.45))
    w_conf = float(weights.get("confidence_score", 0.30))
    w_effort = float(weights.get("effort_inverse", 0.25))
    checkpoint_days = int(cfg.get("checkpoint_days", 28))

    candidates = win_now + pivot
    if not candidates:
        return {"available": False, "summary": "Not enough role data to build a Decision Sprint."}

    effort_map: dict[str, float] = {}
    for row in cross_role.get("effort_ranking", []) or []:
        role_name = row.get("role_name")
        effort = row.get("effort_to_fit")
        if role_name and isinstance(effort, (int, float)):
            effort_map[role_name] = float(effort)

    max_effort = max(effort_map.values()) if effort_map else 1.0

    ranked = []
    guardrail_notes = []
    for entry in candidates:
        fit = entry.get("fit") or {}
        role_name = fit.get("role_name", "Unknown")
        fit_score = float(fit.get("composite_score", 0.0) or 0.0)
        conf_score = _confidence_score(entry.get("confidence"))
        effort_raw = effort_map.get(role_name)
        effort_norm = min(1.0, effort_raw / max_effort) if effort_raw is not None and max_effort > 0 else 0.5

        score = w_fit * fit_score + w_conf * conf_score + w_effort * (1.0 - effort_norm)
        penalty, note = _motivation_penalty(role_name, motivation)
        score -= penalty
        if note:
            guardrail_notes.append(note)

        ranked.append({
            "entry": entry,
            "score": round(max(0.0, min(1.0, score)), 3),
            "effort_norm": round(effort_norm, 3),
        })

    ranked.sort(key=lambda r: r["score"], reverse=True)
    top = ranked[0]
    top_entry = top["entry"]
    top_fit = top_entry.get("fit") or {}
    top_conf = top_entry.get("confidence") or {}
    top_gap = top_entry.get("gap") or {}

    skills_rank: dict[str, float] = {}

    for shared in cross_role.get("shared_gaps", []) or []:
        skill = str(shared.get("skill", "")).strip().lower()
        if not skill:
            continue
        severity = float(shared.get("avg_severity", 0.5) or 0.5)
        leverage = float(shared.get("leverage_multiplier", 1) or 1)
        skills_rank[skill] = max(skills_rank.get(skill, 0.0), severity * leverage)

    for gap in gap_results:
        for item in gap.get("gaps", []) or []:
            desc = str(item.get("description", "")).strip().lower()
            if not desc:
                continue
            severity = float(item.get("severity", 0.4) or 0.4)
            if item.get("leverage_move"):
                severity *= 1.2
            skills_rank[desc] = max(skills_rank.get(desc, 0.0), severity)

    top_skills = [k for k, _ in sorted(skills_rank.items(), key=lambda kv: kv[1], reverse=True)[:2]]
    while len(top_skills) < 2:
        top_skills.append("portfolio-ready role evidence")

    confidence_band = str(top_conf.get("band", "moderate")).lower()
    mode = "commit" if confidence_band in {"high", "moderate"} else "explore"

    project_move = (top_gap.get("top_leverage_moves") or ["Build one role-relevant project artifact this week."])[0]
    market_block = "Send 3 targeted outreach messages and schedule 1 informational call."
    pipeline_block = "Submit 3 tailored applications and complete 1 interview/case prep session."

    checkpoint_date = (date.today() + timedelta(days=checkpoint_days)).isoformat()
    target_role = top_fit.get("role_name", "Unknown")

    action_plan = (
        f"For the next 90 days, {mode} on {target_role}. "
        f"Prioritize closing {top_skills[0]} and {top_skills[1]}. "
        f"Each week: project work ({project_move}), market conversations (3 outreaches + 1 call), "
        "and application pipeline execution (3 applications + prep). "
        f"Re-evaluate on {checkpoint_date}."
    )

    return {
        "available": True,
        "mode": mode,
        "target_role": target_role,
        "decision_score": top["score"],
        "confidence_band": confidence_band,
        "rationale": (
            f"Selected for strongest blend of fit ({top_fit.get('composite_score', 0):.0%}), "
            f"confidence ({confidence_band}), and effort-to-fit efficiency."
        ),
        "top_skill_closures": top_skills,
        "weekly_plan": {
            "project_block": project_move,
            "market_block": market_block,
            "pipeline_block": pipeline_block,
        },
        "checkpoint_date": checkpoint_date,
        "go_criteria": [
            "You produced at least one role-relevant artifact with measurable signal.",
            "You advanced at least one interview process or repeat recruiter conversation.",
        ],
        "pivot_criteria": [
            "No interview traction after 4 weeks despite weekly execution.",
            "Top gap signals remain unaddressed based on project/recruiter feedback.",
        ],
        "guardrail_notes": guardrail_notes,
        "action_plan_text": action_plan,
    }
