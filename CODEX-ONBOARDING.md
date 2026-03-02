---
purpose: Onboarding doc for ChatGPT Codex — enough context to create PRs aligned to the roadmap without additional briefing
created: 2026-03-02
maintained_by: Claude Code (reviewer) + Codex (implementer)
repo: https://github.com/nathanaeljyhlee/career-alignment
---

# CMF Engine — Codex Onboarding

## What This Is

A local AI pipeline that takes a candidate's resume + LinkedIn PDF + WHY statement, runs them through 4 LLM agents, and produces a fit-ranked role recommendation report with gap analysis. Built as an MBA portfolio project. Stack: Python, Streamlit UI, Ollama (local LLMs), Pydantic for schema enforcement.

The pipeline is functional and has been run on real user profiles. Current priority is fixing data accuracy issues surfaced by running it on a non-builder profile (Amos Ng, physician) before expanding to more users.

---

## Architecture

```
app.py                      # Streamlit UI — entry point
engine.py                   # Pipeline orchestrator — 4 stages
config.py                   # Reads tuning.yaml, exposes helpers
parsers.py                  # PDF text extraction
skills.py                   # Skill extraction + alias matching + graph inference
tally_intake.py             # CLI tool: pull submissions from Tally form, run pipeline
output.py                   # Assemble final output dict from PipelineState
pdf_export.py               # Generate styled PDF from output dict

agents/
  profile_synthesizer.py    # Agent 1 (Qwen 7B) — structured candidate profile from resume
  motivation_extractor.py   # Agent 2 (Qwen 7B) — WHY statement → motivation themes
  role_comparator.py        # Agent 3 (Qwen 7B) — role fit scoring with self-consistency
  gap_analyzer.py           # Agent 4 (Qwen 7B) — gap identification per role

matching/
  embeddings.py             # Embedding pre-match: narrow 18 roles to top-K candidates
  skill_overlap.py          # Deterministic required/preferred skill coverage per role
  skill_graph.py            # Co-occurrence graph: hub skills, neighbor inference
  confidence.py             # Composite confidence band from 3 signals

analysis/
  cross_role.py             # Cross-role ranking, shared gaps, leverage skills

data/
  onet_skills.json          # 469 canonical skills (O*NET + ESCO enriched)
  skill_aliases.json        # 1,825 alias entries → canonical skill name
  role_taxonomy.json        # 20 target roles with required/preferred skills + metadata
```

**Pipeline stages (engine.py):**
```
Stage 1: Input Processing
  parse_pdf() → skills.py (alias + LLM extraction + graph inference)

Stage 2: Profile Synthesis
  Agent 1 (CandidateProfile) → Agent 2 (MotivationProfile)

Stage 3: Role Matching
  embeddings.py (top-K pre-filter) → skill_overlap.py (deterministic anchor)
  → Agent 3 (RoleFitResult × N roles, parallel) → Agent 4 (RoleGapAnalysis × N roles)
  → confidence.py → cross_role.py

Stage 4: Output Assembly
  output.py → app.py renders 7 sections → pdf_export.py
```

**Key data models (Pydantic, schema-enforced via `format=Model.model_json_schema()`):**
- `CandidateProfile` — skill_clusters, industry_signals, narrative_coherence_score
- `MotivationProfile` — 7 motivation theme dimensions (0-1 scores)
- `RoleFitResult` — structural_fit_score, motivation_alignment, evidence_chain
- `RoleGapAnalysis` — gap_items (each with severity, evidence_source)

**LLM configuration (tuning.yaml):**
- Extraction model: `qwen2.5:7b` (Agents 1, 2)
- Reasoning model: `qwen2.5:7b` (Agents 3, 4) — upgrade path to phi4:14b documented
- Embedding: `nomic-embed-text` via Ollama
- All parameters tunable in `tuning.yaml` — no hardcoded values in code

**State object:** `PipelineState` dataclass in `engine.py` carries all intermediate results between stages. Never pass raw dicts between stages — use `PipelineState` fields.

---

## How to Run

```bash
# Start Ollama server (separate terminal)
ollama serve

# Run Streamlit app
streamlit run app.py

# CLI: list Tally submissions
python tally_intake.py --list

# CLI: run pipeline on a Tally submission
python tally_intake.py
```

Run output saved to `runs/` as `run_HHMMSS.json`. `latest_run.json` is always overwritten with the most recent run.

---

## Coding Conventions

1. **All LLM calls use `format=PydanticModel.model_json_schema()`** — never `format="json"`. This enforces schema at the grammar level via Ollama's structured output.
2. **All tunable parameters come from `tuning.yaml` via `get_tuning()`** — never hardcode thresholds, weights, or model names in agent files.
3. **Use `config.py` helpers:** `extraction_options()` and `reasoning_options()` return the correct `num_ctx` + temperature dicts for `ollama.chat()` calls.
4. **`skill_aliases.json` format:** Top-level object with `"aliases"` key containing a flat dict: `{"version": "...", "aliases": {"alias string": "Canonical Skill Name", ...}}`. All alias keys lowercase; values must exactly match a `skill_name` in `onet_skills.json` (title-cased). Skills.py loads via `data.get("aliases", data)` — the wrapper is required.
5. **`role_taxonomy.json` format:** Top-level object with `"roles"` key containing an array: `{"version": "...", "roles": [{...}, ...]}`. Each role object has `role_id` (kebab-case), `title`, `required_skills` (list), `preferred_skills` (list), `motivation_attributes` (dict), `expected_signals` (list), `barrier_conditions` (list).
6. **`onet_skills.json` format:** Top-level object with `"skills"` key containing an array: `{"version": "...", "skills": [{"skill_id": "...", "skill_name": "...", "category": "...", "description": "...", "aliases": [...]}, ...]}`. All `skill_name` values title-cased. Skills.py loads via `data.get("skills", [])` — the wrapper is required.
7. **No external API calls at runtime** — all enrichment data is baked into `data/` files at build time.
8. **Commit style:** `Session N: [one-line description]` — see git log for examples.
9. **Taxonomy governance is mandatory for `data/role_taxonomy.json` edits** — run `python scripts/validate_role_taxonomy.py` and follow `docs/taxonomy-governance.md` checklist + cohort review process before merge.
10. **Never commit:** `runs/`, `latest_run.json`, `PROJECT_LOG.md`, `ROADMAP.md`, `=*` files — covered by `.gitignore`.

---

## Roadmap + Triage Protocol

**Source of truth:** `feature-roadmap.csv` — MoSCoW prioritized, all open items.

**Claude's role:** Reviews PRs, triages which roadmap items to assign next, reviews output quality.
**Codex's role:** Creates PRs for assigned items. One item per PR unless items are trivially coupled.

**Before starting any item:**
1. Read the item's `description` and `notes` columns in `feature-roadmap.csv`
2. Check `notes` for dependencies (e.g. "blocked by CMF-001") — do not start blocked items
3. Set `status` to `In Progress` in `feature-roadmap.csv` in the same PR

**PR format:**
- Title: `[CMF-XXX] Short description`
- Body: what changed, which files, how to verify
- Include `feature-roadmap.csv` update (status → Done, completion note in `notes` column)

---

## Open Must Items — Current Priority Queue

Only one Must item remains open. All others (CMF-029, 030, 032, 034, 036, 006) were resolved in Sessions 11-13 or merged via PR #1.

---

### CMF-005 — End-to-end Tally intake run test
**Type:** Verification / minor bug fixes expected
**File:** `tally_intake.py`, `runs/processed_submissions.json`
**Problem:** `tally_intake.py` is fully implemented (Session 11) but has never been run end-to-end on a real Tally submission. Known issue: `--list` fails with `FileNotFoundError` if no Tally API key is available in the environment.
**Task:**
- If Codex can run it: `python tally_intake.py` against one of the 3 existing Tally submissions. Confirm run saves to `runs/` with submission ID in filename and `processed_submissions.json` updates. Fix any crashes.
- If no API key: add a `--dry-run` flag that exercises the full intake code path against a fixture JSON response (no live API call). This verifies parsing and routing logic without credentials.
**Verify:** Either a clean end-to-end run log OR a working `--dry-run` path with fixture data that exercises all code branches.

---

## Should Items (Next Priority After Must Clears)

For awareness — Codex should not start these until CMF-005 is Done. Ordered by recommended implementation sequence.

- **CMF-031** — Rename HIPAA Compliance to Healthcare Regulatory Compliance + add international aliases + one straggler alias from CMF-030 (`"clinical experience"` → `"Healthcare Domain Knowledge"`)
- **CMF-033** — Validate barrier conditions against candidate profile before flagging as gaps (prompt engineering in gap_analyzer.py)
- **CMF-035** — Add expected_signal_coverage to skill_overlap computation (new PipelineState field + penalty multiplier in tuning.yaml)
- **CMF-007** — Transferable language enrichment layer (new skills.py substep + engine.py wiring)
- **CMF-028c** — Lightcast Open Skills snapshot for tool-level aliases (one-time API dump to local CSV)

Full descriptions in `feature-roadmap.csv`.

---

## Key Constraints

- **No external API calls at runtime.** All data enrichment is done at build time and baked into `data/` files.
- **All LLM parameters in tuning.yaml.** If adding a new threshold or weight, add it to `tuning.yaml` and read via `get_tuning()` — do not hardcode in agent files.
- **Schema enforcement is critical.** Never downgrade `format=Model.model_json_schema()` back to `format="json"`. The pipeline crashed repeatedly before this was enforced (see PROJECT_LOG.md Session 6).
- **Alias matching is case-sensitive on values, case-insensitive on lookup.** Keys in `skill_aliases.json` should be lowercase. Values must exactly match canonical names in `onet_skills.json` (title-cased).
- **Test with `python -c "from engine import run_pipeline"` imports** before opening a PR. Import errors in one file can silently kill the pipeline.
