"""
Deterministic Skill Overlap Computation.

Computes weighted Jaccard-style overlap between candidate skills and role
requirements. Used as a structural anchor for LLM scoring in Agents 3 and 4.

Matching logic (in order of precision):
  1. Exact lowercase match
  2. Substring match (either string is a substring of the other)
  3. Embedding similarity >= skill_overlap.embedding_threshold (tuning.yaml) via Ollama nomic-embed-text (fallback)
"""
import logging
from typing import Any

import numpy as np
import ollama

from config import get_tuning

logger = logging.getLogger(__name__)


def _embed_texts(texts: list[str]) -> np.ndarray:
    """Embed texts using Ollama nomic-embed-text. Returns L2-normalized float32 array."""
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    model_name = get_tuning("models", "embedding_model") or "nomic-embed-text"
    response = ollama.embed(model=model_name, input=texts)
    embeddings = np.array(response["embeddings"], dtype=np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return embeddings / norms


def _substring_match(candidate_names: set[str], role_skill: str) -> bool:
    """Check if a role skill matches any candidate skill via exact or substring."""
    role_lower = role_skill.lower()
    if role_lower in candidate_names:
        return True
    for c in candidate_names:
        if role_lower in c or c in role_lower:
            return True
    return False


def _build_profile_text_chunks(candidate_profile: dict[str, Any] | None, candidate_names: set[str]) -> list[str]:
    """Build compact profile text snippets for expected signal semantic coverage."""
    profile_text_chunks: list[str] = []
    if candidate_profile:
        narrative_summary = candidate_profile.get("narrative_summary")
        if isinstance(narrative_summary, str) and narrative_summary.strip():
            profile_text_chunks.append(narrative_summary.strip())

        highest_education = candidate_profile.get("highest_education")
        if isinstance(highest_education, str) and highest_education.strip():
            profile_text_chunks.append(highest_education.strip())

        for cluster in candidate_profile.get("skill_clusters", []) or []:
            if not isinstance(cluster, dict):
                continue
            cluster_name = (cluster.get("cluster_name") or "").strip()
            skills = [str(s).strip() for s in (cluster.get("skills") or []) if str(s).strip()]
            evidence = (cluster.get("evidence_summary") or "").strip()
            combined = " | ".join(part for part in [cluster_name, ", ".join(skills), evidence] if part)
            if combined:
                profile_text_chunks.append(combined)

        for signal in candidate_profile.get("industry_signals", []) or []:
            if not isinstance(signal, dict):
                continue
            industry = (signal.get("industry") or "").strip()
            evidence = (signal.get("evidence") or "").strip()
            recency = (signal.get("recency") or "").strip()
            combined = " | ".join(part for part in [industry, recency, evidence] if part)
            if combined:
                profile_text_chunks.append(combined)

    if not profile_text_chunks:
        profile_text_chunks = list(candidate_names)

    return profile_text_chunks


def build_overlap_context(
    candidate_skills: list[dict],
    candidate_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Precompute candidate-side overlap artifacts for reuse across roles."""
    candidate_names: set[str] = set()
    for s in candidate_skills:
        if s.get("canonical_name"):
            candidate_names.add(s["canonical_name"].lower())
        if s.get("original_mention"):
            candidate_names.add(s["original_mention"].lower())

    candidate_name_list = list(candidate_names)
    profile_text_chunks = _build_profile_text_chunks(candidate_profile, candidate_names)

    context: dict[str, Any] = {
        "candidate_names": candidate_names,
        "candidate_name_list": candidate_name_list,
        "profile_text_chunks": profile_text_chunks,
        "candidate_skill_embeddings": None,
        "profile_text_embeddings": None,
    }

    try:
        if candidate_name_list:
            context["candidate_skill_embeddings"] = _embed_texts(candidate_name_list)
    except Exception as e:
        logger.warning("Candidate skill embedding precompute failed (non-fatal): %s", e)

    try:
        if profile_text_chunks:
            context["profile_text_embeddings"] = _embed_texts(profile_text_chunks)
    except Exception as e:
        logger.warning("Profile text embedding precompute failed (non-fatal): %s", e)

    return context


def compute_skill_overlap(
    candidate_skills: list[dict],
    role: dict,
    candidate_profile: dict[str, Any] | None = None,
    embedding_threshold: float | None = None,
    overlap_context: dict[str, Any] | None = None,
) -> dict:
    """
    Compute weighted overlap between candidate skills and role requirements.

    Args:
        candidate_skills: NormalizedSkill dicts from skills_flat
        role: Single role dict from role_taxonomy.json
        embedding_threshold: Cosine similarity threshold for embedding fallback
        overlap_context: Optional precomputed context from build_overlap_context()

    Returns:
        {
            "required_coverage": float,
            "preferred_coverage": float,
            "expected_signal_coverage": float,
            "overlap_score": float,
            "matched_required": list[str],
            "missing_required": list[str],
            "matched_preferred": list[str],
            "missing_preferred": list[str],
        }
    """
    overlap_cfg = get_tuning("skill_overlap") or {}
    if embedding_threshold is None:
        embedding_threshold = overlap_cfg.get("embedding_threshold", 0.80)
    required_weight = overlap_cfg.get("required_weight", 0.70)
    preferred_weight = overlap_cfg.get("preferred_weight", 0.30)
    expected_signal_threshold = overlap_cfg.get("expected_signal_threshold", 0.50)

    context = overlap_context or build_overlap_context(candidate_skills, candidate_profile)
    candidate_names: set[str] = context.get("candidate_names") or set()

    required_skills: list[str] = role.get("required_skills", [])
    preferred_skills: list[str] = role.get("preferred_skills", [])
    expected_signals: list[str] = role.get("expected_signals", [])

    # Phase 1: exact + substring matching
    matched_req: list[str] = []
    missing_req: list[str] = []
    for skill in required_skills:
        if _substring_match(candidate_names, skill):
            matched_req.append(skill)
        else:
            missing_req.append(skill)

    matched_pref: list[str] = []
    missing_pref: list[str] = []
    for skill in preferred_skills:
        if _substring_match(candidate_names, skill):
            matched_pref.append(skill)
        else:
            missing_pref.append(skill)

    # Phase 2: embedding fallback for remaining unmatched skills
    all_missing = missing_req + missing_pref
    candidate_name_list = context.get("candidate_name_list") or []
    candidate_skill_embeddings = context.get("candidate_skill_embeddings")
    if all_missing and candidate_name_list:
        try:
            if candidate_skill_embeddings is None:
                candidate_skill_embeddings = _embed_texts(candidate_name_list)
            role_embeddings = _embed_texts(all_missing)

            # Similarity matrix: shape (n_missing_role_skills, n_candidate_skills)
            sim_matrix = role_embeddings @ candidate_skill_embeddings.T

            still_missing_req: list[str] = []
            for i, skill in enumerate(missing_req):
                best_sim = float(sim_matrix[i].max())
                if best_sim >= embedding_threshold:
                    matched_req.append(skill)
                else:
                    still_missing_req.append(skill)

            still_missing_pref: list[str] = []
            offset = len(missing_req)
            for i, skill in enumerate(missing_pref):
                best_sim = float(sim_matrix[offset + i].max())
                if best_sim >= embedding_threshold:
                    matched_pref.append(skill)
                else:
                    still_missing_pref.append(skill)

            missing_req = still_missing_req
            missing_pref = still_missing_pref

        except Exception as e:
            logger.warning("Embedding fallback in skill_overlap failed (non-fatal): %s", e)

    required_coverage = len(matched_req) / len(required_skills) if required_skills else 1.0
    preferred_coverage = len(matched_pref) / len(preferred_skills) if preferred_skills else 1.0

    expected_signal_coverage = 1.0
    profile_text_chunks = context.get("profile_text_chunks") or []
    profile_text_embeddings = context.get("profile_text_embeddings")
    if expected_signals and profile_text_chunks:
        try:
            expected_signal_embeddings = _embed_texts(expected_signals)
            if profile_text_embeddings is None:
                profile_text_embeddings = _embed_texts(profile_text_chunks)
            signal_sim_matrix = expected_signal_embeddings @ profile_text_embeddings.T
            signal_matches = sum(
                1 for i in range(len(expected_signals))
                if float(signal_sim_matrix[i].max()) >= expected_signal_threshold
            )
            expected_signal_coverage = signal_matches / len(expected_signals)
        except Exception as e:
            logger.warning("Expected signal coverage embedding step failed (non-fatal): %s", e)

    overlap_score = required_weight * required_coverage + preferred_weight * preferred_coverage

    return {
        "required_coverage": round(required_coverage, 3),
        "preferred_coverage": round(preferred_coverage, 3),
        "expected_signal_coverage": round(expected_signal_coverage, 3),
        "overlap_score": round(overlap_score, 3),
        "matched_required": matched_req,
        "missing_required": missing_req,
        "matched_preferred": matched_pref,
        "missing_preferred": missing_pref,
    }
