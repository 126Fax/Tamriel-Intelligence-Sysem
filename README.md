# Tamriel Intelligence System

## Project overview

The Tamriel Intelligence System is a Python project for answering questions
about the Elder Scrolls universe using information originating from the UESP
Wiki.

The current development focus is the **Top-Down AI**: a user asks a question,
the system analyses what is being requested, retrieves relevant facts from a
knowledge base and produces a readable response.

## Current AI application

The working Top-Down AI is a rule-based question-answering application with
three main stages:

1. Question analysis.
2. Knowledge-base retrieval.
3. Answer generation.

To start it from the repository root:

```bash
python -m top_down
```

To run its tests:

```bash
python -m unittest discover -s tests -v
```

The current knowledge base is a small demonstration dataset in
`knowledge_base.json`. It is not yet a complete representation of UESP lore.

## Project structure

- `top_down/` — the question-answering application.
- `knowledge_base.json` — the current structured demonstration facts.
- `docs/AI_SYSTEM.md` — documentation for the AI design and data flow.
- `src/ingestion/` — code for reading the source XML dump.
- `src/database/` — SQLite storage and retrieval foundations.
- `src/analysis/` — utilities for inspecting page and wiki-markup structure.
- `tests/` — automated tests.

## Source data

The full UESP XML dump is not stored in Git. Its local path is configured in
`config/local.py` using `XML_DUMP_PATH`. The repository's ingestion code
extracts page information and stores it in SQLite. That data-preparation
pipeline supports the project but is separate from the current Top-Down AI
question-answering stages.

For the AI architecture, setup, operation, tests and limitations, see
[AI system documentation](docs/AI_SYSTEM.md).
