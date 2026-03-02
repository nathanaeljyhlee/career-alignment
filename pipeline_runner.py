"""CLI helper for partial/cached pipeline runs.

Example:
  python pipeline_runner.py \
    --resume fixtures/sample_resume.pdf \
    --why-text "I want to pivot to product" \
    --use-cache --cache-key my-profile --start-stage input_processing
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from engine import run_pipeline


def _build_cache_key(args: argparse.Namespace) -> str:
    raw = {
        "resume_path": args.resume,
        "linkedin_path": args.linkedin,
        "mba_year": args.mba_year,
        "why_text": args.why_text or "",
        "why_file": args.why_file,
    }
    encoded = json.dumps(raw, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:12]


def _load_why_text(args: argparse.Namespace) -> str:
    if args.why_file:
        return Path(args.why_file).read_text(encoding="utf-8")
    return args.why_text or ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CMF pipeline with stage-level caching.")
    parser.add_argument("--resume", default=None, help="Path to resume PDF")
    parser.add_argument("--linkedin", default=None, help="Path to LinkedIn PDF")
    parser.add_argument("--why-text", default="", help="WHY statement text")
    parser.add_argument("--why-file", default=None, help="Path to text file containing WHY statement")
    parser.add_argument("--mba-year", default="1y_internship", choices=["1y_internship", "2y_fulltime"])

    parser.add_argument("--start-stage", default="input_processing",
                        choices=["input_processing", "profile_synthesis", "role_matching"])
    parser.add_argument("--end-stage", default="role_matching",
                        choices=["input_processing", "profile_synthesis", "role_matching"])

    parser.add_argument("--use-cache", action="store_true", help="Enable stage cache read/write")
    parser.add_argument("--cache-dir", default=".cache/pipeline", help="Directory for stage cache artifacts")
    parser.add_argument("--cache-key", default=None, help="Cache namespace key; auto-generated if omitted")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cache_key = args.cache_key or _build_cache_key(args)
    why_text = _load_why_text(args)

    state = run_pipeline(
        resume_path=args.resume,
        linkedin_path=args.linkedin,
        why_text=why_text,
        mba_year=args.mba_year,
        start_stage=args.start_stage,
        end_stage=args.end_stage,
        cache_dir=args.cache_dir,
        cache_key=cache_key,
        use_cache=args.use_cache,
    )

    print("Run complete")
    print(f"  run_id: {state.run_id}")
    print(f"  cache_key: {cache_key}")
    print(f"  errors: {len(state.errors)}")
    print(f"  warnings: {len(state.warnings)}")
    print(f"  stage_timings: {state.stage_timings}")


if __name__ == "__main__":
    main()
