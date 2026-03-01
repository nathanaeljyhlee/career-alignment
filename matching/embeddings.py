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
) -> list[dict[str, Any]]:
    """Find the top-K most similar roles for the candidate profile.

    Returns list of role dicts enriched with similarity_score, sorted descending.
    Only roles above embedding_min_similarity are included.
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

    # Get top-K indices above threshold
    sorted_indices = np.argsort(similarities)[::-1]
    results = []
    for idx in sorted_indices:
        score = float(similarities[idx])
        if score < min_sim:
            break
        if len(results) >= top_k:
            break
        role = dict(roles[idx])
        role["similarity_score"] = round(score, 4)
        results.append(role)

    logger.info(
        "Embedding pre-match: %d roles above threshold %.2f (top-K=%d)",
        len(results), min_sim, top_k,
    )
    return results


