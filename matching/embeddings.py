"""
Embedding-based role pre-matching.

Uses Ollama's nomic-embed-text to embed the candidate profile and compare
against pre-embedded role taxonomy definitions. Returns top-K most
similar roles for downstream LLM reasoning.

This is the "bi-encoder retrieval" stage of the hybrid matching pipeline.
"""
import json
import logging
from typing import Any

import numpy as np
import ollama as ollama_client

from config import DATA_DIR, get_tuning

logger = logging.getLogger(__name__)

_role_embeddings: np.ndarray | None = None
_role_taxonomy: list[dict] = []


def _embed_texts(texts: list[str]) -> np.ndarray:
    """Embed texts using Ollama's embedding model (nomic-embed-text).
    Returns L2-normalized embeddings as float32 numpy array.
    """
    model_name = get_tuning("models", "embedding_model") or "nomic-embed-text"
    response = ollama_client.embed(model=model_name, input=texts)
    embeddings = np.array(response["embeddings"], dtype=np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return embeddings / norms


def _load_role_taxonomy() -> list[dict]:
    """Load role definitions from data/role_taxonomy.json."""
    global _role_taxonomy
    if _role_taxonomy:
        return _role_taxonomy
    path = DATA_DIR / "role_taxonomy.json"
    if not path.exists():
        logger.warning("role_taxonomy.json not found")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _role_taxonomy = data.get("roles", data) if isinstance(data, dict) else data
    return _role_taxonomy


def _get_role_embeddings() -> tuple[np.ndarray, list[dict]]:
    """Embed all role definitions. Cached after first call."""
    global _role_embeddings
    roles = _load_role_taxonomy()
    if _role_embeddings is not None:
        return _role_embeddings, roles

    # Build rich text representation for each role
    role_texts = []
    for role in roles:
        text = (
            f"{role.get('role_name', '')}: {role.get('description', '')}. "
            f"Required skills: {', '.join(role.get('required_skills', []))}. "
            f"Preferred skills: {', '.join(role.get('preferred_skills', []))}. "
            f"Expected signals: {', '.join(role.get('expected_signals', []))}."
        )
        role_texts.append(text)

    _role_embeddings = _embed_texts(role_texts)
    return _role_embeddings, roles


def _build_profile_text(
    profile: dict[str, Any],
    skills: list[dict[str, Any]],
    motivation: dict[str, Any] | None = None,
) -> str:
    """Build a rich text representation of the candidate for embedding."""
    parts = []

    if profile.get("narrative_summary"):
        parts.append(profile["narrative_summary"])

    for cluster in profile.get("skill_clusters", []):
        skills_str = ", ".join(cluster.get("skills", []))
        parts.append(f"{cluster.get('cluster_name', '')}: {skills_str}")

    for signal in profile.get("industry_signals", []):
        parts.append(f"{signal.get('industry', '')} ({signal.get('recency', '')})")

    top_skills = sorted(skills, key=lambda s: s.get("confidence", 0), reverse=True)[:15]
    skill_names = [s.get("canonical_name", s.get("skill_name", "")) for s in top_skills]
    parts.append(f"Key skills: {', '.join(skill_names)}")

    if motivation and motivation.get("summary"):
        parts.append(f"Motivation: {motivation['summary']}")

    return " ".join(parts)


def match_roles(
    profile: dict[str, Any],
    skills: list[dict[str, Any]],
    motivation: dict[str, Any] | None = None,
    return_diagnostics: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, Any]]:
    """Find the top-K most similar roles for the candidate profile.

    Returns list of role dicts enriched with similarity_score, sorted descending.
    Only roles above embedding_min_similarity and within top-K are included.

    If return_diagnostics=True, also returns retrieval metadata with full role ranking
    and include/exclude reasons for auditability.
    """
    matching_cfg = get_tuning("role_matching") or {}
    top_k = matching_cfg.get("embedding_top_k", 6)
    min_sim = matching_cfg.get("embedding_min_similarity", 0.30)

    role_embs, roles = _get_role_embeddings()
    if len(roles) == 0:
        return []

    # Embed candidate profile
    profile_text = _build_profile_text(profile, skills, motivation)
    profile_emb = _embed_texts([profile_text])

    # Compute cosine similarities (inner product for normalized vectors)
    similarities = (profile_emb @ role_embs.T).flatten()

    # Build full ranking first for diagnostics.
    sorted_indices = np.argsort(similarities)[::-1]
    ranked_roles = []
    for rank, idx in enumerate(sorted_indices, start=1):
        role = dict(roles[idx])
        role["similarity_score"] = round(float(similarities[idx]), 4)
        role["rank"] = rank
        ranked_roles.append(role)

    # Then select top-K that clear threshold.
    results = []
    for role in ranked_roles:
        score = role["similarity_score"]
        if score < min_sim:
            break
        if len(results) >= top_k:
            break
        results.append({k: v for k, v in role.items() if k != "rank"})

    logger.info(
        "Embedding pre-match: %d roles above threshold %.2f (top-K=%d)",
        len(results), min_sim, top_k,
    )
    if not return_diagnostics:
        return results

    selected_ids = {r.get("role_id") for r in results}
    considered = []
    excluded = []
    for role in ranked_roles:
        role_id = role.get("role_id")
        score = role.get("similarity_score", 0.0)
        if role_id in selected_ids:
            reason = "selected"
        elif score < min_sim:
            reason = "below_threshold"
        elif role.get("rank", 0) > top_k:
            reason = "outside_top_k"
        else:
            reason = "not_selected"

        row = {
            "role_id": role_id,
            "role_name": role.get("role_name"),
            "rank": role.get("rank"),
            "similarity_score": score,
            "reason": reason,
        }
        considered.append(row)
        if reason != "selected":
            excluded.append(row)

    diagnostics = {
        "total_roles": len(roles),
        "top_k": top_k,
        "threshold": min_sim,
        "considered_roles": considered,
        "excluded_roles": excluded,
    }
    return results, diagnostics

