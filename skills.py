"""
Skill extraction + O*NET normalization pipeline.

Hybrid approach (research-backed):
1. Dictionary/alias matching for high-frequency skills (fast, exact)
2. LLM extraction via Ollama for implicit/contextual skills (Qwen 7B)
3. Embedding-based normalization to O*NET taxonomy (sentence-transformers + FAISS)

Thresholds loaded from tuning.yaml.
"""
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import ollama
from pydantic import BaseModel, Field

from config import (
    APP_DIR, DATA_DIR, OLLAMA_ENDPOINT, OLLAMA_TIMEOUT,
    get_tuning, extraction_model, extraction_options,
)

logger = logging.getLogger(__name__)

# Lazy-loaded globals for embedding model and FAISS index
_embed_model = None
_faiss_index = None
_onet_skills: list[dict] = []
_skill_aliases: dict[str, str] = {}


# --- Pydantic schemas for structured LLM output ---

class ExtractedSkill(BaseModel):
    """A single skill extracted by the LLM."""
    skill_name: str = Field(description="The skill as stated or implied in the text")
    confidence: float = Field(description="0.0-1.0 confidence this is a real skill", ge=0.0, le=1.0)
    evidence: str = Field(description="Quote or paraphrase from source text supporting this extraction")
    skill_type: str = Field(description="hard_skill, soft_skill, or domain_knowledge")


class LLMExtractionResult(BaseModel):
    """Full LLM extraction output for a text section."""
    skills: list[ExtractedSkill] = Field(default_factory=list)


class NormalizedSkill(BaseModel):
    """A skill after normalization to O*NET taxonomy."""
    original_mention: str
    canonical_name: str
    onet_skill_id: str | None = None
    match_method: str  # "alias", "embedding", "llm_direct"
    similarity_score: float
    confidence: float
    skill_type: str
    evidence: str


# --- Data loading ---

def _load_onet_skills() -> list[dict]:
    """Load O*NET skill definitions from data/onet_skills.json."""
    global _onet_skills
    if _onet_skills:
        return _onet_skills
    path = DATA_DIR / "onet_skills.json"
    if not path.exists():
        logger.warning("onet_skills.json not found at %s", path)
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _onet_skills = data.get("skills", [])
    return _onet_skills


def _load_skill_aliases() -> dict[str, str]:
    """Load surface-form -> canonical skill mappings."""
    global _skill_aliases
    if _skill_aliases:
        return _skill_aliases
    path = DATA_DIR / "skill_aliases.json"
    if not path.exists():
        logger.warning("skill_aliases.json not found at %s", path)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Support both flat dict and nested {"aliases": {...}} format
    _skill_aliases = data.get("aliases", data) if isinstance(data, dict) and "aliases" in data else data
    return _skill_aliases


# --- Step 1: Dictionary/alias matching ---

def extract_by_alias(text: str) -> list[NormalizedSkill]:
    """Fast exact/fuzzy matching against known skill aliases.
    Catches abbreviations like 'ML', 'PM', 'SQL' and common phrasings.
    """
    aliases = _load_skill_aliases()
    onet_skills = _load_onet_skills()
    text_lower = text.lower()
    found: list[NormalizedSkill] = []
    seen_canonical: set[str] = set()

    # Check aliases (exact substring match, case-insensitive)
    for alias, canonical in aliases.items():
        if canonical.lower() in seen_canonical:
            continue
        # Word-boundary-aware matching
        alias_lower = alias.lower()
        pos = text_lower.find(alias_lower)
        if pos == -1:
            continue
        # Basic word boundary check
        before = text_lower[pos - 1] if pos > 0 else " "
        after = text_lower[pos + len(alias_lower)] if pos + len(alias_lower) < len(text_lower) else " "
        if before.isalnum() or after.isalnum():
            # Only skip for very short aliases (2 chars) to avoid false positives
            if len(alias_lower) <= 2:
                continue

        # Find O*NET skill ID if available
        onet_id = None
        for skill in onet_skills:
            if skill["skill_name"].lower() == canonical.lower():
                onet_id = skill.get("skill_id")
                break

        found.append(NormalizedSkill(
            original_mention=alias,
            canonical_name=canonical,
            onet_skill_id=onet_id,
            match_method="alias",
            similarity_score=1.0,
            confidence=0.95,
            skill_type="hard_skill",  # aliases are typically hard skills
            evidence=f"Matched alias '{alias}' in text",
        ))
        seen_canonical.add(canonical.lower())

    return found


# --- Step 2: LLM-based extraction ---

EXTRACTION_PROMPT = """You are a skill extraction engine for MBA career documents.

Extract all skills (hard skills, soft skills, domain knowledge) from the following text. The text may contain multiple sections from a resume and/or LinkedIn profile.

Include both explicit skills (directly stated) and implicit skills (demonstrated through actions/context).

For each skill, provide:
- skill_name: the skill as stated or implied
- confidence: 0.0-1.0 how confident you are this is a real, distinct skill
- evidence: a brief quote or paraphrase from the text
- skill_type: "hard_skill", "soft_skill", or "domain_knowledge"

IMPORTANT: Deduplicate skills across sections. If the same skill appears in multiple sections, include it only once with the strongest evidence.

Return ONLY valid JSON matching this schema:
{
  "skills": [
    {
      "skill_name": "string",
      "confidence": 0.0,
      "evidence": "string",
      "skill_type": "string"
    }
  ]
}

TEXT TO ANALYZE:
"""


def extract_by_llm(text: str, max_skills: int | None = None) -> list[ExtractedSkill]:
    """Use Qwen 7B to extract skills from text, including implicit ones.

    Args:
        text: Resume/LinkedIn section text
        max_skills: Override max skills per section (from tuning.yaml if None)

    Returns:
        List of ExtractedSkill objects
    """
    if max_skills is None:
        max_skills = get_tuning("skill_extraction", "max_skills_per_section") or 25
    min_confidence = get_tuning("skill_extraction", "llm_extraction_min_confidence") or 0.60

    prompt = EXTRACTION_PROMPT + text

    try:
        response = ollama.chat(
            model=extraction_model(),
            messages=[{"role": "user", "content": prompt}],
            format=LLMExtractionResult.model_json_schema(),
            options=extraction_options({"num_predict": get_tuning("skill_extraction", "extraction_num_predict") or 2048}),
        )
        content = response["message"]["content"]
        result = LLMExtractionResult.model_validate_json(content)

        # Filter by confidence threshold and cap count
        filtered = [s for s in result.skills if s.confidence >= min_confidence]
        return filtered[:max_skills]

    except Exception as e:
        logger.error("LLM skill extraction failed: %s", e)
        return []


# --- Step 3: Embedding-based normalization ---

def _embed_texts(texts: list[str]) -> np.ndarray:
    """Embed texts using Ollama's nomic-embed-text (or configured model).
    Returns L2-normalized embeddings as float32 numpy array.
    """
    model_name = get_tuning("models", "embedding_model") or "nomic-embed-text"
    response = ollama.embed(model=model_name, input=texts)
    embeddings = np.array(response["embeddings"], dtype=np.float32)
    # L2 normalize so inner product = cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return embeddings / norms


def _get_faiss_index():
    """Build FAISS index over O*NET skill names + descriptions."""
    global _faiss_index
    if _faiss_index is not None:
        return _faiss_index

    import faiss

    onet_skills = _load_onet_skills()
    if not onet_skills:
        return None

    # Embed skill names + descriptions for richer matching
    texts = [
        f"{s['skill_name']}: {s.get('description', '')}"
        for s in onet_skills
    ]
    embeddings = _embed_texts(texts)

    dim = embeddings.shape[1]
    _faiss_index = faiss.IndexFlatIP(dim)  # Inner product = cosine for normalized vectors
    _faiss_index.add(embeddings)
    return _faiss_index


def normalize_to_onet(
    extracted_skills: list[ExtractedSkill],
    already_matched: set[str] | None = None,
) -> list[NormalizedSkill]:
    """Normalize LLM-extracted skills to O*NET taxonomy via embedding similarity.

    Args:
        extracted_skills: Skills from LLM extraction
        already_matched: Canonical names already found by alias matching (skip duplicates)

    Returns:
        List of NormalizedSkill with O*NET IDs and similarity scores
    """
    if already_matched is None:
        already_matched = set()

    threshold = get_tuning("skill_extraction", "onet_match_threshold") or 0.70
    onet_skills = _load_onet_skills()
    index = _get_faiss_index()

    if not onet_skills or index is None:
        # Fallback: return skills without normalization
        return [
            NormalizedSkill(
                original_mention=s.skill_name,
                canonical_name=s.skill_name,
                onet_skill_id=None,
                match_method="llm_direct",
                similarity_score=0.0,
                confidence=s.confidence,
                skill_type=s.skill_type,
                evidence=s.evidence,
            )
            for s in extracted_skills
        ]

    results: list[NormalizedSkill] = []

    # Filter out already-matched skills before embedding
    to_embed: list[ExtractedSkill] = []
    for skill in extracted_skills:
        if skill.skill_name.lower() not in already_matched:
            to_embed.append(skill)

    if not to_embed:
        return results

    # Batch embed all skill mentions in one call (instead of N sequential calls)
    skill_names = [s.skill_name for s in to_embed]
    query_embeddings = _embed_texts(skill_names)

    # Batch search FAISS index
    scores, indices = index.search(query_embeddings, k=1)

    for i, skill in enumerate(to_embed):
        best_score = float(scores[i][0])
        best_idx = int(indices[i][0])

        if best_score >= threshold:
            matched_onet = onet_skills[best_idx]
            canonical = matched_onet["skill_name"]

            if canonical.lower() in already_matched:
                continue

            results.append(NormalizedSkill(
                original_mention=skill.skill_name,
                canonical_name=canonical,
                onet_skill_id=matched_onet.get("skill_id"),
                match_method="embedding",
                similarity_score=best_score,
                confidence=skill.confidence,
                skill_type=skill.skill_type,
                evidence=skill.evidence,
            ))
            already_matched.add(canonical.lower())
        else:
            # Below threshold: keep as-is without O*NET mapping
            results.append(NormalizedSkill(
                original_mention=skill.skill_name,
                canonical_name=skill.skill_name,
                onet_skill_id=None,
                match_method="llm_direct",
                similarity_score=best_score,
                confidence=skill.confidence,
                skill_type=skill.skill_type,
                evidence=skill.evidence,
            ))

    return results


# --- Step 4: Skill inference against taxonomy ---

INFERENCE_PROMPT = """You are a skill assessment engine. Given a candidate's full professional text and a checklist of skills, determine which skills the candidate DEMONSTRATES through their experiences, even if not explicitly stated.

For each skill on the checklist, evaluate whether the candidate's text provides evidence they possess it. Only include skills where you find clear evidence.

Requirements:
- confidence must be >= 0.6 to include
- evidence must be a specific quote or paraphrase from the text (not generic)
- Do NOT infer skills without textual support

Return ONLY valid JSON:
{
  "inferred_skills": [
    {
      "skill_name": "exact skill name from checklist",
      "confidence": 0.0,
      "evidence": "specific quote or paraphrase from the text"
    }
  ]
}

--- SKILL CHECKLIST ---
%s

--- CANDIDATE TEXT ---
%s
"""


def _load_taxonomy_skill_names() -> list[str]:
    """Load all unique required/preferred skill names from role_taxonomy.json."""
    path = DATA_DIR / "role_taxonomy.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    roles = data.get("roles", data) if isinstance(data, dict) else data
    skills: set[str] = set()
    for role in roles:
        for s in role.get("required_skills", []):
            skills.add(s)
        for s in role.get("preferred_skills", []):
            skills.add(s)
    return sorted(skills)


def infer_skills_against_taxonomy(
    full_text: str,
    already_extracted: set[str] | None = None,
) -> list[NormalizedSkill]:
    """Infer skills from full resume+LinkedIn text by checking against taxonomy checklist.

    This catches skills the candidate demonstrates but doesn't explicitly state
    (e.g., competitive intelligence, cross-functional leadership, research).

    Args:
        full_text: Concatenated resume + LinkedIn text
        already_extracted: Canonical skill names already found (to avoid duplicates)

    Returns:
        List of NormalizedSkill with match_method="inferred"
    """
    if not get_tuning("skill_extraction", "inference_enabled"):
        return []

    if already_extracted is None:
        already_extracted = set()

    taxonomy_skills = _load_taxonomy_skill_names()
    if not taxonomy_skills:
        logger.warning("No taxonomy skills found for inference")
        return []

    # Only check skills not already extracted
    uncovered = [s for s in taxonomy_skills if s.lower() not in already_extracted]
    if not uncovered:
        return []

    checklist_str = "\n".join(f"- {s}" for s in uncovered)

    # Truncate text to fit context window (leave room for prompt + response)
    max_text_chars = get_tuning("skill_extraction", "max_context_chars") or 12000
    text_for_inference = full_text[:max_text_chars]

    prompt = INFERENCE_PROMPT % (checklist_str, text_for_inference)

    try:
        response = ollama.chat(
            model=extraction_model(),
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options=extraction_options({"num_predict": get_tuning("skill_extraction", "inference_num_predict") or 2048}),
        )
        content = response["message"]["content"]
        data = json.loads(content)
        inferred = data.get("inferred_skills", [])

        # Load O*NET skills for ID lookup
        onet_skills = _load_onet_skills()
        onet_by_name = {s["skill_name"].lower(): s for s in onet_skills}

        results: list[NormalizedSkill] = []
        for item in inferred:
            name = item.get("skill_name", "")
            confidence = item.get("confidence", 0.0)
            evidence = item.get("evidence", "")

            if confidence < 0.6 or not name:
                continue
            if name.lower() in already_extracted:
                continue

            # Look up O*NET ID
            onet_entry = onet_by_name.get(name.lower())
            onet_id = onet_entry.get("skill_id") if onet_entry else None

            results.append(NormalizedSkill(
                original_mention=name,
                canonical_name=name,
                onet_skill_id=onet_id,
                match_method="inferred",
                similarity_score=1.0 if onet_entry else 0.0,
                confidence=confidence,
                skill_type="hard_skill",
                evidence=evidence,
            ))
            already_extracted.add(name.lower())

        return results

    except Exception as e:
        logger.error("Skill inference failed: %s", e)
        return []


# --- Full pipeline ---

def extract_and_normalize(
    sections: dict[str, str],
) -> dict[str, list[NormalizedSkill]]:
    """Run the full skill extraction + normalization pipeline.

    Batches all text into a single LLM extraction call (instead of one per section)
    to minimize Ollama round-trips. Alias matching still runs per-section (fast).

    Args:
        sections: Dict of section_name -> text (from parsers.py output)

    Returns:
        Dict with "_alias" key for alias-matched skills and "_llm" key for
        LLM-extracted + normalized skills. Legacy per-section keys omitted
        since batching merges sections.
    """
    all_results: dict[str, list[NormalizedSkill]] = {}
    global_matched: set[str] = set()

    # Step 1: Alias matching across all sections (fast, exact)
    all_alias_skills: list[NormalizedSkill] = []
    for section_name, text in sections.items():
        if not text or len(text.strip()) < 20:
            continue
        alias_skills = extract_by_alias(text)
        for s in alias_skills:
            if s.canonical_name.lower() not in global_matched:
                global_matched.add(s.canonical_name.lower())
                all_alias_skills.append(s)

    all_results["_alias"] = all_alias_skills

    # Step 2: Concatenate all section text for a single LLM extraction call
    combined_parts: list[str] = []
    for section_name, text in sections.items():
        if not text or len(text.strip()) < 20:
            continue
        combined_parts.append(f"[{section_name}]\n{text}")

    combined_text = "\n\n".join(combined_parts)

    if combined_text.strip():
        # One LLM call with all text (instead of N calls per section)
        # Use a higher skill cap since we're extracting from the full document
        max_skills_total = (get_tuning("skill_extraction", "max_skills_per_section") or 25) * 3
        llm_skills = extract_by_llm(combined_text, max_skills=max_skills_total)

        # Step 3: Normalize all LLM extractions to O*NET in one batch
        normalized = normalize_to_onet(llm_skills, already_matched=global_matched)
        all_results["_llm"] = normalized

        for s in normalized:
            global_matched.add(s.canonical_name.lower())
    else:
        all_results["_llm"] = []

    return all_results


def get_flat_skills(
    section_skills: dict[str, list[NormalizedSkill]],
) -> list[NormalizedSkill]:
    """Flatten section-keyed skills into a deduplicated list, sorted by confidence."""
    seen: set[str] = set()
    flat: list[NormalizedSkill] = []
    for skills in section_skills.values():
        for skill in skills:
            key = skill.canonical_name.lower()
            if key not in seen:
                seen.add(key)
                flat.append(skill)
    flat.sort(key=lambda s: s.confidence, reverse=True)
    return flat
