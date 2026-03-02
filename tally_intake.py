"""
Tally Form Intake Pipeline for CMF Engine (CMF-005)

Pulls new submissions from Tally form gD5Qll, downloads resume PDFs,
prompts for LinkedIn PDF, then runs the CMF pipeline with full TallyContext.

Usage:
    python tally_intake.py           # Process all new submissions
    python tally_intake.py --list    # List new submissions without processing
    python tally_intake.py --rerun <submission_id>  # Re-run a specific submission
"""
import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import requests

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")

from config import APP_DIR
from engine import run_pipeline, TallyContext

# --- Config ---

FORM_ID = "gD5Qll"
API_KEY_FILE = APP_DIR.parent.parent.parent.parent / "secrets" / "Tally API key.env"
INTAKE_DIR = APP_DIR / "temp" / "tally_intake"
PROCESSED_FILE = APP_DIR / "runs" / "processed_submissions.json"
TALLY_BASE = "https://api.tally.so"

MBA_YEAR_MAP = {
    "1st Year MBA: Summer internship": "1y_internship",
    "2nd Year MBA: Full-time role": "2y_fulltime",
}

# Question titles exactly as they appear in the form
Q_NAME = "Name"
Q_EMAIL = "Babson Email"
Q_RESUME = "\U0001f4c4Upload your current resume (PDF)"
Q_LINKEDIN_URL = "LinkedIn Profile"
Q_STAGE = "Which recruiting stage are you in?"
Q_VISION = "What is your long-term career goal and vision? "
Q_TARGET = "What are you currently targeting? Why?"
Q_INDUSTRY = "\U0001f3e2 What is your target industry?"
Q_GEO = "\U0001f30d Geography constraint"
Q_GEO_DETAIL = "What specific geographic constraints apply? "
Q_PRIORITIES = "Right now, you are optimizing for: (select 2)"
Q_SELF_SCORE = "How competitive do you believe you are for your target role today?"
Q_SELF_REASON = "Why do you believe this? (1\u20132 sentences)"
Q_DESIRED = "Which of the following would be most valuable in your report?"
Q_EXTRA = "Is there any information about your background, constraints, or goals that was not captured above that could improve report accuracy? "


# --- Helpers ---

def _load_api_key() -> str:
    """Load Tally API key from secrets file."""
    # Walk up from APP_DIR to find secrets/
    check = APP_DIR
    for _ in range(6):
        candidate = check / "secrets" / "Tally API key.env"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
        check = check.parent
    raise FileNotFoundError(f"Tally API key not found. Searched up from {APP_DIR}")


def _load_processed() -> set[str]:
    if PROCESSED_FILE.exists():
        data = json.loads(PROCESSED_FILE.read_text(encoding="utf-8"))
        return set(data.get("processed_ids", []))
    return set()


def _save_processed(processed_ids: set[str]):
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_FILE.write_text(
        json.dumps(
            {
                "processed_ids": sorted(processed_ids),
                "last_updated": datetime.now().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _fetch_submissions(api_key: str) -> tuple[list[dict], dict[str, tuple[str, str]]]:
    """Returns (submissions, question_map) where question_map is {id: (title, type)}."""
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(
        f"{TALLY_BASE}/forms/{FORM_ID}/submissions",
        headers=headers,
        params={"filter": "completed"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    question_map = {q["id"]: (q["title"], q["type"]) for q in data.get("questions", [])}
    return data.get("submissions", []), question_map


def _parse_submission(sub: dict, qmap: dict[str, tuple]) -> dict:
    """Parse a raw Tally submission into a flat dict keyed by question title."""
    parsed = {"_id": sub["id"], "_submitted_at": sub.get("submittedAt", "")}
    for r in sub.get("responses", []):
        qid = r.get("questionId", "")
        title, _ = qmap.get(qid, (qid, ""))
        parsed[title] = r.get("answer")
    return parsed


def _download_resume(answer, sub_id: str) -> Path | None:
    """Download resume PDF from Tally signed URL. Returns local path or None."""
    if not answer or not isinstance(answer, list):
        print("  ERROR: No resume file in submission.")
        return None

    file_info = answer[0]
    url = file_info.get("url", "")
    filename = file_info.get("name", "resume")
    mime = file_info.get("mimeType", "")

    if mime != "application/pdf":
        print(f"  WARNING: Resume is '{mime}' ({filename}), not PDF.")
        print(f"  pdfplumber cannot parse this format. Ask submitter to re-upload as PDF.")
        return None

    dest_dir = INTAKE_DIR / sub_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "resume.pdf"

    # Signed URL — no auth header needed
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    dest.write_bytes(r.content)
    print(f"  Resume: {filename} ({len(r.content):,} bytes) -> {dest.name}")
    return dest


def _prompt_linkedin(sub_id: str, name: str) -> Path | None:
    """Prompt operator to drop LinkedIn PDF and confirm."""
    dest_dir = INTAKE_DIR / sub_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "linkedin.pdf"

    print(f"\n  LinkedIn PDF needed for {name}.")
    print(f"  Drop file at: {dest}")
    print(f"  Press Enter to skip, or drop the file then press Enter.")
    try:
        input("  > ")
    except EOFError:
        pass

    if dest.exists():
        print(f"  LinkedIn PDF found ({dest.stat().st_size:,} bytes).")
        return dest
    else:
        print(f"  No LinkedIn PDF provided. Pipeline will run on resume only.")
        return None


# --- Core processor ---

def process_submission(sub: dict, qmap: dict, api_key: str, processed_ids: set) -> bool:
    """Process one submission end-to-end. Returns True if pipeline ran successfully."""
    p = _parse_submission(sub, qmap)
    sub_id = p["_id"]
    submitted_date = p.get("_submitted_at", "")[:10]

    name = p.get(Q_NAME) or "Unknown"
    email = p.get(Q_EMAIL) or ""
    linkedin_url = p.get(Q_LINKEDIN_URL) or ""

    # MBA year
    stage_raw_list = p.get(Q_STAGE)
    stage_raw = stage_raw_list[0] if isinstance(stage_raw_list, list) and stage_raw_list else ""
    mba_year = MBA_YEAR_MAP.get(stage_raw, "1y_internship")

    # Text fields
    why_text = (p.get(Q_VISION) or "").strip()
    target_role_text = (p.get(Q_TARGET) or "").strip()
    target_industry = (p.get(Q_INDUSTRY) or "").strip()

    # Geography
    geo_list = p.get(Q_GEO)
    geo_str = geo_list[0] if isinstance(geo_list, list) and geo_list else ""
    geo_detail = (p.get(Q_GEO_DETAIL) or "").strip()
    geography = f"{geo_str}: {geo_detail}".strip(": ") if geo_detail else geo_str

    # Checkboxes
    opt_list = p.get(Q_PRIORITIES)
    optimization_priorities = opt_list if isinstance(opt_list, list) else []

    desired_list = p.get(Q_DESIRED)
    desired_output = desired_list if isinstance(desired_list, list) else []

    # Self-assessment
    self_score_raw = p.get(Q_SELF_SCORE)
    try:
        self_assessment_score = int(self_score_raw) if self_score_raw is not None else None
    except (TypeError, ValueError):
        self_assessment_score = None
    self_assessment_reason = (p.get(Q_SELF_REASON) or "").strip()

    # Extra context
    extra_context = (p.get(Q_EXTRA) or "").strip()
    if extra_context.lower() in ("n/a", "none", "na", ""):
        extra_context = ""

    # Print summary
    target_preview = target_role_text[:80] + "..." if len(target_role_text) > 80 else target_role_text
    print(f"\n{'='*62}")
    print(f"  {name} ({email})")
    print(f"  Submitted: {submitted_date} | Stage: {stage_raw or 'Other'} -> {mba_year}")
    print(f"  Target:    {target_preview}")
    print(f"  Industry:  {target_industry or '(not specified)'}")
    print(f"  Geography: {geography or 'No constraint'}")
    print(f"  Optimizing for: {', '.join(optimization_priorities) or '(none selected)'}")
    print(f"  Self-score: {self_assessment_score}/10" if self_assessment_score else "  Self-score: (not provided)")
    print(f"  LinkedIn URL: {linkedin_url or '(none)'}")
    if desired_output:
        print(f"  Wants from report: {'; '.join(d[:40] for d in desired_output)}")
    print(f"{'='*62}")

    # Download resume
    resume_path = _download_resume(p.get(Q_RESUME), sub_id)
    if not resume_path:
        print(f"  SKIPPED: No valid resume PDF.")
        return False

    # Prompt for LinkedIn PDF
    linkedin_path = _prompt_linkedin(sub_id, name)

    # Build TallyContext
    tally_context = TallyContext(
        submission_id=sub_id,
        name=name,
        email=email,
        target_role_text=target_role_text,
        target_industry=target_industry,
        geography=geography,
        optimization_priorities=optimization_priorities,
        self_assessment_score=self_assessment_score,
        self_assessment_reason=self_assessment_reason,
        desired_output=desired_output,
        extra_context=extra_context,
        linkedin_url=linkedin_url,
    )

    # Run pipeline
    print(f"\n  Running CMF pipeline for {name}...")
    t0 = time.time()
    state = run_pipeline(
        resume_path=str(resume_path),
        linkedin_path=str(linkedin_path) if linkedin_path else None,
        why_text=why_text,
        mba_year=mba_year,
        tally_context=tally_context,
    )
    elapsed = time.time() - t0

    # Report errors
    if state.errors:
        print(f"\n  Pipeline errors: {state.errors}")
    if state.warnings:
        print(f"  Warnings: {state.warnings[:3]}")

    # Rename run log to include submission ID and name for traceability
    if hasattr(state, "_run_log_path") and state._run_log_path:
        old_path = Path(state._run_log_path)
        safe_name = name.lower().replace(" ", "_")[:20]
        new_name = f"{sub_id}_{safe_name}_{old_path.name}"
        new_path = old_path.parent / new_name
        try:
            old_path.rename(new_path)
            print(f"\n  Run log: {new_name}")
        except Exception:
            print(f"\n  Run log: {old_path.name}")

    print(f"  Total time: {elapsed:.0f}s")

    # Mark as processed
    processed_ids.add(sub_id)
    _save_processed(processed_ids)
    return True


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(description="CMF Engine — Tally Intake (CMF-005)")
    parser.add_argument("--list", action="store_true", help="List new submissions without processing")
    parser.add_argument("--rerun", metavar="SUB_ID", help="Re-run a specific submission by ID (ignores processed log)")
    args = parser.parse_args()

    print("CMF Engine — Tally Intake")
    print(f"Form: {FORM_ID} | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    api_key = _load_api_key()
    subs, qmap = _fetch_submissions(api_key)
    processed_ids = _load_processed()

    print(f"Total submissions: {len(subs)} | Already processed: {len(processed_ids)}")

    if args.rerun:
        target_subs = [s for s in subs if s["id"] == args.rerun]
        if not target_subs:
            print(f"Submission '{args.rerun}' not found in form.")
            return
        # Remove from processed so it re-runs
        processed_ids.discard(args.rerun)
        new_subs = target_subs

    elif args.list:
        new_subs = [s for s in subs if s["id"] not in processed_ids]
        if not new_subs:
            print("No new submissions.")
            return
        print(f"\nNew submissions ({len(new_subs)}):")
        for s in new_subs:
            p = _parse_submission(s, qmap)
            name = p.get(Q_NAME) or "Unknown"
            email = p.get(Q_EMAIL) or ""
            submitted = p.get("_submitted_at", "")[:10]
            stage_list = p.get(Q_STAGE)
            stage = stage_list[0][:25] if isinstance(stage_list, list) and stage_list else "Other"
            print(f"  {s['id']} | {name} ({email}) | {submitted} | {stage}")
        return

    else:
        new_subs = [s for s in subs if s["id"] not in processed_ids]
        if not new_subs:
            print("No new submissions to process.")
            return

    print(f"Processing {len(new_subs)} submission(s)...\n")

    success_count = 0
    for sub in new_subs:
        ok = process_submission(sub, qmap, api_key, processed_ids)
        if ok:
            success_count += 1

    print(f"\nDone. {success_count}/{len(new_subs)} processed successfully.")
    print(f"Total processed (all time): {len(processed_ids)}")


if __name__ == "__main__":
    main()
