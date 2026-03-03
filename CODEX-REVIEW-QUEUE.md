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

1. **CMF-041 Phase 2 Decision** (WAITING ON PROFILING DATA)
   - Nathanael: run CMF-041 end-to-end on Nathanael + Amos profiles (6 roles each)
   - Collect `runs/<run_id>_agent3_profile.json` artifacts
   - Analyze LLM vs Python time ratio, token counts
   - Decide Phase 2 optimization: (A) simplify prompt, (B) pre-filter roles, (C) truncate descriptions, or (D) swap model
   - Codex implements chosen fix

2. **CMF-005 — Tally intake end-to-end run test**
   - Type: Verification / minor bug fixes expected
   - Run `python tally_intake.py` against real submissions or implement `--dry-run` with fixture if API key unavailable
   - Verify submission parsing, routing, and `processed_submissions.json` updates

3. **CMF-033 — Gap analyzer prompt guardrail (optional post-heuristic)**
   - Current: heuristic filter `_is_unverified_barrier_gap()` deployed (PR #10)
   - Optional: add explicit system prompt instruction as preventive guard ("Before including any barrier condition...")
   - Test on Amos profile to verify "no multi-workstream" is not flagged

4. **CMF-007 — Transferable language enrichment layer**
   - New substep `generate_transfer_labels()` in skills.py
   - Batched LLM call with anti-hallucination grounding guard
   - Output tagged with `match_method: "transfer_label"`

5. **Embedding reuse optimization (shipped in PR #10)**
   - Candidate-side embeddings (skill names + profile text) precomputed once per run
   - Reused across all role iterations in Stage 3
   - Expected latency reduction for Stage 3 with larger role sets
   - Next: profile to measure actual speedup

---

### CMF-041 — Profile and optimize Agent 3 (role comparator) bottleneck (PHASE 1 COMPLETE)

**Phase 1 Status: ✅ MERGED (PR #9, 2026-03-02)**

Phase 1 profiling instrumentation is now shipped. Codex implemented:
- Per-role timing breakdown (LLM vs Python) in `agents/role_comparator.py`
- Per-sample token counts with fallback estimation
- Automatic export to `runs/<run_id>_agent3_profile.json`
- Non-fatal error handling (profile export failures don't crash pipeline)

**Next step (Phase 2 — optimization decision):**
1. Run CMF-041 end-to-end on Nathanael + Amos profiles (6 roles each)
2. Collect profiling artifacts and analyze where time is spent (LLM vs Python ratio, token counts)
3. Claude decides optimization approach based on profiling root cause:
   - (A) → Simplify Agent 3 prompt (low effort, medium risk)
   - (B) → Pre-filter to top 4-5 roles (low effort, medium risk)
   - (C) → Truncate role descriptions (medium effort, low risk)
   - (D) → Test faster model like Qwen 7B (medium effort, high risk)
4. Codex implements chosen fix in Phase 2 PR

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

### CMF-033 — Validate barrier conditions against candidate profile before flagging as gaps (PARTIAL FIX SHIPPED)
**Type:** Prompt engineering + heuristic filtering
**Files:** `agents/gap_analyzer.py`
**Problem:** `barrier_conditions` from `role_taxonomy.json` are passed verbatim to the gap analyzer prompt and appear in `evidence_source` without verifying they actually apply to the candidate. Example: "No experience managing multi-workstream initiatives" appeared as a gap for a physician who managed multiple clinical departments simultaneously.

**Status:** Partially addressed in code alignment PR (2026-03-02):
- Added `_is_unverified_barrier_gap()` heuristic filter that removes barrier-condition gaps lacking candidate-specific evidence markers (profile/skills/overlap/resume/linkedin/missing)
- Filter runs post-LLM, catching cases where LLM flags barriers without grounding in profile

**Remaining work (optional):**
- Original spec: add explicit instruction to gap_analyzer system prompt ("Before including any barrier condition..."). This would be preventive (pre-LLM guardrail).
- Current approach: post-LLM filter (reactive, heuristic-based).
- If additional tests show the heuristic alone is insufficient, implement the prompt-side guard as well.

**Verify (next run):** Run on Amos profile; should not flag "no multi-workstream" as a gap given clinical department management in profile.

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
| #9 | CMF-041 Phase 1 | 2026-03-02 | Agent 3 profiling instrumentation: per-role timing (LLM vs Python), token counts, sample-level diagnostics. Automatic export to `runs/<run_id>_agent3_profile.json`. Next: run on Nathanael + Amos profiles to diagnose bottleneck, then decide Phase 2 optimization approach (simplify prompt, pre-filter roles, truncate descriptions, or swap model). |
| #10 | Alignment audit + fixes | 2026-03-02 | Code audit (docs/current-state-alignment-review.md + python-code-alignment-proposals.md). P0 fixes: Decision Sprint optimization-priority guardrail (was reading wrong path), checkpoint header made dynamic. P1 optimization: embedding precomputation for skill_overlap (reuse across role iterations). Gap analyzer barrier-condition heuristic filter added. README updated (section count 7→8). |

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
