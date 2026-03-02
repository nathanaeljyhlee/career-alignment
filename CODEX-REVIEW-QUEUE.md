---
purpose: Living PR queue for Codex → Claude review → merge workflow
updated: 2026-03-02
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

### CMF-004 — Role recommendation bias / unbiased role expansion
**Type:** Data Quality + possible prompt change
**Files:** `data/role_taxonomy.json`, possibly `agents/profile_synthesizer.py`
**Problem:** When run on non-builder profiles, the engine may anchor role recommendations on the builder's background. GovTech false-positive was the clearest symptom (partially fixed by CMF-034 adding Digital Transformation as a required skill). Deeper issue: the 18-role taxonomy was calibrated on one profile. Need visibility into the full role universe considered and a way to expand frame without introducing bias.
**Fix approach:**
- Audit `role_taxonomy.json` for any required/preferred skills or motivation_attributes that are specific to the builder's profile (civic tech, fintech, startup experience) rather than the role itself
- For any role where required_skills are all generic leadership skills (no domain-specific filter), add at least one domain-anchoring required skill
- Do NOT redesign the full taxonomy — targeted fixes only. Document each change in the PR body with rationale.
**Verify:** Run a mental check: could a generic MBA student with no relevant domain experience score >60% on this role's required_skills via graph inference alone? If yes, the role needs a domain filter.

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

### CMF-031 — Rename HIPAA Compliance + add international aliases
**Type:** Data-only (no code changes)
**Files:** `data/role_taxonomy.json`, `data/skill_aliases.json`
**Problem:** HIPAA Compliance is a US-specific skill. Candidates who practiced medicine in non-US healthcare systems (Malaysia, UK, etc.) get a false gap. Current canonical name is only relevant for US candidates.
**Fix:**
1. In `role_taxonomy.json`: find all roles that list `HIPAA Compliance` in `required_skills` or `preferred_skills`. Rename to `Healthcare Regulatory Compliance`.
2. In `onet_skills.json`: add a new skill entry for `Healthcare Regulatory Compliance` (category: `"domain"`) OR rename the existing `HIPAA Compliance` entry if it exists. Keep `hipaa compliance` as an alias so US candidates still match.
3. In `skill_aliases.json`, add aliases mapping to `"Healthcare Regulatory Compliance"`:
   - `"hipaa compliance"` → `"Healthcare Regulatory Compliance"`
   - `"hipaa"` → `"Healthcare Regulatory Compliance"`
   - `"clinical compliance"` → `"Healthcare Regulatory Compliance"`
   - `"clinical governance"` → `"Healthcare Regulatory Compliance"`
   - `"medical regulatory"` → `"Healthcare Regulatory Compliance"`
   - `"healthcare compliance"` → `"Healthcare Regulatory Compliance"`
   - `"data protection in healthcare"` → `"Healthcare Regulatory Compliance"`
   - `"gdpr healthcare"` → `"Healthcare Regulatory Compliance"`
**Verify:** `HIPAA Compliance` should not appear anywhere in `role_taxonomy.json` after the fix.

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
| CMF-030 | Merged (PR #1) | One missing alias: `"clinical experience"` → `"Healthcare Domain Knowledge"`. Add in next data-only PR. |
| CMF-005 | In Progress | End-to-end Tally run — needs Tally API key |

---

## Merge Log

| PR | Items | Merged | Notes |
|----|-------|--------|-------|
| #1 | CMF-029/030/032/034/036/006 | 2026-03-02 | CMF-030 missing one alias (`clinical experience`). CMF-006 expander was pre-existing, PR added `transfer_label` support. Format-correct across all data files. |

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
