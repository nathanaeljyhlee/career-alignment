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


def compute_skill_overlap(
    candidate_skills: list[dict],
    role: dict,
    candidate_profile: dict[str, Any] | None = None,
    embedding_threshold: float | None = None,
) -> dict:
    """
    Compute weighted overlap between candidate skills and role requirements.

    Args:
        candidate_skills: NormalizedSkill dicts from skills_flat
        role: Single role dict from role_taxonomy.json
        embedding_threshold: Cosine similarity threshold for embedding fallback

    Returns:
        {
            "required_coverage": float,     # 0-1, fraction of required_skills matched
            "preferred_coverage": float,    # 0-1, fraction of preferred_skills matched
            "expected_signal_coverage": float,  # 0-1, expected_signals coverage vs profile text embeddings
            "overlap_score": float,         # required_weight * required + preferred_weight * preferred (from tuning.yaml)
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
    expected_signal_threshold = 0.50

    # Build candidate skill name set (canonical + original mentions, lowercased)
    candidate_names: set[str] = set()
    for s in candidate_skills:
        if s.get("canonical_name"):
            candidate_names.add(s["canonical_name"].lower())
        if s.get("original_mention"):
            candidate_names.add(s["original_mention"].lower())

    required_skills: list[str] = role.get("required_skills", [])
    preferred_skills: list[str] = role.get("preferred_skills", [])
    expected_signals: list[str] = role.get("expected_signals", [])

    # Build compact profile text snippets for expected signal semantic coverage.
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
    if all_missing and candidate_names:
        try:
            candidate_name_list = list(candidate_names)
            candidate_embeddings = _embed_texts(candidate_name_list)
            role_embeddings = _embed_texts(all_missing)

            # Similarity matrix: shape (n_missing_role_skills, n_candidate_skills)
            sim_matrix = role_embeddings @ candidate_embeddings.T

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
            # Keep substring-based results as-is

    # Compute coverage scores
    required_coverage = len(matched_req) / len(required_skills) if required_skills else 1.0
    preferred_coverage = len(matched_pref) / len(preferred_skills) if preferred_skills else 1.0
    expected_signal_coverage = 1.0
    if expected_signals and profile_text_chunks:
        try:
            expected_signal_embeddings = _embed_texts(expected_signals)
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
