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

## AI-readable data preparation pipeline

The original imported pages remain in the `pages` table. The preparation pipeline
reads those records and writes a separate representation to `ai_pages`; it does
not rewrite the original wiki text.

From the repository root, after importing a dump:

```bash
python -m bottom_up.run_data_preparation
```

By default, this prepares the latest completed source dump. You can select a
specific dump and change the batch size:

```bash
python -m bottom_up.run_data_preparation --dump-id 1 --batch-size 250
```

To rebuild the prepared representation with the current parser:

```bash
python -m bottom_up.run_data_preparation --dump-id 1 --force
```

The pipeline stores:

- Readable text with common wiki markup removed.
- Headings and their levels.
- Templates and their parameters, including raw and readable parameter values.
- Wiki links, destinations and display text.
- Category names.
- External links.
- Source dump, page and revision identifiers.
- A SHA-256 hash of the original page text and the parser version.

JSON fields are stored as JSON text in SQLite and decoded into Python lists and
dictionaries by the retrieval functions. Prepared pages can be read using
`get_prepared_page()` or streamed using `iter_prepared_pages()` from
`src.processing.ai_preparation`.

Preparation is incremental: pages already prepared with the current processor
version are skipped. Processing uses bounded batches, and each completed batch
is committed independently. This allows a failed run to be resumed without
starting from the beginning. Use `--force` to rebuild existing records.

The pipeline deliberately does not decide what a link means, infer semantic
relationships, classify entities, train a model or approve knowledge. Those
are responsibilities of the Bottom-Up AI that will be built on top of this
prepared dataset.

## Splitting a full UESP XML dump

Large dumps do not need to be committed to Git. Keep the original dump on your
computer and use the splitter to create smaller, valid MediaWiki XML documents.
The source file is never modified, and pages (including their revisions,
templates and wiki markup) are kept intact.

The splitter supports plain XML, gzip and bzip2 input. It writes bzip2-compressed
parts and a `manifest.json` describing the source and every part.

From the repository root:

```bash
python -m tools.split_mediawiki_dump --input /path/to/uesp_dump.xml.bz2
```

By default, parts are written under `data/processed/<dump-name>/` with an
approximate uncompressed page-data limit of 90 MB per part. You can choose a
different output directory or size:

```bash
python -m tools.split_mediawiki_dump \
  --input /path/to/uesp_dump.xml.bz2 \
  --output-dir data/processed/uesp \
  --max-size-mb 90
```

The size limit is measured using the uncompressed serialized page XML. This
keeps a safety margin below GitHub's 100 MB per-file limit; a single unusually
large wiki page is never cut in half and may exceed the requested limit.

The generated parts can be read by the existing bzip2 MediaWiki ingestion
reader. Importing all parts into one source-dump record is the next integration
step; do not treat separate parts as separate knowledge sources.
