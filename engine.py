"""
Pipeline Orchestrator for Candidate-Market Fit Engine.

Staged pipeline with explicit state and JSON schemas at each step:
  Stage 1: Input Processing (PDF parsing + skill extraction)
  Stage 2: Profile Synthesis (Agent 1 + Agent 2)
  Stage 3: Role Matching (embedding pre-match + Agent 3 + Agent 4)
  Stage 4: Output Assembly

Each stage produces a typed intermediate result. Failures are logged
and surfaced to the UI, not silently swallowed.

Full run log saved to runs/ directory after each pipeline execution.
"""
import json
import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from config import get_tuning, APP_DIR
from parsers import parse_pdf
from skills import extract_and_normalize, get_flat_skills, infer_skills_against_taxonomy, generate_transfer_labels

from agents.profile_synthesizer import synthesize_profile, CandidateProfile
from agents.motivation_extractor import extract_motivation, MotivationProfile
from agents.role_comparator import compare_roles, AggregatedRoleFit
from agents.gap_analyzer import analyze_gaps_batch, RoleGapAnalysis

from matching.embeddings import match_roles
from matching.confidence import compute_confidence_band, assess_structural_gap
from matching.skill_overlap import compute_skill_overlap
from matching.skill_graph import build_skill_graph, infer_from_graph
from analysis.cross_role import cross_role_analysis, prioritize_gaps_by_graph

logger = logging.getLogger(__name__)

RUNS_DIR = APP_DIR / "runs"


# --- Tally intake context ---

@dataclass
class TallyContext:
    """Structured context from a Tally form submission (CMF-005)."""
    submission_id: str = ""
    name: str = ""
    email: str = ""
    target_role_text: str = ""        # "What are you currently targeting? Why?"
    target_industry: str = ""          # "Target industry"
    geography: str = ""                # e.g. "No constraint" or "U.S."
    optimization_priorities: list[str] = field(default_factory=list)  # checkboxes
    self_assessment_score: int | None = None   # 1-10 linear scale
    self_assessment_reason: str = ""
    desired_output: list[str] = field(default_factory=list)  # report focus checkboxes
    extra_context: str = ""            # additional background (optional field)
    linkedin_url: str = ""             # URL string from form (not PDF)


# --- Pipeline state ---

@dataclass
class PipelineState:
    """Tracks state across pipeline stages."""
    # Inputs
    resume_path: str | None = None
    linkedin_path: str | None = None
    why_text: str = ""
    mba_year: str = "1y_internship"
    tally_context: TallyContext | None = None

    # Stage 1 outputs
    resume_parsed: dict[str, Any] | None = None
    linkedin_parsed: dict[str, Any] | None = None
    skills_by_section: dict[str, list] | None = None
    skills_flat: list[dict] | None = None

    # Stage 2 outputs
    profile: dict[str, Any] | None = None
    motivation: dict[str, Any] | None = None

    # Stage 3 outputs
    matched_roles: list[dict] | None = None
    skill_overlaps: dict[str, dict] | None = None
    fit_results: list[dict] | None = None
    gap_results: list[dict] | None = None
    confidence_results: list[dict] | None = None
    structural_gap_warning: dict | None = None
    cross_role: dict | None = None
    skill_graph: dict | None = None

    # Metadata
    stage_timings: dict[str, float] = field(default_factory=dict)
    substep_timings: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_log: list[dict] = field(default_factory=list)
    run_id: str = ""


def _log_event(state: PipelineState, event: str, data: dict | None = None):
    """Append a timestamped event to the run log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "elapsed_s": round(time.time() - state._start_time, 2) if hasattr(state, "_start_time") else 0,
        "event": event,
    }
    if data:
        entry["data"] = data
    state.run_log.append(entry)
    logger.info("[%s] %s %s", entry["elapsed_s"], event, json.dumps(data or {}, default=str)[:200])


def _timed_substep(state: PipelineState, name: str):
    """Context manager for timing a substep within a stage."""
    class Timer:
        def __init__(self):
            self.start = None
        def __enter__(self):
            self.start = time.time()
            _log_event(state, f"substep_start: {name}")
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            elapsed = round(time.time() - self.start, 2)
            state.substep_timings[name] = elapsed
            _log_event(state, f"substep_end: {name}", {"elapsed_s": elapsed})
            if exc_type:
                _log_event(state, f"substep_error: {name}", {
                    "error": str(exc_val),
                    "traceback": traceback.format_exc(),
                })
            return False  # don't suppress exceptions
    return Timer()


def _time_stage(state: PipelineState, stage_name: str):
    """Context manager for timing a full stage."""
    class Timer:
        def __init__(self):
            self.start = None
        def __enter__(self):
            self.start = time.time()
            _log_event(state, f"stage_start: {stage_name}")
            return self
        def __exit__(self, *args):
            elapsed = round(time.time() - self.start, 2)
            state.stage_timings[stage_name] = elapsed
            _log_event(state, f"stage_end: {stage_name}", {"elapsed_s": elapsed})
    return Timer()


# --- Stage 1: Input Processing ---

def stage_1_input_processing(state: PipelineState) -> PipelineState:
    """Parse PDFs and extract + normalize skills."""
    # Build skill co-occurrence graph (used for inference and gap prioritization)
    try:
        state.skill_graph = build_skill_graph()
        logger.info("Skill graph built: %d skills, %d hub skills",
                    len(state.skill_graph.get("adjacency", {})),
                    len(state.skill_graph.get("hub_skills", [])))
    except Exception as e:
        logger.warning("Skill graph build failed (non-fatal): %s", e)
        state.skill_graph = None

    with _time_stage(state, "input_processing"):
        # Parse resume
        if state.resume_path:
            with _timed_substep(state, "parse_resume"):
                try:
                    state.resume_parsed = parse_pdf(state.resume_path, "resume")
                    sections = list(state.resume_parsed.get("sections", {}).keys())
                    _log_event(state, "resume_parsed", {
                        "sections": sections,
                        "total_chars": sum(len(v) for v in state.resume_parsed.get("sections", {}).values()),
                    })
                except Exception as e:
                    state.errors.append(f"Resume parsing failed: {e}")
                    _log_event(state, "resume_parse_error", {"error": str(e)})

        # Parse LinkedIn
        if state.linkedin_path:
            with _timed_substep(state, "parse_linkedin"):
                try:
                    state.linkedin_parsed = parse_pdf(state.linkedin_path, "linkedin")
                    sections = list(state.linkedin_parsed.get("sections", {}).keys())
                    _log_event(state, "linkedin_parsed", {
                        "sections": sections,
                        "total_chars": sum(len(v) for v in state.linkedin_parsed.get("sections", {}).values()),
                    })
                except Exception as e:
                    state.errors.append(f"LinkedIn parsing failed: {e}")
                    _log_event(state, "linkedin_parse_error", {"error": str(e)})

        # Combine sections for skill extraction
        all_sections: dict[str, str] = {}
        if state.resume_parsed:
            for k, v in state.resume_parsed.get("sections", {}).items():
                all_sections[f"resume_{k}"] = v
        if state.linkedin_parsed:
            for k, v in state.linkedin_parsed.get("sections", {}).items():
                all_sections[f"linkedin_{k}"] = v

        if not all_sections:
            state.errors.append("No parseable content from any input document.")
            return state

        _log_event(state, "sections_combined", {
            "section_count": len(all_sections),
            "section_names": list(all_sections.keys()),
        })

        # Skill extraction + normalization
        with _timed_substep(state, "skill_extraction"):
            try:
                full_text = "\n\n".join(all_sections.values())
                transfer_labels = []
                with _timed_substep(state, "transfer_label_generation"):
                    transfer_labels = generate_transfer_labels(full_text)

                state.skills_by_section = {}
                raw = extract_and_normalize(all_sections, transfer_labels=transfer_labels)
                for section, skills in raw.items():
                    state.skills_by_section[section] = [s.model_dump() for s in skills]

                flat_raw = get_flat_skills(raw)
                state.skills_flat = [s.model_dump() for s in flat_raw]

                _log_event(state, "skills_extracted", {
                    "unique_skills": len(state.skills_flat),
                    "by_method": {
                        "alias": sum(1 for s in state.skills_flat if s.get("match_method") == "alias"),
                        "transfer_label": sum(1 for s in state.skills_flat if s.get("match_method") == "transfer_label"),
                        "embedding": sum(1 for s in state.skills_flat if s.get("match_method") == "embedding"),
                        "llm_direct": sum(1 for s in state.skills_flat if s.get("match_method") == "llm_direct"),
                    },
                    "top_10": [s.get("canonical_name") for s in state.skills_flat[:10]],
                })
            except Exception as e:
                state.errors.append(f"Skill extraction failed: {e}")
                _log_event(state, "skill_extraction_error", {
                    "error": str(e), "traceback": traceback.format_exc(),
                })

        # Skill inference against taxonomy (catches implied skills)
        if state.skills_flat:
            with _timed_substep(state, "skill_inference"):
                try:
                    already_found = {s.get("canonical_name", "").lower() for s in state.skills_flat}

                    inferred = infer_skills_against_taxonomy(full_text, already_found)
                    inferred_dicts = [s.model_dump() for s in inferred]
                    state.skills_flat.extend(inferred_dicts)

                    _log_event(state, "skills_inferred", {
                        "inferred_count": len(inferred_dicts),
                        "total_skills_after": len(state.skills_flat),
                        "inferred_names": [s.get("canonical_name") for s in inferred_dicts],
                    })
                except Exception as e:
                    state.warnings.append(f"Skill inference step failed (non-fatal): {e}")
                    _log_event(state, "skill_inference_error", {
                        "error": str(e), "traceback": traceback.format_exc(),
                    })

        # Graph-inferred skills (catches implied skills from co-occurrence patterns)
        if state.skills_flat and state.skill_graph:
            with _timed_substep(state, "skill_graph_inference"):
                try:
                    already_found = {s.get("canonical_name", "").lower() for s in state.skills_flat}
                    graph_min_coverage = get_tuning("skill_extraction", "graph_min_neighbor_coverage") or 0.35
                    graph_top_k = get_tuning("skill_extraction", "graph_top_k_neighbors") or 10
                    graph_inferred = infer_from_graph(already_found, state.skill_graph, min_neighbor_coverage=graph_min_coverage, top_k_neighbors=graph_top_k)

                    # Convert to NormalizedSkill-compatible dicts
                    graph_inferred_dicts = [
                        {
                            "original_mention": item["skill"],
                            "canonical_name": item["skill"],
                            "onet_skill_id": None,
                            "match_method": "graph_inferred",
                            "similarity_score": item["confidence"],
                            "confidence": item["confidence"],
                            "skill_type": "hard_skill",
                            "evidence": item["reason"],
                        }
                        for item in graph_inferred
                    ]
                    state.skills_flat.extend(graph_inferred_dicts)

                    _log_event(state, "graph_inference_complete", {
                        "graph_inferred_count": len(graph_inferred_dicts),
                        "inferred_names": [d["canonical_name"] for d in graph_inferred_dicts],
                    })
                except Exception as e:
                    state.warnings.append(f"Graph inference step failed (non-fatal): {e}")
                    _log_event(state, "graph_inference_error", {
                        "error": str(e), "traceback": traceback.format_exc(),
                    })

    return state


# --- Stage 2: Profile Synthesis ---

def stage_2_profile_synthesis(state: PipelineState) -> PipelineState:
    """Run Agent 1 (Profile Synthesizer) and Agent 2 (Motivation Extractor)."""
    with _time_stage(state, "profile_synthesis"):
        # Agent 1: Profile Synthesis
        if state.skills_flat:
            with _timed_substep(state, "agent1_profile_synthesizer"):
                try:
                    resume_sections = state.resume_parsed.get("sections") if state.resume_parsed else None
                    linkedin_sections = state.linkedin_parsed.get("sections") if state.linkedin_parsed else None

                    tc = state.tally_context
                    profile_obj = synthesize_profile(
                        state.skills_flat, resume_sections, linkedin_sections,
                        stated_target=tc.target_role_text if tc else "",
                        stated_industry=tc.target_industry if tc else "",
                    )
                    state.profile = profile_obj.model_dump()

                    _log_event(state, "agent1_complete", {
                        "clusters": len(state.profile.get("skill_clusters", [])),
                        "industries": len(state.profile.get("industry_signals", [])),
                        "coherence_score": state.profile.get("narrative_coherence_score"),
                        "coherence_band": state.profile.get("narrative_coherence_band"),
                        "years_experience": state.profile.get("years_total_experience"),
                    })
                except Exception as e:
                    state.errors.append(f"Profile synthesis (Agent 1) failed: {e}")
                    _log_event(state, "agent1_error", {
                        "error": str(e), "traceback": traceback.format_exc(),
                    })

        # Agent 2: Motivation Extraction
        if state.why_text.strip():
            with _timed_substep(state, "agent2_motivation_extractor"):
                try:
                    motivation_obj = extract_motivation(state.why_text)
                    state.motivation = motivation_obj.model_dump()

                    _log_event(state, "agent2_complete", {
                        "primary_driver": state.motivation.get("primary_driver"),
                        "secondary_driver": state.motivation.get("secondary_driver"),
                        "why_quality": state.motivation.get("why_quality"),
                        "themes": {t["dimension"]: t["score"]
                                   for t in state.motivation.get("themes", [])},
                    })
                except Exception as e:
                    state.errors.append(f"Motivation extraction (Agent 2) failed: {e}")
                    _log_event(state, "agent2_error", {
                        "error": str(e), "traceback": traceback.format_exc(),
                    })
        else:
            state.warnings.append("No WHY statement provided. Motivation-based matching will be limited.")
            _log_event(state, "agent2_skipped", {"reason": "no WHY text"})

    return state


# --- Stage 3: Role Matching ---

def stage_3_role_matching(state: PipelineState) -> PipelineState:
    """Embedding pre-match, then Agent 3 (Role Comparator) + Agent 4 (Gap Analyzer)."""
    with _time_stage(state, "role_matching"):
        if not state.profile or not state.skills_flat:
            state.errors.append("Cannot match roles: missing profile or skills data.")
            return state

        # Embedding pre-match
        with _timed_substep(state, "embedding_prematch"):
            try:
                matched = match_roles(
                    state.profile, state.skills_flat, state.motivation
                )
                state.matched_roles = matched

                _log_event(state, "embedding_prematch_complete", {
                    "roles_matched": len(matched),
                    "roles": [
                        {"id": r.get("role_id"), "name": r.get("role_name"),
                         "similarity": r.get("similarity_score")}
                        for r in matched
                    ],
                })

                if not matched:
                    state.errors.append("No roles matched above similarity threshold.")
                    return state

                best_sim = matched[0].get("similarity_score", 0)
                gap_warning = assess_structural_gap(best_sim)
                if gap_warning:
                    state.structural_gap_warning = gap_warning
                    state.warnings.append(gap_warning["message"])
                    _log_event(state, "structural_gap_warning", gap_warning)

            except Exception as e:
                state.errors.append(f"Embedding pre-match failed: {e}")
                _log_event(state, "embedding_prematch_error", {
                    "error": str(e), "traceback": traceback.format_exc(),
                })
                return state

        # Deterministic skill overlap (pre-computed anchor for LLM scoring)
        with _timed_substep(state, "skill_overlap_computation"):
            try:
                skill_overlaps: dict[str, dict] = {}
                overlap_cfg = get_tuning("skill_overlap") or {}
                readiness_adjustment_weight = overlap_cfg.get("domain_readiness_adjustment_weight", 0.20)
                readiness_adjustment_midpoint = overlap_cfg.get("domain_readiness_adjustment_midpoint", 0.50)
                min_adjustment_factor = overlap_cfg.get("domain_readiness_min_adjustment_factor", 0.80)
                max_adjustment_factor = overlap_cfg.get("domain_readiness_max_adjustment_factor", 1.20)

                _log_event(state, "skill_overlap_tuning", {
                    "domain_readiness_adjustment_weight": readiness_adjustment_weight,
                    "domain_readiness_adjustment_midpoint": readiness_adjustment_midpoint,
                    "domain_readiness_min_adjustment_factor": min_adjustment_factor,
                    "domain_readiness_max_adjustment_factor": max_adjustment_factor,
                })
                for role in state.matched_roles:
                    overlap = compute_skill_overlap(
                        state.skills_flat,
                        role,
                        candidate_profile=state.profile,
                    )

                    raw_overlap_score = overlap.get("overlap_score", 0.0)
                    domain_readiness = overlap.get("domain_readiness_composite", 1.0)
                    adjustment_factor = 1 + readiness_adjustment_weight * (
                        domain_readiness - readiness_adjustment_midpoint
                    )
                    adjustment_factor = max(min_adjustment_factor, min(max_adjustment_factor, adjustment_factor))
                    adjusted_overlap_score = raw_overlap_score * adjustment_factor

                    overlap["overlap_score_raw"] = round(raw_overlap_score, 3)
                    overlap["overlap_score"] = round(adjusted_overlap_score, 3)
                    overlap["domain_readiness_adjustment_factor"] = round(adjustment_factor, 3)
                    overlap["structural_components_raw"] = {
                        "required_component": round(
                            overlap_cfg.get("required_weight", 0.70) * overlap.get("required_coverage", 0.0), 3
                        ),
                        "preferred_component": round(
                            overlap_cfg.get("preferred_weight", 0.30) * overlap.get("preferred_coverage", 0.0), 3
                        ),
                        "domain_readiness_composite": round(domain_readiness, 3),
                        "overlap_score": round(raw_overlap_score, 3),
                    }
                    overlap["structural_components_adjusted"] = {
                        "domain_readiness_adjustment_factor": round(adjustment_factor, 3),
                        "overlap_score_adjusted": round(adjusted_overlap_score, 3),
                    }
                    skill_overlaps[role["role_id"]] = overlap
                state.skill_overlaps = skill_overlaps

                _log_event(state, "skill_overlap_complete", {
                    "roles_computed": len(skill_overlaps),
                    "summary": [
                        {
                            "role_id": rid,
                            "overlap_score": ov["overlap_score"],
                            "overlap_score_raw": ov.get("overlap_score_raw"),
                            "required_coverage": ov["required_coverage"],
                            "preferred_coverage": ov.get("preferred_coverage"),
                            "expected_signal_coverage": ov.get("expected_signal_coverage"),
                            "required_specificity_weighted_coverage": ov.get("required_specificity_weighted_coverage"),
                            "domain_readiness_composite": ov.get("domain_readiness_composite"),
                            "domain_readiness_adjustment_factor": ov.get("domain_readiness_adjustment_factor"),
                            "structural_components_raw": ov.get("structural_components_raw"),
                            "structural_components_adjusted": ov.get("structural_components_adjusted"),
                        }
                        for rid, ov in skill_overlaps.items()
                    ],
                })
            except Exception as e:
                state.warnings.append(f"Skill overlap computation failed (non-fatal): {e}")
                _log_event(state, "skill_overlap_error", {
                    "error": str(e), "traceback": traceback.format_exc(),
                })

        # Agent 3: Role Comparison (with self-consistency)
        with _timed_substep(state, "agent3_role_comparator"):
            try:
                tc = state.tally_context
                fit_results = compare_roles(
                    state.profile, state.motivation or {},
                    state.matched_roles, state.mba_year,
                    skill_overlaps=state.skill_overlaps,
                    optimization_priorities=tc.optimization_priorities if tc else None,
                )
                state.fit_results = [r.model_dump() for r in fit_results]

                _log_event(state, "agent3_complete", {
                    "roles_compared": len(state.fit_results),
                    "results": [
                        {"role": r.get("role_name"), "band": r.get("fit_band"),
                         "composite": r.get("composite_score"),
                         "confidence": r.get("confidence_band"),
                         "agreement": r.get("agreement_ratio")}
                        for r in state.fit_results
                    ],
                })
            except Exception as e:
                state.errors.append(f"Role comparison (Agent 3) failed: {e}")
                _log_event(state, "agent3_error", {
                    "error": str(e), "traceback": traceback.format_exc(),
                })
                return state

        # Agent 4: Gap Analysis
        with _timed_substep(state, "agent4_gap_analyzer"):
            try:
                gap_results = analyze_gaps_batch(
                    state.profile, state.skills_flat,
                    state.matched_roles, state.fit_results,
                    skill_overlaps=state.skill_overlaps,
                )
                state.gap_results = [r.model_dump() for r in gap_results]

                _log_event(state, "agent4_complete", {
                    "roles_analyzed": len(state.gap_results),
                    "results": [
                        {"role": r.get("role_name"),
                         "severity_band": r.get("severity_band"),
                         "composite_severity": r.get("composite_severity"),
                         "pivot_viable": r.get("pivot_viable"),
                         "gap_count": len(r.get("gaps", []))}
                        for r in state.gap_results
                    ],
                })
            except Exception as e:
                state.errors.append(f"Gap analysis (Agent 4) failed: {e}")
                _log_event(state, "agent4_error", {
                    "error": str(e), "traceback": traceback.format_exc(),
                })

        # Compute confidence bands
        if state.fit_results:
            state.confidence_results = []
            source_coverage = state.profile.get("source_coverage", {})
            for fit, role in zip(state.fit_results, state.matched_roles):
                conf = compute_confidence_band(
                    agreement_ratio=fit.get("agreement_ratio", 0),
                    embedding_similarity=role.get("similarity_score", 0),
                    source_coverage=source_coverage,
                )
                state.confidence_results.append(conf)

        # Cross-role comparative analysis
        if state.fit_results and state.gap_results:
            with _timed_substep(state, "cross_role_analysis"):
                try:
                    # Graph-informed gap prioritization (if graph available)
                    gap_results_for_cross = state.gap_results
                    if state.skill_graph and state.skills_flat:
                        candidate_skill_names = {
                            s.get("canonical_name", "").lower()
                            for s in state.skills_flat
                        }
                        gap_results_for_cross = prioritize_gaps_by_graph(
                            state.gap_results,
                            state.skill_graph,
                            candidate_skill_names,
                        )
                        state.gap_results = gap_results_for_cross

                    state.cross_role = cross_role_analysis(
                        fit_results=state.fit_results,
                        gap_results=gap_results_for_cross,
                        skill_overlaps=state.skill_overlaps or {},
                    )
                    _log_event(state, "cross_role_complete", {
                        "shared_gaps_count": len(state.cross_role.get("shared_gaps", [])),
                        "leverage_skills_count": len(state.cross_role.get("leverage_skills", [])),
                    })
                except Exception as e:
                    state.warnings.append(f"Cross-role analysis failed (non-fatal): {e}")
                    _log_event(state, "cross_role_error", {
                        "error": str(e), "traceback": traceback.format_exc(),
                    })

    return state


# --- Run log persistence ---

def _json_serializer(obj):
    """Fallback serializer for types json.dump can't handle natively."""
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def _save_run_log(state: PipelineState) -> Path:
    """Save run artifacts:
    1. Full verbose log in runs/ (timestamped, for history)
    2. Compact latest_run.json at project root (for Claude Code to read)
    """
    RUNS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"run_{timestamp}_{state.run_id}.json"
    path = RUNS_DIR / filename

    # --- Full verbose export (for download / history) ---
    full_export = {
        "run_id": state.run_id,
        "timestamp": datetime.now().isoformat(),
        "inputs": {
            "resume_path": state.resume_path,
            "linkedin_path": state.linkedin_path,
            "why_text": state.why_text,
            "mba_year": state.mba_year,
        },
        "stage_timings": state.stage_timings,
        "substep_timings": state.substep_timings,
        "errors": state.errors,
        "warnings": state.warnings,
        "results": {
            "resume_sections": list((state.resume_parsed or {}).get("sections", {}).keys()),
            "linkedin_sections": list((state.linkedin_parsed or {}).get("sections", {}).keys()),
            "skills_flat": state.skills_flat,
            "profile": state.profile,
            "motivation": state.motivation,
            "matched_roles": [
                {k: v for k, v in r.items()
                 if k not in ("required_skills", "preferred_skills", "barrier_conditions",
                              "expected_signals", "motivation_attributes")}
                for r in (state.matched_roles or [])
            ],
            "fit_results": state.fit_results,
            "gap_results": state.gap_results,
            "confidence_results": state.confidence_results,
            "structural_gap_warning": state.structural_gap_warning,
        },
        "run_log": state.run_log,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(full_export, f, indent=2, default=_json_serializer)
    logger.info("Full run log saved to %s", path)

    # --- Compact export for Claude Code (latest_run.json) ---
    # Optimized: no event log, no raw skill list, no taxonomy data.
    # Just timing, errors, agent outputs, and fit/gap results.
    compact = {
        "run_id": state.run_id,
        "timestamp": datetime.now().isoformat(),
        "mba_year": state.mba_year,
        "why_length": len(state.why_text),
        "tally_intake": {
            "submission_id": state.tally_context.submission_id,
            "name": state.tally_context.name,
            "email": state.tally_context.email,
            "target_role": state.tally_context.target_role_text,
            "target_industry": state.tally_context.target_industry,
            "optimization_priorities": state.tally_context.optimization_priorities,
            "self_assessment_score": state.tally_context.self_assessment_score,
            "desired_output": state.tally_context.desired_output,
        } if state.tally_context else None,
        "timing": {**state.stage_timings, "substeps": state.substep_timings},
        "errors": state.errors,
        "warnings": state.warnings,
        "skills_summary": {
            "total": len(state.skills_flat) if state.skills_flat else 0,
            "by_method": {
                "alias": sum(1 for s in (state.skills_flat or []) if s.get("match_method") == "alias"),
                "embedding": sum(1 for s in (state.skills_flat or []) if s.get("match_method") == "embedding"),
                "llm_direct": sum(1 for s in (state.skills_flat or []) if s.get("match_method") == "llm_direct"),
                "inferred": sum(1 for s in (state.skills_flat or []) if s.get("match_method") == "inferred"),
                "graph_inferred": sum(1 for s in (state.skills_flat or []) if s.get("match_method") == "graph_inferred"),
            },
            "top_skills": [
                {"name": s.get("canonical_name"), "type": s.get("skill_type"),
                 "confidence": s.get("confidence"), "method": s.get("match_method")}
                for s in (state.skills_flat or [])[:20]
            ],
        },
        "profile": state.profile,
        "motivation": state.motivation,
        "embedding_prematch": [
            {"role_id": r.get("role_id"), "role_name": r.get("role_name"),
             "similarity": r.get("similarity_score")}
            for r in (state.matched_roles or [])
        ],
        "skill_overlaps": state.skill_overlaps,
        "fit_results": state.fit_results,
        "gap_results": state.gap_results,
        "confidence_results": state.confidence_results,
        "cross_role": state.cross_role,
        "skill_graph_stats": {
            "total_skills_in_graph": len((state.skill_graph or {}).get("adjacency", {})),
            "hub_skills": (state.skill_graph or {}).get("hub_skills", []),
            "clusters_found": len((state.skill_graph or {}).get("clusters", [])),
            "graph_inferred_skills": sum(
                1 for s in (state.skills_flat or [])
                if s.get("match_method") == "graph_inferred"
            ),
        } if state.skill_graph else None,
    }

    latest_path = APP_DIR / "latest_run.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(compact, f, indent=2, default=_json_serializer)
    logger.info("Compact run log saved to %s", latest_path)

    return path


# --- Full pipeline ---

def run_pipeline(
    resume_path: str | None = None,
    linkedin_path: str | None = None,
    why_text: str = "",
    mba_year: str = "1y_internship",
    tally_context: TallyContext | None = None,
    progress_callback=None,
) -> PipelineState:
    """Run the full Candidate-Market Fit Engine pipeline.

    Args:
        resume_path: Path to resume PDF
        linkedin_path: Path to LinkedIn PDF export
        why_text: Free-text WHY statement
        mba_year: "1y_internship" or "2y_fulltime"
        tally_context: Optional structured context from Tally intake (CMF-005)
        progress_callback: Optional callable(stage_name, pct) for UI updates

    Returns:
        PipelineState with all intermediate and final results
    """
    state = PipelineState(
        resume_path=resume_path,
        linkedin_path=linkedin_path,
        why_text=why_text,
        mba_year=mba_year,
        tally_context=tally_context,
    )
    state.run_id = datetime.now().strftime("%H%M%S")
    state._start_time = time.time()

    _log_event(state, "pipeline_start", {
        "has_resume": resume_path is not None,
        "has_linkedin": linkedin_path is not None,
        "why_length": len(why_text),
        "mba_year": mba_year,
    })

    stages = [
        ("Input Processing", stage_1_input_processing, 0.25),
        ("Profile Synthesis", stage_2_profile_synthesis, 0.50),
        ("Role Matching", stage_3_role_matching, 1.00),
    ]

    for stage_name, stage_fn, pct in stages:
        if progress_callback:
            progress_callback(stage_name, pct)

        state = stage_fn(state)

        # Check for fatal errors (no point continuing)
        if state.errors and stage_name == "Input Processing" and not state.skills_flat:
            _log_event(state, "pipeline_abort", {"reason": "no skills extracted"})
            break

    total_time = round(time.time() - state._start_time, 2)
    state.stage_timings["total"] = total_time

    _log_event(state, "pipeline_complete", {
        "total_time_s": total_time,
        "error_count": len(state.errors),
        "warning_count": len(state.warnings),
        "stage_timings": state.stage_timings,
        "substep_timings": state.substep_timings,
    })

    # Auto-save run log
    try:
        state._run_log_path = str(_save_run_log(state))
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("Failed to save run log: %s\n%s", e, tb)
        state.warnings.append(f"Run log save failed: {e}")
        state._run_log_path = None

    return state
