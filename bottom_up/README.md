# Bottom-up AI – Lore Discovery System

## 1. Application Overview

The Bottom-up AI application analyses information from the Elder Scrolls universe using data extracted from the UESP Wiki.

Its purpose is to identify patterns and relationships in the source data, then organise useful findings into a structured knowledge base.

## 2. Current prototype

`bottom_up_ai.py` contains the initial text-pattern and relationship-discovery prototype. It currently uses a small hardcoded list of sentences. It is not yet connected to the SQLite database and its relationship rules are still partly manually specified.

## 3. Testing with real UESP data

A small, committed UESP XML sample is available so development can continue without the full dump.

From the repository root, explicitly run:

```bash
python -m bottom_up.run_sample_import
```

This runs `run_sample_import.py`, which:

- Decodes the small committed UESP sample.
- Uses the existing XML and namespace readers.
- Imports five real UESP pages into a separate SQLite database.
- Stores that database at `data/database/tamriel_sample.db`.

The runner is deliberately separate from `bottom_up_ai.py`. It does not run when the bottom-up module is imported or when the existing prototype is run. It also does not overwrite the main database or `knowledge_base.json`.

The sample database is local generated data and is ignored by Git. Re-running the importer is safe: existing sample pages are not duplicated.


## 4. Sample analysis runner

After importing the sample database, run:

```bash
python -m bottom_up.run_sample_analysis
```

This separate runner reads the five stored pages, analyses their wiki markup, and reports page structure and individual outgoing links. Each link is represented with its source page, destination, destination prefix (when present), and display text.

These are **wiki link references**, not verified semantic relationships. A link from one page to another does not by itself prove that the source page belongs to, describes, or has any other particular relationship with the destination.

The runner does not change the main database, the existing hardcoded demonstration, or `knowledge_base.json`.

## 5. Planned development

The next stages are to test link extraction against a more representative sample of ordinary lore pages, discover recurring patterns across pages, and validate any proposed relationships against source text. Once this works, the same database interface can be used with the full UESP dump.

Potential techniques include:

- Statistical pattern discovery.
- Text similarity and clustering.
- Natural language processing.
- Classification, where useful and testable.

These are planned techniques, not capabilities that the current prototype already provides.

## 6. Testing

The existing pipeline tests use a synthetic XML fixture and a temporary SQLite database. The committed UESP sample runners provide additional manual integration checks against real UESP pages.

The next stages are to connect the bottom-up analysis functions to pages retrieved from the sample database, improve pattern discovery, and test the findings against known examples. Once this works, the same database interface can be used with the full UESP dump.

Potential techniques include:

- Statistical pattern discovery.
- Text similarity and clustering.
- Natural language processing.
- Classification, where useful and testable.

These are planned techniques, not capabilities that the current prototype already provides.

## 5. Testing

The existing pipeline tests use a synthetic XML fixture and a temporary SQLite database. The committed UESP sample runner provides an additional manual integration check against real UESP pages.
