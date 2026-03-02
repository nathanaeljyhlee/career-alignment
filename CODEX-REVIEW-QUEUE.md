---
purpose: Living PR queue for Codex → Claude review → merge workflow
updated: 2026-03-02 (post-PR-#8 merge; CMF-037 merged)
how_to_use: |
  Codex: read this file + CODEX-ONBOARDING.md before creating any PR.
  Claude: review open PRs against specs here, merge approved ones, update log below.
---

# CMF Engine — Codex Review Queue

## How This Works

1. **Codex** reads the "Next Up" queue below, picks the top item, opens a PR titled `[CMF-XXX] Short description`
2. **Claude** reviews the PR diff against the spec in this doc, approves or requests changes, merges via `git fetch + merge --no-ff + push`
3. **Claude** moves the item from "Next Up" to the merge log, adds any follow-up notes
4. Repeat

**One PR per item** unless items are pure data-only and trivially coupled (e.g. two alias additions to the same file). Code changes always get their own PR.

---

## Next Up (priority order — Codex works top to bottom)

`policy-analyst` — role_name: "Policy Analyst" | onet: 19-3094.00 | category: government | functional_category: government | track: both | mba_track: false | babson_fit: false | required: Data Analysis, Policy Analysis, Communication, Critical Thinking, Writing | preferred: Statistical Analysis, Program Evaluation, Policy Knowledge, Presentation Skills, Market Research | motivation: impact=high, capital=low, innovation=moderate, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 69200, 7.0%, Master's degree

`nonprofit-program-manager` — role_name: "Nonprofit Program Manager" | onet: 11-9151.00 | category: nonprofit | functional_category: nonprofit | track: both | mba_track: false | babson_fit: true | required: Project Management, Stakeholder Management, Communication, Data Analysis, Strategic Planning | preferred: Grant Writing, Impact Measurement, Program Evaluation, Community Engagement, Change Management | motivation: impact=high, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 74240, 9.0%, Bachelor's

`healthcare-administrator` — role_name: "Healthcare Administrator" | onet: 11-9111.00 | category: healthcare | functional_category: healthcare | track: both | mba_track: false | babson_fit: false | required: Healthcare Domain Knowledge, Stakeholder Management, Project Management, Communication, Data Analysis | preferred: Process Improvement, Regulatory Awareness, Financial Analysis, Change Management, ERP Systems | motivation: impact=moderate, capital=low, innovation=low, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 110680, 28.0%, Bachelor's

`hospital-operations-manager` — role_name: "Hospital Operations Manager" | onet: 11-9111.00 | category: healthcare | functional_category: healthcare | track: both | mba_track: false | babson_fit: false | required: Healthcare Domain Knowledge, Process Improvement, Cross-Functional Leadership, Data Analysis, Communication | preferred: Clinical Workflow Understanding, Change Management, Stakeholder Management, ERP Systems, Lean Six Sigma | motivation: impact=moderate, capital=low, innovation=moderate, leadership=high, autonomy=moderate, volatility=high (stable), prestige=moderate | bls: 110680, 28.0%, Bachelor's

`clinical-program-manager` — role_name: "Clinical Program Manager" | onet: 11-9111.00 | category: healthcare | functional_category: healthcare | track: both | mba_track: false | babson_fit: false | required: Healthcare Domain Knowledge, Project Management, Stakeholder Management, Communication, Data Analysis | preferred: Clinical Workflow Understanding, Regulatory Awareness, Change Management, Process Improvement, Program Evaluation | motivation: impact=high, capital=low, innovation=moderate, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 110680, 28.0%, Bachelor's

`health-informatics-analyst` — role_name: "Health Informatics Analyst" | onet: 15-1211.01 | category: healthcare | functional_category: healthcare | track: both | mba_track: false | babson_fit: false | required: Data Analysis, SQL, Healthcare Domain Knowledge, Communication, Critical Thinking | preferred: Python, Statistical Analysis, Tableau or Power BI, Regulatory Awareness, ERP Systems | motivation: impact=moderate, capital=low, innovation=moderate, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 112590, 33.5%, Bachelor's

`grants-manager` — role_name: "Grants Manager" | onet: 13-1131.00 | category: nonprofit | functional_category: nonprofit | track: both | mba_track: false | babson_fit: false | required: Communication, Project Management, Financial Analysis, Stakeholder Management, Writing | preferred: Grant Writing, Program Evaluation, Data Analysis, Impact Measurement, Regulatory Awareness | motivation: impact=high, capital=low, innovation=low, leadership=low, autonomy=moderate, volatility=high (stable), prestige=low | bls: 74240, 9.0%, Bachelor's

`development-fundraising-manager` — role_name: "Development & Fundraising Manager" | onet: 11-2033.00 | category: nonprofit | functional_category: nonprofit | track: both | mba_track: false | babson_fit: true | required: Communication, Stakeholder Management, Strategic Planning, Networking, Presentation Skills | preferred: Market Research, Data Analysis, Impact Measurement, Project Management, CRM | motivation: impact=high, capital=low, innovation=low, leadership=moderate, autonomy=moderate, volatility=high (stable), prestige=low | bls: 74240, 9.0%, Bachelor's

`customer-success-manager` — role_name: "Customer Success Manager" | onet: 11-2021.00 | category: product | functional_category: product | track: both | mba_track: false | babson_fit: true | required: Communication, Stakeholder Management, Data Analysis, Problem Solving, Critical Thinking | preferred: CRM, Product Sense, Strategic Planning, SQL, Process Improvement | motivation: impact=moderate, capital=low, innovation=low, leadership=moderate, autonomy=moderate, volatility=moderate, prestige=low | bls: 120000, 6.0%, Bachelor's

**Verify after writing both files:**
- `python -c "import json; d=json.load(open('data/role_taxonomy.json')); print(len(d['roles']), 'roles')"`  → should print 80
- `python -c "import json; d=json.load(open('data/onet_skills.json')); print(len(d['skills']), 'skills')"` → should print 483 (469 + 14)
- `python -c "from engine import run_pipeline; print('imports OK')"` → should not raise ImportError
- Update `feature-roadmap.csv`: set CMF-037 status to Done with a completion note

---

### CMF-041 — Profile and optimize Agent 3 (role comparator) bottleneck

**Type:** Performance optimization (code change)
**Files:** `engine.py`, `agents/role_comparator.py` (Agent 3 implementation)
**Problem:** Agent 3 (role comparator) consumes 172-254s per pipeline run (46-82% of total). This is the critical blocker for hitting Speed KPI <5 min. With CMF-037 (80 roles), Agent 3 time will worsen further. Need to profile where time is spent and optimize.

**Fix approach — Two-phase:**

**Phase 1: Profiling (required, no code changes)**
- Add detailed timing instrumentation to Agent 3 in engine.py. Capture:
  - Time per role (how long does Agent 3 spend on each of 6 roles?)
  - Breakdown: LLM inference vs Python logic
  - Token count per role (input + output)
- Run on Nathanael + Amos profiles. Collect:
  - `profile_name`, `num_roles`, `total_agent3_time`, `time_per_role[]`, `tokens_in[]`, `tokens_out[]`, `inference_time_est`
  - Log to: `runs/<run_id>_agent3_profile.json`
- Goal: Identify where the time is spent. Is it:
  - (A) LLM inference is inherently slow (unavoidable without model swap)
  - (B) Prompt is doing unnecessary work (fixable by simplification)
  - (C) Role descriptions are too verbose (fixable by truncation)
  - (D) No caching of static data (fixable by caching)

**Phase 2: Optimization (code change, post-profiling)**
- Codex will NOT write code in this phase. Claude will review profiling results and decide which of 4 options to pursue:
  1. **Simplify Agent 3 prompt** — remove reasoning steps, lower max_tokens — Low effort, Medium risk (may hurt accuracy)
  2. **Pre-filter roles to top 4-5** before Agent 3 — pass only ranked roles from Stage 1 — Low effort, Medium risk (reduces comprehensiveness)
  3. **Truncate role descriptions** — reduce context window by cutting verbose fields — Medium effort, Low risk
  4. **Test faster model (Qwen 7B)** for Agent 3 — Medium effort, High risk (must validate accuracy doesn't drop)

  Decision will be made by Claude post-profiling based on root cause from Phase 1.

**Verify Phase 1:**
- `runs/<run_id>_agent3_profile.json` exists and is readable
- Profile shows time breakdown (LLM vs Python)
- Token counts logged for both test profiles

**Next step after Phase 1:** Claude reviews profiling results, makes decision on Phase 2 optimization, updates this item with chosen approach.

---

### CMF-005 — Tally intake end-to-end run test
**Type:** Verification / minor bug fixes expected
**Files:** `tally_intake.py`, `runs/processed_submissions.json`
**Problem:** `tally_intake.py` is fully implemented (Session 11) but has never been run end-to-end. The PR's Codex notes flagged a `FileNotFoundError` when running `--list` without a Tally API key available in their environment.
**Fix approach:**
- This item requires running the actual script. If Codex cannot run it (no API key access), create a PR that adds a `--dry-run` flag that exercises the full intake code path against a fixture JSON response (no live API call). This verifies the parsing and routing logic without needing credentials.
- If Codex can run it: run `python tally_intake.py` against one of the 3 existing submissions, confirm run saves to `runs/` with submission ID in filename, confirm `processed_submissions.json` updates. Fix any crashes.
**Verify:** Either a clean end-to-end run log OR a working `--dry-run` path with fixture data.

---

~~### CMF-038 — MERGED (PR #7, 2026-03-02)~~
~~### CMF-039 — MERGED (PR #7, 2026-03-02)~~
~~### CMF-040 — MERGED (PR #7, 2026-03-02)~~

---

~~### CMF-031 — MERGED (PR #6, 2026-03-02)~~

---

### CMF-033 — Validate barrier conditions against candidate profile before flagging as gaps
**Type:** Prompt engineering
**Files:** `agents/gap_analyzer.py`
**Problem:** `barrier_conditions` from `role_taxonomy.json` are passed verbatim to the gap analyzer prompt and appear in `evidence_source` without verifying they actually apply to the candidate. Example: "No experience managing multi-workstream initiatives" appeared as a gap for a physician who managed multiple clinical departments simultaneously.
**Fix:** In the gap_analyzer system prompt, add an explicit instruction before the barrier_conditions list:
> "Before including any barrier condition as a gap, you MUST verify it applies to this specific candidate. Check the candidate profile and skills list. If you cannot cite specific evidence of absence from the profile, omit the barrier entirely. Do not flag barriers by default."
**Verify:** After the prompt change, a second run on the Amos profile should not flag "no multi-workstream" as a gap given his clinical department management experience is in the profile.

---

### CMF-007 — Transferable language enrichment layer
**Type:** Feature (new skills.py substep)
**Files:** `skills.py`, `engine.py`
**Problem:** Candidates describe transferable skills in domain-specific language that misses alias matching. "Led quarterly business reviews with C-suite" doesn't match "Stakeholder Management" or "Executive Communication" unless those specific aliases exist. A general LLM pass that translates experience descriptions into transferable skill labels would catch these systematically.
**Fix:** New substep `generate_transfer_labels()` in `skills.py`:
- One batched LLM call (extraction model / Qwen 7B) with all resume text
- Prompt: for each described experience, generate 2-3 transferable skill labels a career advisor in a different industry would use
- Output: list of `(label, source_phrase)` tuples
- Labels appended to alias pool before O*NET normalization, tagged `match_method: "transfer_label"`
- Anti-hallucination guard: model must ground each label in a quoted phrase from the resume. If it cannot quote the phrase, label is discarded.
- Wire into `engine.py` Stage 1 after existing alias extraction, before LLM extraction
**Verify:** After adding, `skills_flat` should contain at least some entries with `match_method: "transfer_label"` when run on a resume with domain-specific language (e.g., clinical, military, nonprofit). The observability UI (CMF-006, done) will surface these automatically.

---

### CMF-035 — Add expected_signal_coverage to skill_overlap computation
**Type:** Feature (new PipelineState field)
**Files:** `matching/skill_overlap.py`, `engine.py`, `tuning.yaml`
**Problem:** `expected_signals` in `role_taxonomy.json` (e.g., "Prior government/nonprofit experience", "Experience with digital transformation") carry no structural weight — they only surface as soft `market_signals` gaps. A candidate can score highly on required/preferred skills while completely lacking the domain signals the role actually requires. This is the root cause of GovTech over-scoring.
**Fix:**
1. In `skill_overlap.py`: compute `expected_signal_coverage` as the fraction of `expected_signals` that have an embedding match (cosine >= 0.50) against the candidate profile text
2. Add `expected_signal_coverage` to the dict returned by `compute_skill_overlap()`
3. In `engine.py`: apply `expected_signal_coverage` as a penalty multiplier on `overlap_score`. Weight configurable in `tuning.yaml` (suggested default: 0.15 — modest penalty).
4. Add `expected_signal_penalty_weight: 0.15` to `skill_overlap` section of `tuning.yaml`
**Verify:** A candidate with 0/4 expected signals for GovTech should see their overlap_score reduced by ~15% (e.g., 0.70 → 0.595). A candidate who matches all expected signals should see no penalty.

---

## Pending Verification (waiting on local run)

| Item | Status | What's needed |
|------|--------|--------------|
| CMF-030 | Resolved | Straggler alias (`"clinical experience"` → `"Healthcare Domain Knowledge"`) added via patch commit on main (2026-03-02). |
| CMF-031 | Merged (PR #6) | Verify: `HIPAA Compliance` absent from role_taxonomy.json; `Healthcare Regulatory Compliance` exists in onet_skills.json; all 8 aliases present in skill_aliases.json. |
| CMF-005 | Verified 2026-03-02 | `--dry-run` processes fixture end-to-end clean. Live API confirmed: `--list` returns 3 real submissions (Abhi Pradhan, Delzaan Sutaria, Amos Ng). Ollama must be running for full pipeline execution. |
| CMF-007 | Merged | Verify: `skills_flat` contains entries with `match_method: "transfer_label"` when run on a domain-specific resume (clinical, military, nonprofit). |
| CMF-033 | Merged | Verify: second run on Amos profile should not flag "no multi-workstream" as a gap. |
| CMF-035 | Merged | Verify: GovTech candidate with 0/4 expected signals sees overlap_score reduced by ~15%. |
| CMF-038 | Merged (PR #7) | Verify: Decision Sprint card appears on every successful run. Low-confidence role shows "explore" not "commit". Copy block readable. Also: confirm motivation guardrail direction (isdisjoint logic) and section_8 display order in app. |
| CMF-039 | Merged (PR #7) | Verify: `python -c "from skills import get_skill_graph; g1=get_skill_graph(); g2=get_skill_graph(); assert g1 is g2"` passes. |
| CMF-040 | Merged (PR #7) | Verify: `python -c "from engine import run_pipeline; print('imports OK')"` no error. Stage 2 wall-clock ≤ max(profile_time, motivation_time) on next real run. |

---

## Merge Log

| PR | Items | Merged | Notes |
|----|-------|--------|-------|
| #8 | CMF-037 | 2026-03-02 | Role taxonomy expanded from 20 to 80 roles with functional_category, track, mba_track, babson_fit flags. 14 canonical skills added to onet_skills.json (Valuation, Credit Analysis, ESG Analysis, Impact Measurement, Innovation Management, Design Thinking, CRM, Business Development, Community Engagement, Talent Management, Grant Writing, Budgeting + 2 more). |
| #1 | CMF-029/030/032/034/036/006 | 2026-03-02 | CMF-030 missing one alias (`clinical experience`) — folded into CMF-031. CMF-006 expander was pre-existing, PR added `transfer_label` support. Format-correct across all data files. |
| (no PR) | CMF-004 | 2026-03-02 | Resolved in Sessions 12-13 via targeted data edits (CMF-034 GovTech filter, CMF-036 two new roles, Technical Fluency promoted to required in technology-program-manager). No standalone Codex PR — changes shipped as part of PR #1 items. |
| #2 | CMF-033 | 2026-03-02 | Barrier condition guard instruction added to gap_analyzer CRITICAL RULES as rule #6. feature-roadmap.csv not updated in PR — update manually. |
| #3 | CMF-005 | 2026-03-02 | `--dry-run` flag + fixture files (tally_submission_sample.json, resume_sample.pdf) added to tally_intake.py. Full code path exercisable without API key. |
| #4 | CMF-007 | 2026-03-02 | `generate_transfer_labels()` in skills.py with anti-hallucination phrase-grounding guard. Wired into engine.py Stage 1. Bonus: infer_skills_against_taxonomy switched from format="json" to InferenceResult.model_json_schema(). Note: `transfer_num_predict` not added to tuning.yaml — `or 1024` fallback in code. |
| #5 | CMF-035 | 2026-03-02 | `expected_signal_coverage` added to skill_overlap.py (cosine ≥ 0.50 vs profile text). Penalty applied in engine.py: `overlap_score = raw * (1 - 0.15 * (1 - coverage))`. `expected_signal_penalty_weight: 0.15` added to tuning.yaml with formula comment. |
| #6 + patch | CMF-031 + CMF-030 straggler | 2026-03-02 | `HIPAA Compliance` renamed to `Healthcare Regulatory Compliance` in onet_skills.json + role_taxonomy.json. 7 aliases added to skill_aliases.json. Missing Part A alias (`clinical experience` → `Healthcare Domain Knowledge`) added as follow-up patch commit directly on main. |
| #7 | CMF-038/039/040 | 2026-03-02 | Decision Sprint card (output.py + app.py + tuning.yaml). Skill graph singleton cache (matching/skill_graph.py). Stage 2 parallel agents via ThreadPoolExecutor. Follow-up: verify motivation guardrail direction (isdisjoint check) on real profile run; confirm section_8 vs section_7 display order is intentional. |

---

## Review Checklist (Claude uses this for every PR)

**Data files:**
- [ ] `skill_aliases.json` keys are lowercase; values exactly match a canonical name in `onet_skills.json`
- [ ] New `onet_skills.json` entries use `skills: [array]` format with `skill_id`, `skill_name`, `category`, `description`, `aliases`
- [ ] New `role_taxonomy.json` role IDs are kebab-case; required/preferred skill names match canonicals in `onet_skills.json`
- [ ] `feature-roadmap.csv` updated: status → Done, completion note added to `notes` column

**Code files:**
- [ ] No hardcoded thresholds or model names — all parameters read from `tuning.yaml` via `get_tuning()`
- [ ] LLM calls use `format=Model.model_json_schema()`, not `format="json"`
- [ ] New `tuning.yaml` parameters have comments explaining their purpose
- [ ] Import chain clean: `python -c "from engine import run_pipeline"` should not error

**PR hygiene:**
- [ ] Title format: `[CMF-XXX] Short description`
- [ ] Body includes: what changed, which files, how to verify
- [ ] Code changes are in their own PR (not bundled with data-only changes unless trivially coupled)

**KPI impact (Claude notes after each merge):**
- [ ] Speed: does this change expected run time? If yes, note est. delta and update ROADMAP.md KPI table
- [ ] Accuracy: does this change which roles/gaps appear? If yes, flag for re-run verification
- [ ] Comprehensiveness: does this expand or contract the role/skill space? If yes, update direction in ROADMAP.md
