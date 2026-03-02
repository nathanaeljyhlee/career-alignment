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
  onet_skills.json          # 468 canonical skills (O*NET + ESCO enriched)
  skill_aliases.json        # 1,806 alias entries → canonical skill name
  role_taxonomy.json        # 18 target roles with required/preferred skills + metadata
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
4. **`skill_aliases.json` format:** `{"alias string": "Canonical Skill Name"}` — all keys lowercase, values match canonical name in `onet_skills.json` exactly.
5. **`role_taxonomy.json` format:** Array of role objects. Each role has `role_id`, `title`, `required_skills` (list), `preferred_skills` (list), `motivation_attributes` (dict), `expected_signals` (list), `barrier_conditions` (list).
6. **`onet_skills.json` format:** `{"Canonical Skill Name": {"category": "...", "source": "...", ...}}` — all canonical names title-cased.
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

Ordered by recommended implementation sequence. All are independent unless noted.

---

### CMF-029 — Add clinical/medical aliases for Critical Thinking
**Type:** Data-only (no code changes)
**File:** `data/skill_aliases.json`
**Problem:** A physician with 6+ years clinical practice shows Critical Thinking as `missing_required` for every role. No clinical-context aliases exist for this skill.
**Fix:** Add ~8 entries mapping clinical terminology to `"Critical Thinking"`:
```
"clinical reasoning" → "Critical Thinking"
"clinical decision making" → "Critical Thinking"
"differential diagnosis" → "Critical Thinking"
"clinical judgment" → "Critical Thinking"
"evidence-based medicine" → "Critical Thinking"
"diagnostic reasoning" → "Critical Thinking"
"medical problem solving" → "Critical Thinking"
"clinical analysis" → "Critical Thinking"
```
**Verify:** After adding, `skill_aliases.json` keys for the above should map to `"Critical Thinking"` (exact match, title-cased value).

---

### CMF-030 — Add medical experience aliases for Healthcare Domain Knowledge and Clinical Workflow Understanding
**Type:** Data-only (no code changes)
**File:** `data/skill_aliases.json`
**Problem:** PM HealthTech role lists a practicing physician as missing PREFERRED skills for healthcare domain knowledge and clinical workflow. Most damaging inaccuracy in the engine.
**Fix (Healthcare Domain Knowledge):**
```
"patient care" → "Healthcare Domain Knowledge"
"clinical practice" → "Healthcare Domain Knowledge"
"medical practice" → "Healthcare Domain Knowledge"
"physician experience" → "Healthcare Domain Knowledge"
"clinical experience" → "Healthcare Domain Knowledge"
```
**Fix (Clinical Workflow Understanding):**
```
"ward management" → "Clinical Workflow Understanding"
"discharge planning" → "Clinical Workflow Understanding"
"clinical operations" → "Clinical Workflow Understanding"
"hospital operations" → "Clinical Workflow Understanding"
"patient flow" → "Clinical Workflow Understanding"
"inpatient management" → "Clinical Workflow Understanding"
```
**Note:** Verify `"Healthcare Domain Knowledge"` and `"Clinical Workflow Understanding"` exist as canonical names in `onet_skills.json` before adding aliases. Add to onet_skills.json first if missing.

---

### CMF-032 — Fix gap dedup logic (substring match on skill names)
**Type:** Bug fix
**File:** `agents/gap_analyzer.py`
**Problem:** Lines ~207-215 deduplicate gaps by checking `g.description.lower() in matched_set`. Gap descriptions are full sentences (e.g. "Lacks Technical Fluency in advanced data tools"), not skill names, so this check never fires. LLM can output gaps that directly contradict the deterministic overlap data.
**Fix:** Also strip gaps where any matched skill name (len >= 8) appears as a substring in the gap description:
```python
# Current (broken):
if g.description.lower() not in matched_set

# Fixed:
if g.description.lower() not in matched_set and not any(
    m in g.description.lower() for m in matched_lower if len(m) >= 8
)
```
Where `matched_lower` is the set of matched skill names lowercased (already computed nearby — check the surrounding context to wire it correctly).
**Verify:** Two confirmed false gaps from Amos run: "Lacks Technical Fluency" (matched_preferred for Tech PM) and "Missing Agile Methodology" (matched_preferred for PM EdTech) should not appear in gap output after fix.

---

### CMF-034 — Add Digital Transformation to GovTech required_skills
**Type:** Data-only (no code changes)
**File:** `data/role_taxonomy.json`
**Problem:** Government Digital Services ranks #1 for a physician (0.7 composite / strong) despite zero public sector experience. Root cause: all required_skills are generic leadership skills (Stakeholder Management, Project Management, Communication, Cross-Functional Leadership, Change Management) that graph inference fills for any experienced professional. No domain filter exists.
**Fix:** Add `"Digital Transformation"` to `required_skills` for the `government-digital-services` role entry in `role_taxonomy.json`.
**Expected impact:** Drops physician's required skill coverage from 62.5% to ~37.5%, moving GovTech out of "Win Now" band.
**Verify:** `"Digital Transformation"` must exist as a canonical skill in `onet_skills.json`. If not, add it with category `"strategy"` before referencing it in the taxonomy.

---

### CMF-036 — Add healthcare-pivot roles to role taxonomy
**Type:** Data addition
**File:** `data/role_taxonomy.json`
**Problem:** The 18-role taxonomy was built for a tech/strategy/product/finance career search. No appropriate transition roles exist for clinical-to-MBA candidates. A physician running the engine gets no relevant role matches.
**Fix:** Add 2 new roles following the existing role object schema:

**Role 1: Healthcare Technology Consulting**
- `role_id`: `"healthcare-technology-consulting"`
- Focus: clinical domain expertise + digital transformation advisory + health system clients
- Required skills should include: Healthcare Domain Knowledge, Stakeholder Management, Project Management, Strategic Planning, Communication
- Preferred skills: Clinical Workflow Understanding, Digital Transformation, Data Analysis, Change Management
- `motivation_attributes`: impact_orientation high, innovation moderate, leadership_scale moderate
- `expected_signals`: clinical background, health system or hospital experience, digital health interest

**Role 2: Digital Health Strategy**
- `role_id`: `"digital-health-strategy"`
- Focus: health system transformation + product strategy + clinical background as differentiator
- Required skills: Healthcare Domain Knowledge, Strategic Planning, Stakeholder Management, Communication, Project Management
- Preferred skills: Clinical Workflow Understanding, Digital Transformation, Product Sense (if in taxonomy), Data Analysis
- `motivation_attributes`: impact_orientation high, innovation high, leadership_scale moderate
- `expected_signals`: clinical or healthcare background, interest in health tech/digital tools, MBA pivot signal

**Note:** Review existing role objects in `role_taxonomy.json` for exact schema before adding. Required and preferred skill names must exactly match canonical names in `onet_skills.json`.

---

### CMF-005 — End-to-end Tally intake run test (verification only)
**Type:** Verification / testing — no code changes expected
**File:** `tally_intake.py` (already built in Session 11)
**Problem:** `tally_intake.py` is fully implemented but has not been run end-to-end on a real Tally submission. One known issue: Submission 2 uploaded `.docx` not PDF — should produce a clear error message without crashing.
**Task:** Run `python tally_intake.py` against one of the 3 existing Tally submissions. Confirm:
- Pipeline runs to completion
- Output saved to `runs/` with submission ID in filename
- `processed_submissions.json` updated
- Non-PDF submission (if used) produces error message, not crash
**If bugs found:** Fix them and document in PR body. Update `feature-roadmap.csv` status to Done only when a clean run completes.

---

### CMF-006 — Skill extraction observability UI
**Type:** UI feature
**File:** `app.py`
**Problem:** The `match_method` field already exists on every skill in `skills_flat` (values: `alias`, `llm`, `inferred`, `graph_inferred`, `transfer_label`). No UI layer exposes this to the user.
**Fix:** Add an expandable section in `app.py` (after Section 1 / Profile Summary, before role results) that shows which skills were extracted and by what method. Suggested format: grouped by method with skill names, counts per method.
**Note:** Keep it compact — expandable `st.expander("Skill Extraction Details")` is appropriate. Do not block the main flow.

---

## Should Items (Next Priority After Musts Clear)

For awareness — do not start until all Must items above are Done:

- **CMF-031** — Rename HIPAA Compliance to Healthcare Regulatory Compliance + add international aliases
- **CMF-033** — Validate barrier conditions against candidate profile before flagging as gaps (prompt engineering in gap_analyzer.py)
- **CMF-035** — Add expected_signal_coverage to skill_overlap computation (new PipelineState field + penalty multiplier)
- **CMF-007** — Transferable language enrichment layer (new skills.py substep)
- **CMF-028c** — Lightcast Open Skills snapshot for tool-level aliases (one-time API dump)
- **CMF-028b** — BLS EP 17-skill score overlay (manual download required from bls.gov)

Full descriptions in `feature-roadmap.csv`.

---

## Key Constraints

- **No external API calls at runtime.** All data enrichment is done at build time and baked into `data/` files.
- **All LLM parameters in tuning.yaml.** If adding a new threshold or weight, add it to `tuning.yaml` and read via `get_tuning()` — do not hardcode in agent files.
- **Schema enforcement is critical.** Never downgrade `format=Model.model_json_schema()` back to `format="json"`. The pipeline crashed repeatedly before this was enforced (see PROJECT_LOG.md Session 6).
- **Alias matching is case-sensitive on values, case-insensitive on lookup.** Keys in `skill_aliases.json` should be lowercase. Values must exactly match canonical names in `onet_skills.json` (title-cased).
- **Test with `python -c "from engine import run_pipeline"` imports** before opening a PR. Import errors in one file can silently kill the pipeline.
