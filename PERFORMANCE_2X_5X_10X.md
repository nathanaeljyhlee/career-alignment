# Performance Plan: 2x / 5x / 10x Speed + Efficiency (No Functionality Regression)

This document identifies practical ways to improve runtime and resource efficiency while preserving current output quality and behavior.

## Baseline hotspots observed

- **LLM calls dominate latency** in skill extraction, inference, profile/motivation/role/gap agents via `ollama.chat(...)`. 
- **Embedding calls** are repeated across pipeline stages (`skills.py`, `matching/embeddings.py`) and can become expensive when repeated across runs.
- **Graph build is done per run** in Stage 1 (`build_skill_graph()`), though source taxonomy is mostly static.
- **Role ranking uses full sort** over all similarities instead of partial top-k selection.
- **Alias matching + O*NET id lookup** does nested loops for each alias hit.

---

## 2x improvements (low risk, fast to implement)

1. **Cache skill graph across runs (module-level singleton)**
   - Build once at process start or lazy-init on first request, then reuse.
   - Current behavior rebuilds each pipeline run in `stage_1_input_processing`.
   - Expected impact: notable startup reduction per run when graph build is non-trivial.

2. **Use `np.argpartition` for top-k role retrieval instead of full `argsort`**
   - In `matching/embeddings.py`, replace full descending sort with partial top-k selection + local sort.
   - Keeps exact same result set for top-k, lower CPU for larger taxonomy.

3. **Precompute O*NET `skill_name -> skill_id` map once**
   - In `skills.py::extract_by_alias`, current approach scans full O*NET list per alias match.
   - Replace with cached dict lookup to remove inner-loop scan.

4. **Memoize prompt-invariant reads from `get_tuning(...)`**
   - Multiple stages repeatedly fetch same config keys in hot paths.
   - Pull once per function invocation, pass downstream.

5. **Skip expensive inference steps under safe conditions**
   - Keep behavior-equivalent gate: if alias+LLM already extracted high-confidence dense skills above threshold, skip graph/taxonomy inference.
   - Guard behind tuning flags so default behavior can remain unchanged.

---

## 5x improvements (moderate refactor, high ROI)

1. **Persistent embedding cache (disk-backed)**
   - Cache embeddings by key `(model_name, normalized_text_hash)`.
   - Apply to:
     - O*NET skill embeddings in `skills.py`
     - Role taxonomy embeddings in `matching/embeddings.py`
     - Candidate profile text embeddings (short TTL is fine)
   - Reuse across process restarts using `npz`/SQLite/LMDB.

2. **Parallelize independent Stage 2 agent calls**
   - `synthesize_profile(...)` and `extract_motivation(...)` are independent once Stage 1 completes.
   - Run concurrently with threadpool or async request fan-out to Ollama.
   - Same outputs; lower wall-clock latency.

3. **Parallelize Agent 3 / Agent 4 where dependency allows**
   - If gap analysis can rely on pre-match + profile/skills without waiting for full Agent 3 reasoning (or only needs selected fields), compute compatible parts concurrently.
   - Otherwise parallelize per-role computations inside each agent.

4. **Add run-level artifact reuse for repeated uploads**
   - Hash resume/linkedin PDFs + WHY text; if identical and tuning/model versions match, return cached run artifacts.
   - Provides huge speedup for iterative UI exploration.

5. **Structured batching for LLM role analysis prompts**
   - Instead of many serial per-role calls, batch role comparisons in fewer prompts where token budget allows.
   - Preserve schema and reasoning fields; test for output parity.

---

## 10x improvements (architecture-level; staged rollout)

1. **Split pipeline into online/offline compute**
   - Offline: precompute and version role, skill, and graph assets.
   - Online: only parse docs, compute candidate embedding, do narrow LLM reasoning.
   - Minimizes repeated heavy preparation work.

2. **Introduce two-tier model routing with confidence guardrails**
   - Fast small model for first-pass extraction/comparison.
   - Escalate to larger model only for low-confidence or ambiguous cases.
   - Maintain quality by routing fallback rather than replacing all calls.

3. **Move to retrieval-first role reasoning with compact evidence packs**
   - Replace full-text prompt context with deterministic evidence snippets + compact structured features.
   - Shrinks prompt tokens substantially, reducing both latency and cost.

4. **Async job queue + streaming updates**
   - For multi-user reliability, queue heavy LLM work and stream stage updates to UI.
   - Increases throughput and avoids contention/timeouts under load.

5. **Evaluation harness for non-regression + performance budgets**
   - Golden dataset of resumes/LinkedIns/WHY statements.
   - Enforce output-equivalence tolerances and stage SLA budgets in CI.
   - Makes aggressive optimization safe and repeatable.

---

## Recommended implementation order

1. Top-k partial sort + O*NET map cache + graph singleton.
2. Persistent embedding cache.
3. Stage 2 concurrency.
4. Reuse artifacts for duplicate inputs.
5. Retrieval-first prompt compaction + model routing.

## Metrics to track

- End-to-end p50/p95 runtime per run.
- Stage-level timings (`input_processing`, `profile_synthesis`, `role_matching`).
- Number of Ollama chat calls and total prompt/completion tokens.
- Cache hit rates (embedding cache, run artifact cache).
- Output parity vs. baseline (fit bands, top roles, key gaps).
