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
- A rule-based top-down question-answering prototype using `knowledge_base.json`.
- Automated tests and GitHub Actions CI.

## Quick start

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the full automated test suite:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Run the bottom-up sample demonstration:

```bash
python -m bottom_up.run_demo
```

Run the top-down question-answering prototype:

```bash
python -m top_down.chat
```

The top-down prototype currently uses six manually supplied sample facts in `knowledge_base.json`. It can answer the example questions supported by those facts, but it does not yet query all 477,491 pages or automatically use bottom-up discoveries.

## Full UESP data

The full UESP XML dump is not stored in Git. Keep it locally under `data/raw/` and use the repository's configuration/import tools to process it. The committed synthetic fixtures are used for automated tests and do not require the full dump.

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
