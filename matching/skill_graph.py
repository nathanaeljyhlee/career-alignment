"""
Skill Co-occurrence Graph.

Builds a graph from role_taxonomy.json where:
  - Nodes are skill names
  - Edges connect skills that appear together in the same role
  - Edge weight = number of roles in which both skills co-occur

Used for:
  - Skill inference: if a candidate has 60%+ of a skill's neighbors, they likely have it implicitly
  - Gap prioritization: hub skills (high degree) are more impactful gaps
  - Cluster-based leverage: filling a gap that completes a skill cluster is high-leverage

No external dependencies — pure Python with collections.
"""
import json
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

# Default taxonomy path (resolved relative to this file's location)
_DEFAULT_TAXONOMY_PATH = Path(__file__).parent.parent / "data" / "role_taxonomy.json"


def build_skill_graph(taxonomy_path: str | None = None) -> dict:
    """
    Build adjacency data from role_taxonomy.json.

    Args:
        taxonomy_path: Path to role_taxonomy.json. Defaults to data/role_taxonomy.json.

    Returns:
        {
            "adjacency": {
                "skill_name": {
                    "neighbors": {"other_skill": weight, ...},
                    "roles": ["role_id", ...],
                    "degree": int,
                }
            },
            "clusters": [
                {
                    "name": str,
                    "skills": list[str],
                    "roles": list[str],
                }
            ],
            "hub_skills": list[str],  # Top-10 most connected skills
        }
    """
    path = Path(taxonomy_path) if taxonomy_path else _DEFAULT_TAXONOMY_PATH
    if not path.exists():
        logger.warning("role_taxonomy.json not found at %s — returning empty graph", path)
        return {"adjacency": {}, "clusters": [], "hub_skills": []}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    roles = data.get("roles", data) if isinstance(data, dict) else data

    # Build adjacency
    adjacency: dict[str, dict] = {}
    # adjacency[skill]["neighbors"][other_skill] = weight
    # adjacency[skill]["roles"] = set of role_ids

    for role in roles:
        role_id = role.get("role_id", "")
        role_skills = role.get("required_skills", []) + role.get("preferred_skills", [])

        # Ensure all skills exist in adjacency
        for skill in role_skills:
            if skill not in adjacency:
                adjacency[skill] = {"neighbors": {}, "roles": set(), "degree": 0}
            adjacency[skill]["roles"].add(role_id)

        # Add edges for every pair that co-occurs in this role
        for i, skill_a in enumerate(role_skills):
            for skill_b in role_skills[i + 1:]:
                if skill_a == skill_b:
                    continue
                # Bidirectional edge
                adjacency[skill_a]["neighbors"][skill_b] = (
                    adjacency[skill_a]["neighbors"].get(skill_b, 0) + 1
                )
                adjacency[skill_b]["neighbors"][skill_a] = (
                    adjacency[skill_b]["neighbors"].get(skill_a, 0) + 1
                )

    # Compute degree
    for skill, data_node in adjacency.items():
        data_node["degree"] = len(data_node["neighbors"])
        data_node["roles"] = list(data_node["roles"])  # Convert set to list for JSON

    # Hub skills = top 10 by degree
    sorted_by_degree = sorted(
        adjacency.keys(), key=lambda s: adjacency[s]["degree"], reverse=True
    )
    hub_skills = sorted_by_degree[:10]

    # Clusters via connected components (BFS/DFS)
    clusters = _find_clusters(adjacency, roles)

    return {
        "adjacency": adjacency,
        "clusters": clusters,
        "hub_skills": hub_skills,
    }


def _find_clusters(adjacency: dict, roles: list[dict]) -> list[dict]:
    """
    Find connected components in the skill graph.
    Each component becomes a cluster, named by the most frequent role category.
    """
    visited: set[str] = set()
    components: list[set[str]] = []

    def bfs(start: str) -> set[str]:
        component: set[str] = set()
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            component.add(node)
            for neighbor in adjacency.get(node, {}).get("neighbors", {}).keys():
                if neighbor not in visited:
                    queue.append(neighbor)
        return component

    for skill in adjacency:
        if skill not in visited:
            component = bfs(skill)
            if len(component) > 1:  # Only include clusters with 2+ skills
                components.append(component)

    # Build role category lookup
    role_by_id: dict[str, str] = {r.get("role_id", ""): r.get("category", "") for r in roles}

    clusters = []
    for component in components:
        # Find roles this cluster's skills appear in
        cluster_roles: list[str] = []
        category_counts: dict[str, int] = defaultdict(int)
        for skill in component:
            for role_id in adjacency.get(skill, {}).get("roles", []):
                if role_id not in cluster_roles:
                    cluster_roles.append(role_id)
                category = role_by_id.get(role_id, "")
                if category:
                    category_counts[category] += 1

        # Name the cluster by most frequent category
        cluster_name = (
            max(category_counts, key=category_counts.get).replace("_", " ").title()
            if category_counts
            else "General"
        )

        clusters.append({
            "name": cluster_name,
            "skills": sorted(component),
            "roles": cluster_roles,
        })

    # Sort by cluster size descending
    clusters.sort(key=lambda c: len(c["skills"]), reverse=True)
    return clusters


def infer_from_graph(
    candidate_skills: set[str],
    skill_graph: dict,
    min_neighbor_coverage: float = 0.60,
) -> list[dict]:
    """
    Infer skills the candidate likely has based on graph adjacency.

    If a candidate has >= min_neighbor_coverage of a skill's neighbors,
    they probably have that skill implicitly even if not explicitly extracted.

    Args:
        candidate_skills: Lowercase canonical skill names the candidate has
        skill_graph: From build_skill_graph()
        min_neighbor_coverage: Threshold (default 0.60 = 60% of neighbors required)

    Returns:
        List of {"skill": str, "confidence": float, "reason": str}
        for inferred skills (not already in candidate_skills)
    """
    adjacency = skill_graph.get("adjacency", {})
    if not adjacency:
        return []

    candidate_lower = {s.lower() for s in candidate_skills}
    inferred: list[dict] = []

    for skill_name, skill_data in adjacency.items():
        skill_lower = skill_name.lower()
        if skill_lower in candidate_lower:
            continue  # Already have this skill

        neighbors = skill_data.get("neighbors", {})
        if len(neighbors) < 2:
            continue  # Not enough neighbors to infer from

        neighbor_names = {n.lower() for n in neighbors.keys()}
        matched_neighbors = neighbor_names & candidate_lower
        coverage = len(matched_neighbors) / len(neighbor_names)

        if coverage >= min_neighbor_coverage:
            matched_list = sorted(matched_neighbors)[:4]
            confidence = round(min(0.85, 0.50 + coverage * 0.40), 2)

            inferred.append({
                "skill": skill_name,
                "confidence": confidence,
                "reason": (
                    f"Graph inference: candidate has {len(matched_neighbors)}/{len(neighbor_names)} "
                    f"co-occurring skills ({', '.join(matched_list)})"
                ),
            })

    # Sort by confidence descending, cap at 5 to avoid noise
    inferred.sort(key=lambda x: x["confidence"], reverse=True)
    return inferred[:5]
