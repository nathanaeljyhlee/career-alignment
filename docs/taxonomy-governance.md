# Role Taxonomy Governance Workflow

This workflow governs all edits to `data/role_taxonomy.json` to prevent regressions like CMF-004 (generic role definitions over-matching non-target candidates).

## 1) Validation Gate (Schema + Lint)

Run this before every taxonomy PR and after rebasing:

```bash
python scripts/validate_role_taxonomy.py
```

What this checks:

- **Schema shape**
  - Required top-level keys exist (`version`, `created`, `description`, `roles`).
  - Every role entry includes required fields (`role_id`, `role_name`, required/preferred skills, barriers, expected signals, motivation, BLS block).
  - Canonical schema is stored in `data/role_taxonomy.schema.json`.
- **Role completeness**
  - `required_skills`, `barrier_conditions`, and `expected_signals` are all non-empty.
- **Domain-signal quality lint**
  - Each role has **at least one domain-distinguishing required skill or expected signal**.
  - Barrier conditions are **non-generic** (not template placeholders; sufficiently specific).
  - `expected_signals` are **testable against profile evidence** (e.g., prior experience, portfolio, track record, certifications).

If the command fails, do not merge taxonomy changes until all errors are resolved.

## 2) Role Review Checklist (Required in PR Description)

For every new or edited role, reviewers must verify all three checks below explicitly:

- [ ] At least one **domain-distinguishing** required skill or expected signal is present.
- [ ] Barrier conditions are **non-generic** and reflect role-specific disqualifiers.
- [ ] Every `expected_signal` can be evaluated from candidate profile evidence (resume/LinkedIn/projects/certs/outcomes).

Recommended reviewer prompts:

1. "Would a generalist profile pass this role with only transferable leadership/communication skills?" If yes, tighten domain filters.
2. "Could this barrier apply to nearly every role in the taxonomy?" If yes, rewrite with role context.
3. "Can I point to concrete profile evidence that would satisfy/fail each signal?" If no, make the signal observable.

## 3) Cohort-Based Review Process

Every taxonomy edit must be reviewed in at least one cohort lens, and major role additions should cover all three:

1. **Clinical pivot cohort** (e.g., physician → healthtech/consulting)
   - Validate that healthcare domain requirements are explicit.
   - Confirm clinical experience is recognized as positive evidence where relevant.
2. **Public sector cohort** (e.g., government/nonprofit candidates)
   - Validate public-service constraints and civic-domain signals are not genericized.
   - Check that public-sector roles do not over-rank private-sector profiles without domain evidence.
3. **Tech PM cohort** (e.g., product/technical program track)
   - Ensure product/technical fluency signals are required or strongly expected.
   - Confirm role barriers filter out non-technical profiles unless explicitly pivot-friendly.

### Cohort review mechanics

- Use at least one representative historical profile (or fixture) per cohort when available.
- Record pass/fail notes for each edited role under a `Taxonomy Governance` section in the PR.
- Any cohort failure blocks merge until role wording/skills/signals are updated and revalidated.

## 4) Merge Criteria

A taxonomy PR is merge-ready only when:

1. `python scripts/validate_role_taxonomy.py` passes.
2. Review checklist is completed for every changed role.
3. Cohort review notes are attached and no blocking failures remain.

This process is mandatory for all future role additions and edits.
