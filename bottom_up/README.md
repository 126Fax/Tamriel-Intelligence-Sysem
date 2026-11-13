# Bottom-Up AI – Lore Discovery System

## Purpose

The Bottom-Up AI examines UESP content to discover recurring patterns and propose structured knowledge. Findings must be traceable to source pages and reviewed before being treated as accepted knowledge.

A wiki link is only a reference between pages. It does not, by itself, establish a semantic relationship.

## Current prototype

`bottom_up_ai.py` contains an early text-pattern and relationship-discovery demonstration using a small hardcoded set of sentences. It is not yet connected to the full SQLite dataset.

## Sample workflow

A five-page UESP sample is committed so development and analysis can be repeated without importing the full dump.

From the repository root:

```bash
python -m bottom_up.run_sample_import
python -m bottom_up.run_sample_analysis
```

The sample importer writes to `data/database/tamriel_sample.db`, leaving the main database untouched. The analysis runner reports page structure and outgoing wiki-link references.

## Full-dump data workflow

The full XML dump is kept locally and is not committed to Git.

Split the dump at complete page boundaries:

```bash
python -m tools.split_mediawiki_dump --input /path/to/uesp_dump.xml.bz2
```

Import all parts as one source dump:

```bash
python -m bottom_up.run_split_dump_import --manifest data/processed/<dump-name>/manifest.json
```

Prepare the imported pages for downstream AI components:

```bash
python -m bottom_up.run_data_preparation
```

The preparation process preserves the original page records and creates separate AI-readable records containing readable text, headings, templates and parameters, wiki links, categories and external links. It does not decide what a link means, approve discoveries or train a model.

See [the data guide](../data/README.md) for the full workflow and local-data rules.

## Development direction

The next Bottom-Up AI work should focus on a narrow, testable discovery task:

1. Read prepared pages from the database.
2. Identify repeated structures or candidate patterns.
3. Record the source pages and text supporting each finding.
4. Present discoveries for human review.
5. Evaluate how often proposed findings are correct.

Potential techniques include statistical pattern discovery, text similarity, clustering and classification. These are options to investigate, not capabilities already implemented.

## Testing

Automated tests use synthetic XML fixtures and temporary databases. The five-page UESP sample provides an additional manual integration check. The full-dump workflow and its performance still need to be tested in the local project environment before being relied upon for a complete import.
