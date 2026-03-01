# Career Alignment Engine

A local, privacy-first AI system that analyzes a candidate's resume and professional narrative against a structured role taxonomy to produce fit scores, gap analysis, and strategic career recommendations.

Built as part of the Babson College MBA AI Fellowship.

---

## What It Does

Upload a resume (PDF) and write a brief "why" statement. The engine runs a 3-stage pipeline:

1. **Input Processing** — Extracts skills via alias matching, LLM extraction, and O*NET normalization. Builds a co-occurrence skill graph to infer skills demonstrated but not explicitly stated.
2. **Profile Synthesis** — Two LLM agents produce a structured skill cluster profile and a 7-dimension motivational profile from the why statement.
3. **Role Matching** — Deterministic skill overlap scoring anchors LLM fit classification. Two more agents run self-consistency role comparison and gap severity analysis. A cross-role analysis identifies shared gaps, leverage skills, and effort-to-fit rankings.

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

**Data:** 18 MBA-relevant roles (O*NET-grounded), 98 standardized skills, 185 surface-form aliases.

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
├── engine.py                 # Pipeline orchestrator (3 stages, auto-logging)
├── output.py                 # Result formatter (7 sections)
├── parsers.py                # PDF parsing (pdfplumber)
├── skills.py                 # Skill extraction + O*NET normalization
├── tuning.yaml               # All tunable parameters
├── requirements.txt
├── agents/
│   ├── profile_synthesizer.py
│   ├── motivation_extractor.py
│   ├── role_comparator.py
│   └── gap_analyzer.py
├── matching/
│   ├── embeddings.py
│   ├── skill_overlap.py
│   ├── skill_graph.py
│   └── confidence.py
├── analysis/
│   └── cross_role.py
└── data/
    ├── role_taxonomy.json    # 18 MBA roles
    ├── onet_skills.json      # 98 O*NET skills
    └── skill_aliases.json    # 185 surface-form mappings
```

---

## Status

Active development. Current focus: calibration and quality validation.

Planned additions:
- PDF export of candidate report
- Gap-based follow-up questions (interactive clarification)
- Internship vs. full-time toggle prominence
- Role selection from taxonomy list (vs. free text)
- Skill extraction observability (show match method per skill)

---

## License

Copyright (c) 2026 Nathanael Lee. All rights reserved.

Source code is publicly available for reference and educational purposes. Commercial use, redistribution, or derivative works require explicit written permission.
