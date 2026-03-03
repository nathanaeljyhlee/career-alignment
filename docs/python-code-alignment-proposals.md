# Python Codebase Alignment & Efficiency Proposals (Full File Audit)

Date: March 2026  
Scope: **Every `*.py` file** in the repository, reviewed against product objectives:
1) high-signal fit accuracy, 2) actionable output quality, 3) privacy-first local execution, 4) runtime efficiency, 5) maintainability.

## Priority rubric
- **P0** = high-impact alignment or correctness risk
- **P1** = meaningful performance/quality gain
- **P2** = maintainability, consistency, observability improvements

---

## 1) Root application modules

### `app.py`
- **Current alignment**: Functional UI coverage across all stages; good operator visibility via debug sections.
- **Proposals**:
  - **P0**: Make section numbering/order deterministic and explicit (Decision Sprint currently renders before Cross-Role even though key names imply inverse order) to reduce interpretation drift.
  - **P1**: Split into `ui/sidebar.py`, `ui/results.py`, `ui/forms.py` to improve testability and reduce ~770-line monolith complexity.
  - **P1**: Add lightweight timing badges for each section using `state.stage_timings` to improve user trust in pipeline behavior.
  - **P2**: Replace broad `except Exception` blocks in UI paths with narrower handling + user-facing reason categories (connection/data/parsing).

### `engine.py`
- **Current alignment**: Strong staged orchestration, structured run logs, and Stage-2 parallelization are already aligned with roadmap goals.
- **Proposals**:
  - **P0**: Extract stage handlers into dedicated modules (`pipeline/stage1.py` ... `stage4.py`) to reduce coupling and make regression testing easier.
  - **P0**: Add a formal `state.validate()` step between stages to enforce required fields and reduce silent degradation.
  - **P1**: Introduce role-loop micro-profiling (per-role overlap, comparator, gap timing) to isolate slow roles and improve optimization targeting.
  - **P1**: Add optional deterministic mode (seed + fixed top-k ordering) for reproducible benchmark runs.
  - **P2**: Convert ad-hoc warnings/errors to typed enums for downstream UI filtering and analytics.

### `output.py`
- **Current alignment**: Good deterministic post-processing and Decision Sprint assembly.
- **Proposals**:
  - **P0**: Fix Decision Sprint optimization-priority source path to check `section_1_snapshot.tally_intake.optimization_priorities` first.
  - **P0**: Guard against role ordering side effects by explicit sort keys when selecting top win-now/pivot and sprint target role.
  - **P1**: Move strategy-card math to pure helper functions and add unit tests for decision score, effort normalization, and constraints guardrail.
  - **P1**: Ensure all user-visible sprint copy is config-driven (header/day language and checkpoint framing).
  - **P2**: Add output schema version + migration note in metadata for backward compatibility of saved runs.

### `pdf_export.py`
- **Current alignment**: Delivers export capability from structured outputs.
- **Proposals**:
  - **P1**: Introduce reusable section render primitives to remove repeated layout patterns and reduce long-file maintenance burden.
  - **P1**: Add overflow-safe text wrapping helper for long gap descriptions and evidence chains.
  - **P2**: Add export smoke test using fixture output to detect rendering regressions.

### `parsers.py`
- **Current alignment**: Solid baseline extraction/section segmentation.
- **Proposals**:
  - **P1**: Add page-level OCR fallback hook (off by default) for image-based PDFs with explicit warning metadata.
  - **P1**: Add confidence score for section detection (header match ratio) to help downstream reliability messaging.
  - **P2**: Centralize header variants into data files for easier governance updates.

### `config.py`
- **Current alignment**: Minimal and clear config loader.
- **Proposals**:
  - **P1**: Add typed config model validation on load (required keys, weight sums, threshold ranges) to fail fast.
  - **P2**: Add environment variable overrides for endpoint/timeouts and optional debug flags.
  - **P2**: Include `reload_if_mtime_changed` helper for long-running UI sessions.

### `skills.py`
- **Current alignment**: Broad extraction coverage and taxonomy normalization; critical to product quality.
- **Proposals**:
  - **P0**: Decompose into focused modules (`aliases.py`, `embedding_match.py`, `llm_extract.py`, `inference.py`) to lower defect risk in a 650+ line core file.
  - **P1**: Cache embedding results for repeated skill strings across sections/runs (in-memory LRU) to reduce repeated Ollama embed calls.
  - **P1**: Add explicit provenance tags for each normalized skill (`alias`, `llm_extract`, `graph_infer`, `transfer_label`) to improve explanation quality.
  - **P2**: Add calibration report script (precision/recall on fixtures) for threshold tuning governance.

### `tally_intake.py`
- **Current alignment**: Enables external intake and operational workflow.
- **Proposals**:
  - **P1**: Isolate API client from transformation logic to allow offline unit tests and easier API evolution.
  - **P1**: Add idempotency guardrails (submission fingerprint + run status) to avoid duplicate processing under retries.
  - **P2**: Add structured audit trail output per submission (parse status, missing assets, pipeline outcome).

---

## 2) Agents

### `agents/profile_synthesizer.py`
- **Current alignment**: Schema-enforced structured extraction is strong.
- **Proposals**:
  - **P1**: Add evidence density and contradiction counters per skill cluster for stronger downstream confidence scoring.
  - **P2**: Split prompt template + postprocessing utilities to shrink file complexity and simplify prompt iteration.

### `agents/motivation_extractor.py`
- **Current alignment**: Produces consistent 7-dimension motivation profile.
- **Proposals**:
  - **P1**: Add explicit low-information pathway for short WHY statements (avoid overconfident theme assignment).
  - **P1**: Add deterministic fallback labeler when model response is malformed but text is present.
  - **P2**: Add calibration hooks to compare motivation labels vs human review set.

### `agents/role_comparator.py`
- **Current alignment**: Self-consistency and parallel role evaluation align with quality goals.
- **Proposals**:
  - **P0**: Make consensus aggregation explicitly robust to partial sample failure and expose sample-level diagnostics in output.
  - **P1**: Add adaptive worker cap based on CPU count and model throughput to prevent local machine overload.
  - **P1**: Add deterministic tie-breaker logic when fit bands/scores are near-equal.
  - **P2**: Externalize prompt fragments and scoring rationale templates for easier controlled updates.

### `agents/gap_analyzer.py`
- **Current alignment**: Deterministic overlap anchoring + post-dedup improves reliability.
- **Proposals**:
  - **P0**: Add explicit barrier-condition verification against candidate evidence before surfacing barrier gaps.
  - **P0**: Force inclusion order in output (missing required first, then preferred, then market/narrative) to preserve user trust.
  - **P1**: Add rule-based gap normalization (skill alias canonicalization in descriptions) before fuzzy grouping downstream.
  - **P2**: Emit per-gap rationale confidence for filtering in UI/PDF.

### `agents/__init__.py`
- **Current alignment**: Placeholder package marker.
- **Proposals**:
  - **P2**: Export stable public interfaces (optional) to standardize imports across modules.

---

## 3) Matching subsystem

### `matching/embeddings.py`
- **Current alignment**: Effective top-k retrieval and caching of role embeddings.
- **Proposals**:
  - **P1**: Add checksum-based invalidation for cached role embeddings when taxonomy changes.
  - **P1**: Cache candidate profile embeddings during run lifecycle to support repeated comparisons/debug mode.
  - **P2**: Emit retrieval diagnostics (threshold misses, marginal scores) to improve taxonomy tuning loop.

### `matching/skill_overlap.py`
- **Current alignment**: Deterministic overlap with embedding fallback and expected-signal coverage.
- **Proposals**:
  - **P0**: Refactor API to accept optional precomputed candidate embeddings and profile-chunk embeddings to remove repeated per-role compute.
  - **P1**: Make expected-signal threshold configurable in `tuning.yaml` instead of hardcoded `0.50`.
  - **P1**: Add lexical normalization (stemming/symbol cleanup) before substring matching to reduce false negatives.
  - **P2**: Return match provenance per matched skill (`exact`, `substring`, `embedding`) for transparency.

### `matching/confidence.py`
- **Current alignment**: Clear composite confidence structure.
- **Proposals**:
  - **P1**: Incorporate additional factor for evidence density (skill count + source diversity), not only source completeness.
  - **P1**: Add explicit penalty for high disagreement + low overlap scenarios (currently may collapse into moderate).
  - **P2**: Add explanation templates keyed by band/factors for more consistent UI language.

### `matching/skill_graph.py`
- **Current alignment**: Graph caching and hub-skill logic support leverage analysis.
- **Proposals**:
  - **P1**: Optimize connected-component BFS queue from list/pop(0) to deque for scalability.
  - **P1**: Add cache invalidation if taxonomy file mtime/hash changes.
  - **P2**: Persist prebuilt graph artifact optionally to speed cold starts.

### `matching/__init__.py`
- **Current alignment**: Placeholder package marker.
- **Proposals**:
  - **P2**: Export key matching APIs for cleaner import ergonomics.

---

## 4) Analysis subsystem

### `analysis/cross_role.py`
- **Current alignment**: Provides comparative narrative, shared gaps, and leverage ranking.
- **Proposals**:
  - **P0**: Improve fuzzy gap grouping to avoid over-grouping semantically different gaps with similar wording.
  - **P1**: Use role IDs consistently (not names) in internal joins to avoid display-name collision issues.
  - **P1**: Add sensitivity controls for leverage scoring formula in tuning config.
  - **P2**: Add deterministic summary tests with fixture role/gap bundles.

### `analysis/__init__.py`
- **Current alignment**: Placeholder package marker.
- **Proposals**:
  - **P2**: Export stable analysis entrypoints.

---

## 5) Validation scripts

### `scripts/validate_role_taxonomy.py`
- **Current alignment**: Strong governance utility and schema linting.
- **Proposals**:
  - **P1**: Add check for role text redundancy/duplication to prevent taxonomy drift and noisy embedding retrieval.
  - **P1**: Add optional strict mode ensuring each role has at least one domain-differentiating required skill.
  - **P2**: Output machine-readable JSON report for CI integration.

---

## Cross-cutting implementation plan

## Phase A (P0 correctness/alignment)
1. Fix Decision Sprint priority lookup path and deterministic ranking behavior.
2. Add barrier-condition verification logic in gap analyzer prompt + post-check.
3. Introduce precomputed embeddings interface in overlap module and consume from engine.

## Phase B (P1 efficiency/quality)
1. Refactor `skills.py` and `app.py` into smaller modules.
2. Add cache invalidation for taxonomy-dependent caches (`matching/embeddings.py`, `matching/skill_graph.py`).
3. Add deterministic fixture tests for output/cross-role summaries.

## Phase C (P2 maintainability/governance)
1. Improve typed config + error enums.
2. Add CI-friendly lint/test artifacts for taxonomy and output schema.
3. Standardize package exports and docs for module boundaries.

---

## Suggested success metrics
- **Latency**: reduce Stage 3 median wall-time by 20-35% via embedding reuse.
- **Decision quality**: increase agreement between Sprint target role and advisor review set.
- **Gap precision**: lower false-positive gap rate on reviewed runs.
- **Operational robustness**: lower rate of partial-run failures and stale-session UI errors.
