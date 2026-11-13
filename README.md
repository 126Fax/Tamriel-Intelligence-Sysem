# Tamriel Intelligence System

A Python project exploring two cooperating AI approaches to Elder Scrolls lore using the UESP Wiki as its source of information.

## Architecture

- **Bottom-Up AI:** examines source material, discovers recurring patterns and proposes structured knowledge for human review.
- **Top-Down AI:** interprets questions and uses the organised knowledge to retrieve evidence and produce answers.

The two systems share the same source data, but have different responsibilities. A wiki link is recorded as a reference; it is not automatically treated as proof of a semantic relationship.

## Current foundations

- Read compressed MediaWiki XML exports.
- Extract the latest revision of each page.
- Read MediaWiki namespace definitions.
- Store page metadata and original page text in SQLite.
- Retrieve pages using basic title and text keyword search.
- Split large XML exports at complete page boundaries.
- Prepare a separate AI-readable representation containing readable text, headings, templates, links, categories and external links.
- Keep a small synthetic XML fixture and a five-page UESP sample for repeatable testing.

The original imported page text remains separate from the AI-readable representation. The preparation step does not overwrite the source page.

## Project layout

- `src/ingestion/`: XML and namespace readers.
- `src/database/`: SQLite connection, schema and database operations.
- `src/analysis/`: early page and content analysis utilities.
- `src/processing/`: AI-readable data preparation.
- `bottom_up/`: Bottom-Up AI prototype and workflow runners.
- `top_down/`: Top-Down AI prototype.
- `tools/`: reusable command-line tools, including the XML splitter.
- `tests/`: automated tests and test fixtures.
- `data/`: sample data and local generated data.

See [the data guide](data/README.md) and [the AI development plan](docs/AI_DEVELOPMENT_PLAN.md) for more detail.

## Setup

Use Python 3.10 or newer and install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

The full UESP dump and generated databases are local data and must not be committed to Git. Set `XML_DUMP_PATH` in the ignored `config/local.py` file to point to the original dump on your computer.

## Important data behaviour

The current XML ingestion reader stores the **latest revision** of each page. It does not retain the full revision history. The splitter, however, keeps complete page elements and their revisions intact in its output parts.

## Development approach

Keep the data pipeline reliable but proportionate. Once the shared foundations are stable, most development effort should go into the Bottom-Up and Top-Down AI behaviours, their evaluation, and the evidence supporting their results.

Automated tests use synthetic fixtures and temporary databases. The full-dump workflow should be tested locally before relying on it for a complete import.
