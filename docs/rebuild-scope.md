# Career Alignment Engine — 10x Rebuild Scope

## 0) Goal of the Rebuild
Rebuild the product from first principles to make it **10x more effective** on three dimensions:
1. **Decision quality:** recommendations are measurably better and more reliable.
2. **User outcomes:** users get to interviews/offers faster via action plans and tracking.
3. **Operating leverage:** data, evaluation, and iteration loops are built-in so the system improves every week.

The current version demonstrates a thoughtful pipeline and strong local-first foundation, but a 10x version should shift from a "single-run analyzer" to an **adaptive career copilot platform**.

---

## 1) Product Scope (What to Build)

### A. Core user jobs
- **Diagnose fit now** (what roles are realistic immediately).
- **Design pivot path** (what skills/signals to build in 30/60/90 days).
- **Execute applications** (resume bullets, stories, networking targets, interview prep).
- **Track progress** (did fit improve after actions).

### B. Product surfaces
1. **Intake + Profile Graph**
   - Resume/LinkedIn import, transcript/coursework import, optional work samples.
   - Structured candidate graph (skills, experiences, evidence snippets, quantified outcomes).
2. **Role Intelligence Hub**
   - Unified role ontology with variants by region/seniority/company stage.
   - Required/preferred skills, proof signals, compensation bands, hiring velocity signals.
3. **Fit & Trajectory Engine**
   - Role fit score + confidence + explainability.
   - Counterfactual simulator ("if I add X project/certification, how does fit shift?").
4. **Action Planner**
   - 90-day plan with weekly goals and evidence checkpoints.
   - Output assets: resume deltas, outreach targets, interview story drills.
5. **Progress Loop**
   - Users log actions; system recalculates fit and ROI by action type.

### C. User outcomes to optimize
- Time to first interview.
- Interview conversion rate.
- Offer probability uplift.
- User-reported clarity and confidence.

---

## 2) Technical Scope (How to Build It)

### A. Architecture principles
- **Separation of concerns:** UI, orchestration, feature computation, model inference, and evaluation services are independent.
- **Event-driven pipeline:** each transformation emits typed events (ingestion, extraction, scoring, plan generation).
- **Version everything:** model versions, taxonomy versions, prompt versions, feature schema versions.
- **Observability-first:** every recommendation is reproducible with lineage.

### B. Proposed service map
1. **Ingestion Service**
   - Document parsing, OCR fallback, section detection, normalization.
2. **Profile Feature Service**
   - Candidate knowledge graph builder (skills, experiences, impact claims, evidence confidence).
3. **Role Knowledge Service**
   - Taxonomy API + governance workflows + versioned role definitions.
4. **Matching Service**
   - Hybrid retriever + scorer stack (rules + embeddings + calibrated ML).
5. **Planning Service**
   - Generates intervention plans and predicts marginal fit gain.
6. **Evaluation Service**
   - Offline eval sets + online outcome tracking + drift alerts.
7. **Experience API + Frontend**
   - Session state, recommendations, explanations, task tracking.

### C. Data model (minimum)
- `candidate_profile` (normalized entities + evidence links).
- `role_definition` (requirements + signal weights + constraints).
- `fit_assessment` (score components + confidence + explanation artifacts).
- `action_plan` (recommended interventions + expected uplift).
- `outcome_event` (application/interview/offer results).

---

## 3) Intelligence Scope (Modeling Strategy)

### A. Move from prompt-only to hybrid decision stack
- Deterministic features for reliability (skill coverage, tenure evidence, role constraints).
- Embedding retrieval for candidate-role semantic proximity.
- LLM reasoning only where needed (explanations, synthesis, plan narration).
- Calibrated meta-model on top for final fit probability + uncertainty.

### B. Evidence and attribution
- Every recommendation must include:
  - top supporting evidence snippets,
  - missing evidence,
  - assumptions made,
  - confidence decomposition.

### C. Continuous learning loop
- Capture user feedback (accepted/rejected suggestions).
- Capture downstream outcomes (interviews/offers).
- Retrain calibration/ranking models on real outcomes.

---

## 4) Evaluation Scope (What "10x better" means)

### A. Offline evaluation
- Gold-labeled benchmark: historical candidate-role pairs with outcomes.
- Metrics:
  - Top-k role precision/recall.
  - Calibration error (predicted fit vs observed success).
  - Explanation faithfulness checks.
  - Gap recommendation usefulness (expert rubric).

### B. Online evaluation
- A/B test against current baseline:
  - Activation rate.
  - Plan completion.
  - Interview/offer lift.
  - Retention over 4–8 weeks.

### C. Reliability targets
- Deterministic pipeline success > 99%.
- P95 latency budget per full run.
- Controlled fallback behavior when model services fail.

---

## 5) UX Scope (Experience Redesign)

### A. Decision-centric interface
- Replace long static report with:
  1. **Best next role now**,
  2. **Best pivot role**,
  3. **Single highest-ROI skill to build next**.

### B. Actionable outputs
- Weekly checklist and due dates.
- Auto-generated networking list and messaging drafts.
- Interview story prompts linked to identified evidence gaps.

### C. Trust layer
- Show why recommendation changed over time.
- Show confidence and what would increase it.

---

## 6) Delivery Scope (Phased Plan)

### Phase 1 (0–6 weeks): Foundation Rebuild
- New service boundaries + typed contracts.
- Candidate graph and role knowledge APIs.
- Eval harness + baseline benchmark set.

### Phase 2 (6–12 weeks): Matching v2 + Explainability
- Hybrid scoring and calibration layer.
- Evidence attribution and confidence breakdowns.
- Internal reviewer tools for quality QA.

### Phase 3 (12–18 weeks): Planning + Outcome Loop
- 90-day action planner with expected uplift.
- Progress tracker and fit re-simulation.
- Outcome ingestion (applications/interviews/offers).

### Phase 4 (18–24 weeks): Optimization & Scale
- Active-learning loop.
- Cost/latency optimization and caching.
- Role ontology expansion with governance automation.

---

## 7) Team Scope
Minimum cross-functional team for 6 months:
- 1 product lead (career outcomes + experiments).
- 1 domain lead (career coaching/recruiting operations).
- 2 backend/platform engineers.
- 1 ML engineer (ranking/calibration/evals).
- 1 frontend engineer.
- 1 design/research contributor (part-time acceptable).

---

## 8) Key Risks and Mitigations
- **Risk:** taxonomy staleness.
  - **Mitigation:** versioned ontology + monthly review cadence + telemetry-driven updates.
- **Risk:** LLM hallucinated rationale.
  - **Mitigation:** evidence-locked explanation templates and faithfulness checks.
- **Risk:** high confidence on weak data.
  - **Mitigation:** hard uncertainty penalties and minimum-evidence thresholds.
- **Risk:** low user follow-through.
  - **Mitigation:** progress nudges, weekly plans, and outcome feedback loops.

---

## 9) Explicit Non-Goals for V1 Rebuild
- Full ATS/job-board integrations.
- Automated application submission.
- Multi-language support.
- Enterprise org admin tooling.

---

## 10) Definition of Success (6-month checkpoint)
The rebuild is successful if it achieves all of:
1. Statistically significant improvement in interview conversion over baseline cohort.
2. Calibrated fit scoring with low error on held-out outcome data.
3. Most users complete at least one high-ROI action plan cycle.
4. Product and model teams can ship weekly quality improvements through eval-driven iteration.
