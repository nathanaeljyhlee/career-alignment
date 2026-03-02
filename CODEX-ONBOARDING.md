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
  onet_skills.json          # 483 canonical skills (O*NET + ESCO enriched)
  skill_aliases.json        # 1,832 alias entries → canonical skill name
  role_taxonomy.json        # 20 target roles (expanding to 80 via CMF-037)
  role_taxonomy.schema.json # JSON schema — used by validate_role_taxonomy.py

scripts/
  validate_role_taxonomy.py # Schema + governance lint — run before any role_taxonomy.json PR

docs/
  taxonomy-governance.md    # Governance workflow for adding/modifying roles
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
5. **`role_taxonomy.json` format:** Top-level object with `"roles"` key containing an array: `{"version": "...", "roles": [{...}, ...]}`. Required role fields: `role_id` (kebab-case), `role_name`, `onet_code`, `category`, `description`, `required_skills`, `preferred_skills`, `motivation_attributes`, `expected_signals`, `barrier_conditions`, `bls_data`. Optional CMF-037 fields: `functional_category`, `track` (`"internship"` | `"ft"` | `"both"`), `mba_track` (bool), `babson_fit` (bool). Run `python scripts/validate_role_taxonomy.py` after any edit to this file.
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

## Current Priority Queue

Full specs in `CODEX-REVIEW-QUEUE.md`. Work top to bottom.

### Must (blocking user expansion)

**CMF-037 — Expand role taxonomy from 20 to 80 roles**
Fields `functional_category`, `track`, `mba_track`, `babson_fit` already added to existing 20 roles. Need 60 new roles covering internship/FT tracks, MBA-specific vs general, Babson entrepreneurial track. Add 14 new canonical skills to `onet_skills.json`. Full spec + all 60 role stubs in `CODEX-REVIEW-QUEUE.md`. Run `python scripts/validate_role_taxonomy.py` before opening PR.

### Should (next after CMF-037)

- **CMF-038** — Decision Sprint card: deterministic output section converting fit analysis to a 90-day commitment (role bet + skill closures + weekly loop + go/pivot checkpoint). No new LLM calls — all inputs already in pipeline output.
- **CMF-039** — Skill graph singleton: cache `build_skill_graph()` across runs (module-level lazy init). No output change.
- **CMF-040** — Parallelize Stage 2: run `synthesize_profile()` and `extract_motivation()` concurrently via `ThreadPoolExecutor`. No output change.

### Already done (do not re-implement)
CMF-001 through CMF-007, CMF-028 through CMF-036 — all closed. See merge log in `CODEX-REVIEW-QUEUE.md`.

---

## Key Constraints

- **No external API calls at runtime.** All data enrichment is done at build time and baked into `data/` files.
- **All LLM parameters in tuning.yaml.** If adding a new threshold or weight, add it to `tuning.yaml` and read via `get_tuning()` — do not hardcode in agent files.
- **Schema enforcement is critical.** Never downgrade `format=Model.model_json_schema()` back to `format="json"`. The pipeline crashed repeatedly before this was enforced (see PROJECT_LOG.md Session 6).
- **Alias matching is case-sensitive on values, case-insensitive on lookup.** Keys in `skill_aliases.json` should be lowercase. Values must exactly match canonical names in `onet_skills.json` (title-cased).
- **Test with `python -c "from engine import run_pipeline"` imports** before opening a PR. Import errors in one file can silently kill the pipeline.
