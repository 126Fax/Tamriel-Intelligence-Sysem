# Tamriel Intelligence System

## Project overview

The Tamriel Intelligence System is a Python AI project that explores two cooperating approaches to Elder Scrolls lore from the UESP Wiki:

- **Bottom-up AI:** examines wiki content, identifies recurring features and patterns, and organises knowledge into a structured form.
- **Top-down AI:** interprets a user's question, retrieves relevant facts from that structured knowledge, and produces an answer.

The aim is to build understandable working examples, test them, and gradually connect them. The two systems are not yet fully integrated.

## Current working components

- Compressed MediaWiki XML reading and page import into SQLite.
- A five-page UESP sample import and structural analysis demonstration.
- A bottom-up prototype for basic pattern and relationship exploration.
- A Knowledge Cleaner prototype that reviews candidate facts and records approval, rejection or review decisions.
- A rule-based top-down question-answering prototype using `knowledge_base.json`.
- Automated tests and GitHub Actions CI.

## Quick start

Create and activate the project's single virtual environment, then install
dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `.venv` already exists, activate it rather than creating another one.
See [Development environment](docs/DEVELOPMENT_ENVIRONMENT.md) for setup and
safe duplicate-environment cleanup instructions.

Run the full automated test suite:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Run the bottom-up sample demonstration:

```bash
python -m bottom_up.run_demo
```

The standalone sentence-pattern discovery functions are available from
`bottom_up.pattern_discovery`. They support multi-word variable values,
configurable support thresholds and pattern-specialisation analysis.

Run the Knowledge Cleaner against the generated candidate facts:

```bash
python -m cleaner.run_cleaner
```

The Cleaner reads `knowledge_base.json` without modifying it and writes an auditable review report to `data/cleaner/cleaner_results.json`. See [docs/KNOWLEDGE_CLEANER.md](docs/KNOWLEDGE_CLEANER.md) for its decisions and limitations.

Run the top-down question-answering prototype:

```bash
python -m top_down.chat
```

The top-down prototype currently uses six manually supplied sample facts in `knowledge_base.json`. It can answer the example questions supported by those facts, but it does not yet query all 477,491 pages or automatically use bottom-up discoveries.

## Full UESP data and bottom-up pipeline

The full UESP XML dump is not stored in Git. Keep it locally under `data/raw/`. The full pipeline streams the dump into SQLite, analyses the imported pages, stores extracted links and evidence-backed candidate relationships, and rebuilds `knowledge_base.json` for the top-down prototype.

Run the full workflow:

```bash
python -m bottom_up.run_full_pipeline
```

If the dump is already imported and you only want to rerun bottom-up analysis:

```bash
python -m bottom_up.run_full_pipeline --skip-import
```

See [docs/FULL_DUMP_PIPELINE.md](docs/FULL_DUMP_PIPELINE.md) for the database tables, batch settings and current extraction limits. The committed synthetic fixtures are used for automated tests and do not require the full dump.

## Architecture and next steps

The intended data flow is:

```text
UESP XML
   |
   v
Bottom-up analysis
   |
   v
Structured knowledge + source evidence
   |
   v
Top-down question analysis
   |
   v
Knowledge retrieval
   |
   v
Evidence-based answer
```

The next major milestone is to make bottom-up discoveries produce traceable facts that the top-down system can retrieve, then evaluate both systems against a repeatable test set.

See [top_down/README.md](top_down/README.md) for the current question-answering prototype and [docs/TESTING_AND_DEMO.md](docs/TESTING_AND_DEMO.md) for testing instructions.
