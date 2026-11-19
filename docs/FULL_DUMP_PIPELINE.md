# Full UESP import and bottom-up analysis

The full XML dump stays local in `data/raw/`; it is not committed to Git.
The importer streams the compressed XML and stores each page's title, page ID,
namespace, revision ID and original wiki text in the local SQLite database at
`data/database/tamriel_intelligence.db`.

## Run the complete pipeline

From the repository root in Codespaces:

```bash
python -m pip install -r requirements.txt
python -m bottom_up.run_full_pipeline
```

The command imports the dump (re-imports are idempotent), analyses the pages
already imported, and rebuilds `knowledge_base.json`.

If the dump has already been imported and you only want to rerun analysis:

```bash
python -m bottom_up.run_full_pipeline --skip-import
```

The default import batch size is 2,500, matching the fastest setting in the
current benchmark. Analysis uses smaller batches to keep memory use controlled.
Use `--batch-size` and `--analysis-batch-size` to tune them.

## What is stored

| SQLite table | Purpose |
|---|---|
| `source_dumps` | Original dump and import status |
| `pages` | Full imported wiki page text and metadata |
| `page_analysis` | Template, link, heading and tag counts |
| `page_links` | Source page and each extracted wiki link |
| `candidate_facts` | Explicit relationship candidates with source evidence |

The generated `knowledge_base.json` contains the subject, relationship, object,
source page ID/title, evidence sentence, extraction method and confidence.

## Important limits

This is the first full-dump analysis engine, not general semantic understanding.
It extracts wiki structure and a deliberately small set of explicit sentence
patterns (province, lives in, located in). A wiki link is recorded as a link,
not assumed to mean a relationship. Candidate facts are evidence-backed
extractions, not independently verified lore. The top-down system can retrieve
the generated triples, but its question analyser still supports only a limited
set of question forms.

Analysis is repeatable: rerunning it rebuilds derived analysis rows for the
selected dump without deleting or reimporting the original page records.
