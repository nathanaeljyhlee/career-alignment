# Career Alignment Engine

A local, privacy-first AI system that analyzes a candidate's resume and professional narrative against a structured role taxonomy to produce fit scores, gap analysis, and strategic career recommendations.

Built as part of the Babson College MBA AI Fellowship.

---

## What It Does

Upload a resume (PDF) and write a brief "why" statement. The engine runs a 3-stage pipeline:

1. **Input Processing** — Extracts skills via alias matching, LLM extraction, transferable language translation, and O*NET normalization. Builds a co-occurrence skill graph to infer skills demonstrated but not explicitly stated.
2. **Profile Synthesis** — Two LLM agents produce a structured skill cluster profile and a 7-dimension motivational profile from the why statement.
3. **Role Matching** — Deterministic skill overlap scoring (with expected-signal coverage penalty) anchors LLM fit classification. Two more agents run self-consistency role comparison and gap severity analysis. A cross-role analysis identifies shared gaps, leverage skills, and effort-to-fit rankings.
4. **Output Assembly** — Structured result assembled and rendered as 7 report sections in the UI; exportable as PDF.

Output: 7 sections covering skill profile, motivation fit, win-now roles, pivot roles, gap analysis, leverage moves, and a cross-role comparative summary.

---

## Architecture

```
Streamlit UI (app.py)
  |
Pipeline Orchestrator (engine.py)
  |
  +-- Stage 1: Input Processing
  |     parsers.py (pdfplumber)
  |     skills.py (alias + LLM + O*NET/FAISS normalization)
  |     matching/skill_graph.py (co-occurrence graph, hub skill inference)
  |
  +-- Stage 2: Profile Synthesis
  |     agents/profile_synthesizer.py  (skill clusters, coherence score)
  |     agents/motivation_extractor.py (7 motivational dimensions)
  |
  +-- Stage 3: Role Matching
        matching/embeddings.py    (nomic-embed-text pre-match, top-K retrieval)
        matching/skill_overlap.py (deterministic overlap per role)
        agents/role_comparator.py (3x self-consistency, fit bands)
        agents/gap_analyzer.py    (gap severity, pivot viability, leverage moves)
        matching/confidence.py    (composite confidence bands)
        analysis/cross_role.py    (shared gaps, leverage skills, effort ranking)
```

**Models:** All inference runs locally via [Ollama](https://ollama.ai). No data leaves your machine.
- LLM agents: `qwen2.5:7b` (swap to `phi4:14b` for stronger reasoning)
- Embeddings: `nomic-embed-text`

**Data:** 20 MBA-relevant roles (O*NET-grounded, expanding to 80 via CMF-037), 483 canonical skills, 1,832 surface-form aliases.

---

## Setup

**Prerequisites:**
- Python 3.10+
- [Ollama](https://ollama.ai) installed and running
- Required models pulled:

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

**Install dependencies:**

```bash
pip install -r requirements.txt
```

**Run:**

```bash
streamlit run app.py
```

---

## Configuration

All scoring parameters are in `tuning.yaml` — weights, thresholds, model names, and parallel worker counts. Inline comments explain every parameter. No code changes needed for parameter tuning.

---

## Project Structure

```
candidate-market-fit/
├── app.py                    # Streamlit UI
├── config.py                 # Path config + tuning.yaml loader
├── engine.py                 # Pipeline orchestrator (4 stages, auto-logging)
├── output.py                 # Result formatter (7 sections)
├── parsers.py                # PDF parsing (pdfplumber)
├── pdf_export.py             # PDF export from output dict
├── skills.py                 # Skill extraction + O*NET normalization + transfer labels
├── tally_intake.py           # CLI: pull Tally form submissions, run pipeline
├── tuning.yaml               # All tunable parameters
├── requirements.txt
├── agents/
│   ├── profile_synthesizer.py
│   ├── motivation_extractor.py
│   ├── role_comparator.py
│   └── gap_analyzer.py
├── matching/
│   ├── embeddings.py
│   ├── skill_overlap.py      # Includes expected_signal_coverage penalty
│   ├── skill_graph.py
│   └── confidence.py
├── analysis/
│   └── cross_role.py
├── scripts/
│   └── validate_role_taxonomy.py  # Schema + governance lint
├── docs/
│   └── taxonomy-governance.md
└── data/
    ├── role_taxonomy.json         # 20 MBA roles (expanding to 80)
    ├── role_taxonomy.schema.json  # JSON schema for validation
    ├── onet_skills.json           # 483 canonical skills
    └── skill_aliases.json         # 1,832 surface-form mappings
```

---

## Status

Active development. Pipeline is functional and has been validated on multiple real user profiles including a non-builder (clinical-to-MBA pivot candidate). All core Must items from initial build are resolved.

**Full feature roadmap:** [`feature-roadmap.csv`](feature-roadmap.csv) — MoSCoW prioritized.

Current focus:
- **CMF-037** — Expand role taxonomy from 20 to 80 roles (internship / FT tracks, MBA-specific, Babson entrepreneurial)
- **CMF-038** — Decision Sprint output card (converts fit analysis to a 90-day action commitment)
- **CMF-039 / 040** — Performance: skill graph caching + Stage 2 parallelization

---

## License

Copyright (c) 2026 Nathanael Lee. All rights reserved.

Source code is publicly available for reference and educational purposes. Commercial use, redistribution, or derivative works require explicit written permission.
