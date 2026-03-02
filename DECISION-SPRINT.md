# Decision Sprint: 10x Change Write-Up

## One-line concept
Add a **Decision Sprint** card to the output so every user leaves with one prioritized role decision and a concrete 90-day execution plan.

## Why this is a 10x change
The current engine is strong at diagnosis (fit, gaps, leverage), but users can still stall on action. The Decision Sprint converts analysis into a single commitment path:

- **What to pursue now** (role choice)
- **What to fix first** (highest-leverage gaps)
- **What to do this week** (behavioral plan)
- **When to re-evaluate** (go/pivot checkpoint)

This reduces time-to-decision and increases the chance users actually execute on the report.

## User problem statement
"I understand my fit report, but I still don't know what to do first this week."

## Product outcome
After reading results, users should be able to say:
1. The role they are pursuing for the next 90 days.
2. The top two capability gaps they will close first.
3. Their specific weekly execution loop.
4. The date they will decide to continue or pivot.

## Proposed output contract (Decision Sprint card)

### 1) 90-day role bet
- `target_role`: one role from existing ranked outputs
- `rationale`: short explanation grounded in overlap + effort + motivation fit
- `confidence_band`: High / Medium / Low (reuse confidence framework)

### 2) Highest-leverage skill closures
- `skill_1`, `skill_2`
- For each: why this unlocks multiple target roles (cross-role leverage)

### 3) Weekly execution plan (repeatable loop)
- `project_block`: artifact-building task (2–4 hrs/week)
- `market_block`: networking/conversation target (e.g., 3 outreach messages + 1 call)
- `pipeline_block`: applications/case prep cadence

### 4) Go/Pivot checkpoint
- `checkpoint_date`: default now + 4 weeks
- `go_criteria`: measurable signs to continue
- `pivot_criteria`: measurable signs to switch to backup role

## Data mapping (reuse existing pipeline outputs)
No new upstream extraction needed.

- **Role choice input**: Sections 4 and 7 (win-now roles, effort ranking)
- **Gap prioritization input**: Sections 5 and 7 (gap severity + shared gaps)
- **Leverage rationale input**: Section 6 (leverage moves)
- **Motivation guardrail input**: Section 3 (motivation profile)

## Scoring logic (deterministic first)
Use a simple deterministic score for target role selection:

`decision_score = 0.45 * fit_score + 0.30 * confidence_score + 0.25 * (1 - effort_rank_norm)`

Then apply a motivation guardrail:
- If role conflicts with top motivational constraints, downgrade one rank and promote next candidate.

For top-2 skill closures:
- Rank missing skills by `gap_severity * cross_role_frequency * leverage_weight`.

## UX placement
- Render Decision Sprint **after** existing recommendations as a final “Now act” block.
- Keep card compact and scannable (4 numbered sections, max ~12 lines before optional expanders).

## Implementation plan (same-day shippable)
1. **Output synthesis** (`output.py`)
   - Add a `build_decision_sprint(result_bundle)` formatter.
   - Read existing structured outputs, compute deterministic selections, emit a normalized dict.
2. **UI render** (`app.py`)
   - Add `render_decision_sprint(card)` directly after current recommendation sections.
   - Include copy-to-clipboard text block for accountability.
3. **Config knobs** (`tuning.yaml`, optional)
   - Add decision weights and checkpoint interval days.
4. **Telemetry hooks** (lightweight)
   - Log selected role, selected skills, and confidence band for later calibration.

## Acceptance criteria
- Card appears on every successful run.
- Card references only roles and skills present in the computed outputs.
- If confidence is low, card explicitly says "explore" instead of "commit".
- User can copy a one-paragraph action plan in one click.

## Success metrics
### Product metrics
- ≥80% of pilot users can restate their next 7-day plan without prompting.
- Self-reported "I know what to do next" increases vs. baseline report.

### Behavioral metrics
- Increase in follow-up sessions with updated resume/why statement within 2–4 weeks.
- Reduction in "analysis-only" sessions with no downstream action notes.

## Risks and mitigations
- **Risk:** Overconfident recommendation when data quality is weak.
  - **Mitigation:** confidence-aware language and explicit explore mode.
- **Risk:** Advice feels generic.
  - **Mitigation:** force card content to cite role-specific gaps and leverage skills.
- **Risk:** Added complexity in UI.
  - **Mitigation:** one compact card, no extra navigation.

## Rollout
- Phase 1: deterministic version only (no additional LLM step).
- Phase 2: optional short polish pass for language quality.
- Phase 3: calibrate weights from observed user outcomes.

## Non-goals (for this iteration)
- No new role taxonomy expansion.
- No new data collection forms.
- No personalized labor-market salary/location modeling.
