# Current-State Alignment Review (March 2026)

This review evaluates the current codebase against the product goals in the roadmap: **high-signal fit accuracy**, **actionable decision guidance**, **privacy-first local operation**, and **responsive runtime**.

## Objective-by-Objective Snapshot

### 1) Privacy-first local inference
**Status: Aligned**
- Core inference paths use local Ollama models for both chat and embeddings.
- No network transport is required for model calls in the normal pipeline path.

### 2) Fit accuracy and anti-false-positive controls
**Status: Partially aligned**
- Deterministic overlap scoring is in place and includes expected-signal penalties before Agent 3 scoring.
- Gap and cross-role outputs are present, but some ranking logic can still be skewed by implementation details listed below.

### 3) Actionability (clear decisions + leverage moves)
**Status: Partially aligned**
- Decision Sprint and cross-role leverage are implemented.
- A guardrail intended to honor candidate optimization priorities currently reads from the wrong location in the output structure, so it may not influence target-role selection as intended.

### 4) Runtime/performance efficiency
**Status: Partially aligned**
- Stage 2 parallelization and skill-graph caching are implemented.
- There is still avoidable repeated embedding work in Stage 3 overlap scoring.

---

## Misalignments and Inefficiencies

## A. Decision Sprint priority guardrail is effectively disconnected
**What is happening**
- `build_decision_sprint()` looks for `optimization_priorities` at `section_1_snapshot.optimization_priorities`.
- But `build_output()` stores these values under `section_1_snapshot.tally_intake.optimization_priorities`.

**Impact**
- The guardrail that should de-prioritize roles with disjoint constraints is likely inert in Tally-driven runs.
- This weakens product intent for personalized decision support.

**Recommendation**
1. Read priorities from `section_1_snapshot.tally_intake.optimization_priorities` first, with backward-compatible fallback.
2. Add a small unit test fixture around Decision Sprint role-bet selection to validate guardrail behavior.

## B. Repeated embedding calls in skill overlap create avoidable latency
**What is happening**
- `compute_skill_overlap()` embeds candidate skill names and profile chunks per role.
- Stage 3 loops this over each matched role, repeating candidate-side embeddings each time.

**Impact**
- Higher end-to-end latency, especially with larger top-K role sets.
- Unnecessary CPU overhead for local-first deployments.

**Recommendation**
1. Precompute candidate embeddings once per run (candidate skill names + profile text chunks).
2. Pass precomputed vectors into overlap scoring per role.
3. Keep current API as wrapper for backwards compatibility.

## C. Documentation drift: output section count and rendering order are unclear
**What is happening**
- README still describes output as 7 sections in several places.
- The app renders Decision Sprint before Cross-Role Analysis while internal keys are `section_7_cross_role` and `section_8_decision_sprint`.

**Impact**
- New contributors and reviewers can misread expected behavior.
- Harder to reason about whether app behavior is intentional vs regression.

**Recommendation**
1. Update README to describe 8 sections and clarify display order in the Streamlit UI.
2. Add one short note in architecture docs that numbering in output keys is semantic, not strict UI order.

## D. Decision Sprint checkpoint text is hardcoded to 28-day language
**What is happening**
- `_render_decision_sprint_text()` always starts with `Decision Sprint (28-Day Checkpoint)`.
- `checkpoint_days` is configurable in `tuning.yaml`.

**Impact**
- User-visible copy can contradict configured behavior.

**Recommendation**
1. Generate the header dynamically from `checkpoint_days`.
2. Add regression check to ensure text always matches config.

---

## Prioritized Action Plan

### P0 (immediate)
- Fix Decision Sprint optimization-priority lookup path.
- Make checkpoint header text dynamic to match `tuning.yaml`.

### P1 (next)
- Refactor Stage 3 overlap scoring to reuse candidate embeddings across roles.
- Add timing instrumentation for overlap sub-steps before/after refactor.

### P2 (documentation + governance)
- Keep README section count and UI ordering documentation synchronized with `output.py`/`app.py`.
- Add a "documentation drift" checklist item in PR reviews for output schema changes.

---

## Suggested Validation Checks After P0/P1

- Deterministic fixture test: decision-sprint role bet changes when optimization priorities conflict.
- Runtime benchmark: Stage 3 median time before vs after embedding reuse.
- Snapshot test: decision-sprint copy includes configured checkpoint days.

