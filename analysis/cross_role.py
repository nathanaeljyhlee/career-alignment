"""
Cross-Role Comparative Analysis.

Compares fit_results and gap_results across all matched roles to produce:
  - Role ranking by composite score and effort-to-fit
  - Shared gaps (skills missing across multiple roles)
  - Leverage skills (skills whose acquisition unlocks the most roles)
  - Template-based comparative narrative (no LLM call — deterministic)

All logic is purely deterministic (no Ollama calls).
"""
import re
from typing import Any


# Gap type weights for effort computation (mirrors tuning.yaml gap_analysis.gap_type_weights)
_GAP_TYPE_WEIGHTS = {
    "hard_skills": 0.50,
    "market_signals": 0.35,
    "narrative_coherence": 0.15,
}


def _normalize_gap_description(description: str) -> str:
    """Strip common prefixes and normalize gap description to a skill-like key."""
    description = description.lower().strip()
    # Remove common prefixes
    prefixes = [
        "lacks ", "missing ", "no ", "limited ", "weak ", "insufficient ",
        "need ", "needs ", "requires ", "require ",
    ]
    for prefix in prefixes:
        if description.startswith(prefix):
            description = description[len(prefix):]
    # Take only the first 5 words as the key (avoids over-splitting)
    words = description.split()[:5]
    return " ".join(words)


def _fuzzy_group_gaps(
    all_gaps: list[dict],
) -> dict[str, list[dict]]:
    """
    Group gap items by normalized description key.
    Returns {normalized_key: [gap_item_dict, ...]} sorted by occurrence count desc.
    """
    groups: dict[str, list[dict]] = {}
    for gap in all_gaps:
        key = _normalize_gap_description(gap.get("description", ""))
        if not key:
            continue
        if key not in groups:
            groups[key] = []
        groups[key].append(gap)
    return groups


def cross_role_analysis(
    fit_results: list[dict],
    gap_results: list[dict],
    skill_overlaps: dict[str, dict],
) -> dict:
    """
    Produce cross-role comparative insights.

    Args:
        fit_results: AggregatedRoleFit dicts (from engine.py state.fit_results)
        gap_results: RoleGapAnalysis dicts (from engine.py state.gap_results)
        skill_overlaps: {role_id: overlap_dict} from compute_skill_overlap

    Returns:
        {
            "role_ranking": [...],
            "shared_gaps": [...],
            "leverage_skills": [...],
            "comparative_narrative": str,
            "effort_ranking": [...],
        }
    """
    if not fit_results:
        return {
            "role_ranking": [],
            "shared_gaps": [],
            "leverage_skills": [],
            "comparative_narrative": "No roles to compare.",
            "effort_ranking": [],
        }

    # Build lookup: role_id -> gap_result
    gap_by_role: dict[str, dict] = {}
    for gr in gap_results:
        gap_by_role[gr.get("role_id", "")] = gr

    # --- 1. Role ranking ---
    role_ranking = []
    for fit in fit_results:
        role_id = fit.get("role_id", "")
        gap = gap_by_role.get(role_id, {})
        overlap = skill_overlaps.get(role_id, {})

        composite = fit.get("composite_score", 0.0)
        overlap_score = overlap.get("overlap_score", 0.0)
        gap_severity = gap.get("composite_severity", 0.0)
        effort_to_fit = round(gap_severity * (1.0 - overlap_score), 3)

        role_ranking.append({
            "role_name": fit.get("role_name", ""),
            "role_id": role_id,
            "composite_score": composite,
            "overlap_score": overlap_score,
            "gap_severity": gap_severity,
            "effort_to_fit": effort_to_fit,
            "fit_band": fit.get("fit_band", ""),
        })

    role_ranking.sort(key=lambda r: r["composite_score"], reverse=True)

    # --- 2. Effort ranking (lower effort = better ROI) ---
    effort_ranking = sorted(
        [
            {
                "role_name": r["role_name"],
                "effort_to_fit": r["effort_to_fit"],
                "current_fit": r["composite_score"],
            }
            for r in role_ranking
        ],
        key=lambda r: r["effort_to_fit"],
    )

    # --- 3. Shared gaps ---
    # Collect all gap items tagged with their role
    all_gap_items: list[dict] = []
    for gr in gap_results:
        role_name = gr.get("role_name", "")
        role_id = gr.get("role_id", "")
        for gap_item in gr.get("gaps", []):
            enriched = dict(gap_item)
            enriched["_role_name"] = role_name
            enriched["_role_id"] = role_id
            all_gap_items.append(enriched)

    gap_groups = _fuzzy_group_gaps(all_gap_items)

    # Only include gaps that appear in 2+ roles
    shared_gaps = []
    for key, items in gap_groups.items():
        roles_affected = list({item["_role_name"] for item in items})
        if len(roles_affected) < 2:
            continue

        avg_severity = round(sum(item.get("severity", 0) for item in items) / len(items), 3)

        # Most common addressability
        addr_counts: dict[str, int] = {}
        for item in items:
            a = item.get("addressability", "semester_project")
            addr_counts[a] = addr_counts.get(a, 0) + 1
        addressability = max(addr_counts, key=addr_counts.get)

        shared_gaps.append({
            "skill": key,
            "roles_affected": roles_affected,
            "avg_severity": avg_severity,
            "addressability": addressability,
            "leverage_multiplier": len(roles_affected),
        })

    shared_gaps.sort(key=lambda g: (g["leverage_multiplier"], g["avg_severity"]), reverse=True)

    # --- 4. Leverage skills ---
    # For each shared gap, estimate total fit improvement if closed
    leverage_skills = []
    for sg in shared_gaps:
        # Estimate improvement per role: severity * gap_type_weight
        # We don't know gap_type from the key alone, default to hard_skills weight
        gap_type_weight = _GAP_TYPE_WEIGHTS.get("hard_skills", 0.50)
        total_fit_improvement = round(
            sg["avg_severity"] * gap_type_weight * len(sg["roles_affected"]), 3
        )

        # Build recommendation based on addressability
        if sg["addressability"] == "quick_win":
            recommendation = f"Complete a targeted online course or side project to demonstrate {sg['skill']}."
        elif sg["addressability"] == "semester_project":
            recommendation = f"Pursue a semester-long project or elective course focused on {sg['skill']}."
        else:
            recommendation = f"Develop {sg['skill']} through an internship or sustained work experience."

        leverage_skills.append({
            "skill": sg["skill"],
            "roles_unlocked": sg["roles_affected"],
            "total_fit_improvement": total_fit_improvement,
            "addressability": sg["addressability"],
            "recommendation": recommendation,
        })

    leverage_skills.sort(key=lambda ls: ls["total_fit_improvement"], reverse=True)

    # --- 5. Comparative narrative (template-based, no LLM) ---
    narrative = _build_narrative(role_ranking, shared_gaps, leverage_skills)

    return {
        "role_ranking": role_ranking,
        "shared_gaps": shared_gaps[:5],  # Top 5 shared gaps
        "leverage_skills": leverage_skills[:3],  # Top 3 leverage skills
        "comparative_narrative": narrative,
        "effort_ranking": effort_ranking,
    }


def _build_narrative(
    role_ranking: list[dict],
    shared_gaps: list[dict],
    leverage_skills: list[dict],
) -> str:
    """Build a 3-5 sentence template narrative comparing roles."""
    if not role_ranking:
        return "Insufficient data for comparative analysis."

    top = role_ranking[0]
    top_score_pct = f"{top['composite_score']:.0%}"
    top_overlap_pct = f"{top['overlap_score']:.0%}"

    sentence1 = (
        f"Your strongest fit is {top['role_name']} ({top_score_pct}), "
        f"with {top_overlap_pct} required-skill coverage."
    )

    if leverage_skills:
        top_lever = leverage_skills[0]
        n_roles = len(top_lever["roles_unlocked"])
        sentence2 = (
            f"Your highest-leverage learning investment is {top_lever['skill']}, "
            f"which would improve fit across {n_roles} role{'s' if n_roles != 1 else ''}."
        )
    else:
        sentence2 = "Your gaps are role-specific — no single skill unlocks multiple roles."

    if len(role_ranking) >= 2:
        second = role_ranking[1]
        second_score_pct = f"{second['composite_score']:.0%}"
        effort_diff = top["effort_to_fit"] - second["effort_to_fit"]
        if effort_diff > 0:
            effort_comparison = "more effort"
        elif effort_diff < 0:
            effort_comparison = "less effort"
        else:
            effort_comparison = "similar effort"
        sentence3 = (
            f"Compared to {second['role_name']} ({second_score_pct}), "
            f"{top['role_name']} requires {effort_comparison} to reach competitive fit."
        )
    else:
        sentence3 = ""

    parts = [sentence1, sentence2]
    if sentence3:
        parts.append(sentence3)

    return " ".join(parts)


def prioritize_gaps_by_graph(
    gap_results: list[dict],
    skill_graph: dict,
    candidate_skills: set[str],
) -> list[dict]:
    """
    Re-rank gaps within each role using skill graph data.

    Prioritization logic:
    1. Hub skill gaps (high degree) are more impactful — higher severity boost
    2. "Almost there" gaps (candidate has 3/4 neighbors) are more addressable
    3. Cluster-completing gaps get highest leverage label

    Args:
        gap_results: RoleGapAnalysis dicts
        skill_graph: From build_skill_graph()
        candidate_skills: Lowercase canonical skill names the candidate has

    Returns:
        gap_results with gaps re-ranked/annotated by graph priority
    """
    adjacency = skill_graph.get("adjacency", {})
    hub_skills = {s.lower() for s in skill_graph.get("hub_skills", [])}

    updated_results = []
    for role_gap in gap_results:
        updated_gaps = []
        for gap_item in role_gap.get("gaps", []):
            gap_copy = dict(gap_item)
            desc_lower = gap_item.get("description", "").lower()

            # Check if this gap is a hub skill (more impactful)
            is_hub = any(hub in desc_lower for hub in hub_skills)

            # Check neighbor coverage ("almost there")
            best_coverage = 0.0
            for skill_name, skill_data in adjacency.items():
                if skill_name.lower() in desc_lower or desc_lower in skill_name.lower():
                    neighbors = {n.lower() for n in skill_data.get("neighbors", {}).keys()}
                    if neighbors:
                        candidate_coverage = len(
                            neighbors & {s.lower() for s in candidate_skills}
                        ) / len(neighbors)
                        best_coverage = max(best_coverage, candidate_coverage)

            # Annotate gap with graph metadata
            gap_copy["_hub_skill"] = is_hub
            gap_copy["_neighbor_coverage"] = round(best_coverage, 2)

            # Addressability upgrade for "almost there" gaps
            if best_coverage >= 0.60 and gap_copy.get("addressability") == "long_term":
                gap_copy["addressability"] = "semester_project"
            elif best_coverage >= 0.80 and gap_copy.get("addressability") == "semester_project":
                gap_copy["addressability"] = "quick_win"

            updated_gaps.append(gap_copy)

        # Re-sort: hub skills first, then by severity desc
        updated_gaps.sort(
            key=lambda g: (g.get("_hub_skill", False), g.get("severity", 0)),
            reverse=True,
        )

        role_gap_copy = dict(role_gap)
        role_gap_copy["gaps"] = updated_gaps
        updated_results.append(role_gap_copy)

    return updated_results
