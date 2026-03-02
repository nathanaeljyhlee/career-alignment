"""
Candidate-Market Fit Engine — Streamlit UI

Upload resume + LinkedIn PDF, provide WHY statement, get role matching results.
Runs entirely locally via Ollama (Qwen 7B).
"""
import json
import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from engine import run_pipeline, PipelineState
from output import build_output
from config import get_tuning, OLLAMA_ENDPOINT, APP_DIR

# Configure logging to terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

RUNS_DIR = APP_DIR / "runs"

# --- Page config ---
st.set_page_config(
    page_title="Candidate-Market Fit Engine",
    page_icon="*",
    layout="wide",
)


# --- Ollama health check ---
def check_ollama() -> bool:
    try:
        import urllib.request
        req = urllib.request.Request(f"{OLLAMA_ENDPOINT}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_available_models() -> list[str]:
    try:
        import urllib.request
        req = urllib.request.Request(f"{OLLAMA_ENDPOINT}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


# --- Sidebar ---
with st.sidebar:
    st.title("Settings")

    ollama_running = check_ollama()
    if ollama_running:
        st.success("Ollama: Connected")
        available = get_available_models()
        models_cfg = get_tuning("models") or {}
        extraction = models_cfg.get("extraction_model", "qwen2.5:7b")
        reasoning = models_cfg.get("reasoning_model", "qwen2.5:7b")

        extraction_ok = any(extraction in m for m in available)
        reasoning_ok = any(reasoning in m for m in available)

        if extraction_ok:
            st.success(f"Extraction: {extraction}")
        else:
            st.error(f"Missing: {extraction}")
            st.code(f"ollama pull {extraction}", language="bash")

        if reasoning_ok:
            st.success(f"Reasoning: {reasoning}")
        else:
            st.error(f"Missing: {reasoning}")
            st.code(f"ollama pull {reasoning}", language="bash")
    else:
        st.error("Ollama: Not running")
        st.info("Start Ollama with `ollama serve` or the desktop app.")

    show_debug = st.checkbox("Show debug info", value=False)

    # Previous runs
    st.divider()
    st.caption("Previous Runs")
    if RUNS_DIR.exists():
        run_files = sorted(RUNS_DIR.glob("run_*.json"), reverse=True)
        if run_files:
            selected_run = st.selectbox(
                "Load previous run",
                options=["(current)"] + [f.name for f in run_files],
            )
            if selected_run != "(current)" and st.button("Load"):
                run_path = RUNS_DIR / selected_run
                with open(run_path, "r", encoding="utf-8") as f:
                    st.session_state["loaded_run"] = json.load(f)
                st.rerun()
        else:
            st.caption("No previous runs yet.")

# --- Main UI ---
st.title("Candidate-Market Fit Engine")
st.caption("Upload your resume and LinkedIn, tell us your WHY, and discover your best-fit roles.")

col1, col2 = st.columns(2)

with col1:
    resume_file = st.file_uploader(
        "Resume (PDF)", type=["pdf"], key="resume",
        help="Your current resume in PDF format",
    )

with col2:
    linkedin_file = st.file_uploader(
        "LinkedIn Export (PDF)", type=["pdf"], key="linkedin",
        help="Export your LinkedIn profile as PDF (optional but recommended)",
    )

st.divider()
mba_year = st.radio(
    "Which MBA track are you on?",
    options=["1y_internship", "2y_fulltime"],
    format_func=lambda x: "1-Year MBA — Internship Search" if x == "1y_internship" else "2-Year MBA — Full-time Search",
    horizontal=True,
    help=(
        "This changes how structural skills vs. motivation alignment are weighted. "
        "Internship: 65% skills / 35% motivation. Full-time: 50% / 50%. "
        "Getting this wrong will shift all your fit scores."
    ),
)
st.divider()

why_text = st.text_area(
    "WHY Statement",
    placeholder=(
        "Why do you want the roles you're targeting? What drives you? "
        "What kind of impact do you want to make? Be specific - this helps "
        "the engine understand your motivations beyond your resume."
    ),
    height=150,
    help="Minimum 200 characters for best results. Be honest about what drives you.",
)

# Character count feedback
if why_text:
    min_len = get_tuning("motivation_extraction", "min_why_length") or 200
    char_count = len(why_text.strip())
    if char_count < min_len:
        st.warning(f"WHY statement is {char_count} characters (minimum {min_len} for reliable analysis)")
    else:
        st.success(f"WHY statement: {char_count} characters")

# --- Run pipeline ---
can_run = resume_file is not None
if not ollama_running:
    can_run = False

if st.button("Analyze My Fit", type="primary", disabled=not can_run, use_container_width=True):
    # Save uploaded files to temp paths
    resume_path = None
    linkedin_path = None

    if resume_file:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(resume_file.getbuffer())
        tmp.close()
        resume_path = tmp.name

    if linkedin_file:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(linkedin_file.getbuffer())
        tmp.close()
        linkedin_path = tmp.name

    # Live progress display
    progress_bar = st.progress(0, text="Starting pipeline...")
    timing_display = st.empty()
    stage_times: dict[str, str] = {}

    import time as _time
    _timer = {"stage_start": _time.time()}  # mutable container for closure

    def update_progress(stage_name: str, pct: float):
        # Record previous stage time
        if stage_times:
            last_stage = list(stage_times.keys())[-1]
            if stage_times[last_stage] == "running...":
                stage_times[last_stage] = f"{_time.time() - _timer['stage_start']:.1f}s"

        stage_times[stage_name] = "running..."
        _timer["stage_start"] = _time.time()
        progress_bar.progress(pct, text=f"Stage: {stage_name}...")

        # Update timing display
        lines = [f"  {k}: {v}" for k, v in stage_times.items()]
        timing_display.code("PIPELINE TIMING\n" + "\n".join(lines), language="text")

    # Run
    state = run_pipeline(
        resume_path=resume_path,
        linkedin_path=linkedin_path,
        why_text=why_text,
        mba_year=mba_year,
        progress_callback=update_progress,
    )

    progress_bar.progress(1.0, text="Complete!")

    # Final timing display
    timing_lines = []
    for stage, elapsed in state.stage_timings.items():
        timing_lines.append(f"  {stage}: {elapsed:.1f}s")
    if state.substep_timings:
        timing_lines.append("\n  SUBSTEPS:")
        for substep, elapsed in state.substep_timings.items():
            timing_lines.append(f"    {substep}: {elapsed:.1f}s")
    timing_display.code("PIPELINE TIMING\n" + "\n".join(timing_lines), language="text")

    # Build output
    output = build_output(
        profile=state.profile,
        motivation=state.motivation,
        fit_results=state.fit_results,
        gap_results=state.gap_results,
        confidence_results=state.confidence_results,
        matched_roles=state.matched_roles,
        skills_flat=state.skills_flat,
        structural_gap_warning=state.structural_gap_warning,
        errors=state.errors,
        warnings=state.warnings,
        stage_timings=state.stage_timings,
        cross_role=getattr(state, "cross_role", None),
    )

    # Store in session state
    st.session_state["output"] = output
    st.session_state["state"] = state
    st.session_state["run_log_path"] = getattr(state, "_run_log_path", None)

# --- Results display ---
if "output" in st.session_state:
    output = st.session_state["output"]

    # Download / export button -- always available when results exist
    run_log_path = st.session_state.get("run_log_path")
    log_data = None
    log_filename = None

    if run_log_path and Path(run_log_path).exists():
        with open(run_log_path, "r", encoding="utf-8") as f:
            log_data = f.read()
        log_filename = Path(run_log_path).name
    else:
        # Build export from current session state (covers stale/old runs)
        state = st.session_state.get("state")
        export = {
            "timestamp": datetime.now().isoformat(),
            "note": "Exported from session state (no saved run log)",
            "output": output,
        }
        if state:
            export["stage_timings"] = getattr(state, "stage_timings", {})
            export["substep_timings"] = getattr(state, "substep_timings", {})
            export["errors"] = getattr(state, "errors", [])
            export["warnings"] = getattr(state, "warnings", [])
            export["results"] = {
                "skills_flat": getattr(state, "skills_flat", None),
                "profile": getattr(state, "profile", None),
                "motivation": getattr(state, "motivation", None),
                "fit_results": getattr(state, "fit_results", None),
                "gap_results": getattr(state, "gap_results", None),
                "confidence_results": getattr(state, "confidence_results", None),
            }
            export["run_log"] = getattr(state, "run_log", [])
        log_data = json.dumps(export, indent=2, default=str)
        log_filename = f"run_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    col_json, col_pdf = st.columns(2)

    with col_json:
        st.download_button(
            "Download Full Run Log (JSON)",
            data=log_data,
            file_name=log_filename,
            mime="application/json",
            use_container_width=True,
        )

    with col_pdf:
        try:
            from pdf_export import generate_pdf
            pdf_bytes = generate_pdf(output)
            pdf_filename = f"cmf_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            st.download_button(
                "Download PDF Report",
                data=pdf_bytes,
                file_name=pdf_filename,
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )
        except ImportError:
            st.info("Install reportlab to enable PDF export: `pip install reportlab`")
        except Exception as _pdf_err:
            st.warning(f"PDF generation failed: {_pdf_err}")

    if run_log_path and Path(run_log_path).exists():
        st.caption(f"Auto-saved: {run_log_path}")
    elif run_log_path is None:
        st.warning("Run log was NOT saved to disk. Check terminal for errors.")

    # Errors and warnings
    if output["metadata"]["errors"]:
        for err in output["metadata"]["errors"]:
            st.error(err)

    if output["metadata"]["warnings"]:
        for warn in output["metadata"]["warnings"]:
            st.warning(warn)

    # Section 1: Candidate Snapshot
    snap = output["section_1_snapshot"]
    if snap.get("available"):
        st.header("1. Candidate Snapshot")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Experience", f"{snap.get('years_experience', 0):.0f} years")
        with col2:
            coherence = snap.get("narrative_coherence", "N/A")
            st.metric("Narrative Coherence", coherence.title() if isinstance(coherence, str) else "N/A")
        with col3:
            st.metric("Education", snap.get("highest_education", "N/A"))

        st.write(snap.get("narrative_summary", ""))

        if snap.get("primary_driver"):
            st.write(f"**Primary Driver:** {snap['primary_driver'].replace('_', ' ').title()}")
            st.write(f"**Secondary Driver:** {snap.get('secondary_driver', '').replace('_', ' ').title()}")
            if snap.get("motivation_summary"):
                st.write(f"*{snap['motivation_summary']}*")

    # Section 2: Skill Profile
    skills_section = output["section_2_skills"]
    if skills_section.get("available"):
        st.header("2. Skill Profile")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Skills", skills_section["total_skills"])
        with col2:
            st.metric("O*NET Matched", skills_section["onet_matched"])
        with col3:
            st.metric("Novel/Unmatched", skills_section["unmatched"])

        if skills_section.get("clusters"):
            for cluster in skills_section["clusters"]:
                with st.expander(
                    f"{cluster.get('cluster_name', 'Cluster')} ({cluster.get('strength', '').title()})"
                ):
                    st.write(", ".join(cluster.get("skills", [])))
                    st.caption(cluster.get("evidence_summary", ""))

        # Show top skills list
        if skills_section.get("top_skills"):
            with st.expander("Top Skills (by confidence)"):
                for s in skills_section["top_skills"]:
                    st.write(f"- **{s['name']}** ({s['type']}) -- {s['confidence']:.0%}")

    # --- CMF-006: Skill Extraction Observability ---
    _obs_state = st.session_state.get("state")
    _skills_flat = getattr(_obs_state, "skills_flat", None) if _obs_state else None
    if _skills_flat:
        METHOD_META = {
            "alias":        ("green",  "Exact match — skill surface form found directly in alias dictionary"),
            "llm":          ("blue",   "AI extracted — LLM identified this skill from context in your text"),
            "llm_direct":   ("blue",   "AI extracted — LLM identified this skill from context in your text"),
            "embedding":    ("blue",   "Embedding match — LLM skill normalized to O*NET via semantic similarity"),
            "inferred":     ("orange", "Inferred — skill demonstrated through actions but not explicitly stated"),
            "graph_inferred": ("red",  "Graph inferred — skill implied by proximity to other extracted skills in the skill graph"),
        }
        counts: dict[str, int] = {}
        for sk in _skills_flat:
            m = sk.get("match_method", "unknown")
            counts[m] = counts.get(m, 0) + 1

        summary_parts = [f"{v} {k}" for k, v in counts.items()]
        summary_line = f"{len(_skills_flat)} skills extracted from your resume. Methods: {', '.join(summary_parts)}"

        with st.expander("How your skills were extracted", expanded=False):
            st.caption(summary_line)

            # Group skills by method
            from collections import defaultdict
            by_method: dict[str, list[dict]] = defaultdict(list)
            for sk in _skills_flat:
                by_method[sk.get("match_method", "unknown")].append(sk)

            # Display in a consistent order
            method_order = ["alias", "llm_direct", "llm", "embedding", "inferred", "graph_inferred"]
            import pandas as pd
            displayed = set()
            for method in method_order + [m for m in by_method if m not in method_order]:
                if method not in by_method or method in displayed:
                    continue
                displayed.add(method)
                color, description = METHOD_META.get(method, ("gray", "Unknown extraction method"))
                skills_in_group = by_method[method]
                label = method.replace("_", " ").title()
                st.markdown(f"**:{color}[{label}]** — _{description}_")
                rows = [
                    {
                        "Skill": sk.get("canonical_name", sk.get("original_mention", "")),
                        "Confidence": f"{sk.get('confidence', 0):.0%}",
                    }
                    for sk in sorted(skills_in_group, key=lambda s: s.get("confidence", 0), reverse=True)
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Dynamic section numbering — tracks next number so sections don't skip
    _section_num = 3

    # Section: Win Now Roles
    win_now = output["section_3_win_now"]
    if win_now:
        st.header(f"{_section_num}. Win Now Roles")
        _section_num += 1
        st.caption("Roles where you can compete today.")
        for entry in win_now:
            fit = entry["fit"]
            conf = entry.get("confidence") or {}
            with st.expander(
                f"{fit.get('role_name', 'Unknown')} -- "
                f"{fit.get('fit_band', '').title()} "
                f"({fit.get('composite_score', 0):.0%} fit, "
                f"{conf.get('band', 'N/A')} confidence)"
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Structural Fit", f"{fit.get('structural_fit_score', 0):.0%}")
                with col2:
                    st.metric("Motivation Alignment", f"{fit.get('motivation_alignment_score', 0):.0%}")
                st.write(fit.get("reasoning", ""))

                # Evidence details
                if fit.get("evidence"):
                    for ev in fit["evidence"]:
                        dim = ev.get("dimension", "").replace("_", " ").title()
                        st.write(f"**{dim}** (score: {ev.get('score', 0):.0%})")
                        # Support both evidence_chain (new) and supporting/gaps (legacy)
                        if ev.get("evidence_chain"):
                            for item in ev["evidence_chain"]:
                                prefix = "+" if item.get("direction") == "supporting" else "-"
                                impact = item.get("score_impact", "")
                                st.write(f"  {prefix} [{impact}] {item.get('claim', '')}")
                                st.caption(f"    Source: {item.get('source', '')}")
                        else:
                            if ev.get("supporting"):
                                for point in ev["supporting"]:
                                    st.write(f"  + {point}")
                            if ev.get("gaps"):
                                for gap in ev["gaps"]:
                                    st.write(f"  - {gap}")

                if entry.get("gap") and entry["gap"].get("gaps"):
                    st.write("**Key Gaps:**")
                    for gap in entry["gap"]["gaps"][:3]:
                        st.write(f"- {gap.get('description', '')} ({gap.get('addressability', '')})")

    elif not output["metadata"]["errors"]:
        st.header(f"{_section_num}. Win Now Roles")
        _section_num += 1
        st.info("No strong or competitive role matches found. Check the gap analysis below for improvement areas.")

    # Section: Invest to Pivot
    pivot = output["section_4_pivot"]
    if pivot:
        st.header(f"{_section_num}. Invest to Pivot Roles")
        _section_num += 1
        st.caption("Roles worth investing in if you want to pivot.")
        for entry in pivot:
            fit = entry["fit"]
            gap = entry.get("gap") or {}
            with st.expander(
                f"{fit.get('role_name', 'Unknown')} -- "
                f"{gap.get('severity_band', '').title()} gaps"
            ):
                st.write(fit.get("reasoning", ""))
                st.write(f"**Pivot Rationale:** {gap.get('pivot_rationale', '')}")
                if gap.get("top_leverage_moves"):
                    st.write("**Highest-Leverage Moves:**")
                    for i, move in enumerate(gap["top_leverage_moves"], 1):
                        st.write(f"{i}. {move}")

    # Section: Detailed Gap Analysis
    gaps = output["section_5_gaps"]
    if gaps:
        st.header(f"{_section_num}. Detailed Gap Analysis")
        _section_num += 1
        for gap_result in gaps:
            with st.expander(
                f"{gap_result.get('role_name', 'Unknown')} -- "
                f"{gap_result.get('severity_band', '').title()} severity "
                f"(composite: {gap_result.get('composite_severity', 0):.0%})"
            ):
                st.write(f"**Pivot Viable:** {'Yes' if gap_result.get('pivot_viable') else 'No'}")
                st.write(f"**Rationale:** {gap_result.get('pivot_rationale', '')}")

                for gap in gap_result.get("gaps", []):
                    severity_pct = f"{gap.get('severity', 0):.0%}"
                    st.write(
                        f"- **{gap.get('gap_type', '').replace('_', ' ').title()}** "
                        f"({severity_pct}, {gap.get('addressability', '')}): "
                        f"{gap.get('description', '')}"
                    )
                    if gap.get("leverage_move"):
                        st.caption(f"  Action: {gap['leverage_move']}")

                if gap_result.get("top_leverage_moves"):
                    st.write("**Top Leverage Moves:**")
                    for i, move in enumerate(gap_result["top_leverage_moves"], 1):
                        st.write(f"{i}. {move}")

    # Section: Strategic Decision
    strategic = output["section_6_strategic"]
    if strategic:
        st.header(f"{_section_num}. Strategic Recommendation")
        _section_num += 1
        rec = strategic.get("recommendation", "")
        if rec == "win_now":
            st.success(strategic.get("summary", ""))
        elif rec == "invest_to_pivot":
            st.info(strategic.get("summary", ""))
        elif rec == "dual_track":
            st.info(strategic.get("summary", ""))
        else:
            st.warning(strategic.get("summary", ""))

    # Section: Cross-Role Analysis
    cross = output.get("section_7_cross_role")
    if cross and cross.get("role_ranking"):
        with st.expander(f"{_section_num}. Cross-Role Analysis", expanded=True):
            _section_num += 1

            st.subheader("Role Comparison")
            for r in cross.get("role_ranking", []):
                cols = st.columns(4)
                cols[0].write(f"**{r['role_name']}**")
                cols[1].metric("Fit", f"{r['composite_score']:.0%}")
                cols[2].metric("Skill Coverage", f"{r['overlap_score']:.0%}")
                cols[3].metric("Effort to Fit", f"{r['effort_to_fit']:.2f}")

            if cross.get("leverage_skills"):
                st.subheader("Highest-Leverage Skills to Develop")
                for ls in cross["leverage_skills"]:
                    roles_str = ", ".join(ls.get("roles_unlocked", []))
                    st.write(
                        f"**{ls['skill'].title()}** — unlocks fit in: {roles_str}"
                    )
                    st.caption(f"Action: {ls.get('recommendation', '')}")

            if cross.get("shared_gaps"):
                st.subheader("Shared Gaps (Appear Across Multiple Roles)")
                for sg in cross["shared_gaps"]:
                    roles_str = ", ".join(sg.get("roles_affected", []))
                    st.write(
                        f"- **{sg['skill'].title()}** — affects {sg['leverage_multiplier']} roles "
                        f"({roles_str}) | avg severity: {sg['avg_severity']:.0%} | {sg['addressability']}"
                    )

            if cross.get("effort_ranking"):
                st.subheader("Effort-to-Fit Ranking (Lowest Effort First)")
                for er in cross["effort_ranking"]:
                    st.write(
                        f"- **{er['role_name']}**: effort={er['effort_to_fit']:.2f}, "
                        f"current fit={er['current_fit']:.0%}"
                    )

            if cross.get("comparative_narrative"):
                st.markdown(f"**Summary:** {cross['comparative_narrative']}")

    # Debug info
    if show_debug:
        st.header("Debug Info")
        state = st.session_state.get("state")
        if state:
            try:
                st.subheader("Timing")
                st.json({
                    "stage_timings": getattr(state, "stage_timings", {}),
                    "substep_timings": getattr(state, "substep_timings", {}),
                })

                st.subheader("Pipeline Summary")
                st.json({
                    "errors": getattr(state, "errors", []),
                    "warnings": getattr(state, "warnings", []),
                    "skills_count": len(getattr(state, "skills_flat", None) or []),
                    "matched_roles_count": len(getattr(state, "matched_roles", None) or []),
                    "fit_results_count": len(getattr(state, "fit_results", None) or []),
                    "gap_results_count": len(getattr(state, "gap_results", None) or []),
                })

                if getattr(state, "skills_flat", None):
                    st.subheader("Extracted Skills")
                    st.json(state.skills_flat)

                if getattr(state, "profile", None):
                    st.subheader("Profile (Agent 1 Output)")
                    st.json(state.profile)

                if getattr(state, "motivation", None):
                    st.subheader("Motivation (Agent 2 Output)")
                    st.json(state.motivation)

                if getattr(state, "fit_results", None):
                    st.subheader("Fit Results (Agent 3 Output)")
                    st.json(state.fit_results)

                if getattr(state, "gap_results", None):
                    st.subheader("Gap Results (Agent 4 Output)")
                    st.json(state.gap_results)

                if getattr(state, "run_log", None):
                    st.subheader("Full Run Log")
                    st.json(state.run_log)
            except AttributeError as e:
                st.error(f"Stale session state (missing field: {e}). Run the pipeline again to refresh.")
                del st.session_state["state"]

# --- Loaded run display ---
if "loaded_run" in st.session_state:
    st.divider()
    st.header("Loaded Previous Run")
    loaded = st.session_state["loaded_run"]
    st.json(loaded)
    if st.button("Clear loaded run"):
        del st.session_state["loaded_run"]
        st.rerun()
