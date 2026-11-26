# Tamriel Intelligence System — Rust implementation

This is the Rust implementation of the project, kept in `rust-version/` while
the migration is in progress. It does not share the Python database or
overwrite the Python `knowledge_base.json`.

## Pipeline

```text
UESP compressed MediaWiki XML
          |
          v
  Streaming XML ingestion
          |
          v
  Rust SQLite source database
          |
          v
  Bottom-Up wiki analysis
  - templates and parameters
  - internal wiki links
  - headings and tags
  - explicit relationship candidates
  - source page and evidence retained
          |
          v
  Candidate fact database
          |
          +--> Optional AI-readable page preparation
          |    (separate resumable derived table)
          |
          v
  Knowledge-base JSON export
          |
          v
  Top-Down question analysis
          |
          v
  Structured fact retrieval / page search
          |
          v
  Evidence-aware answer
```

The crate also includes a first-pass Knowledge Cleaner and a separate table for
user/mod observations. User and mod observations are kept distinct from UESP
source records; they are not silently promoted to canonical facts.

## Project structure

- `src/main.rs` — command-line entry point and pipeline orchestration.
- `src/config.rs` — portable project paths and dump discovery.
- `src/ingestion.rs` — streaming `.xml.bz2` import and batched SQLite writes.
- `src/database.rs` — Rust database schema and connection helpers.
- `src/wiki.rs` — wikitext structure, template parameter and link extraction,
  markup stripping, and conservative sentence fact extraction.
- `src/analysis.rs` — Bottom-Up batch analysis and evidence storage.
- `src/ai_preparation.rs` — resumable, versioned AI-readable page preparation.
- `src/knowledge.rs` — atomic JSON knowledge-base export.
- `src/top_down.rs` — question handling, structured fact lookup and page search.
- `src/cleaner.rs` — non-destructive candidate review report.
- `data/reference/provinces.json` — nine-province reference catalogue.

## Requirements

- Rust stable toolchain and Cargo.
- The existing UESP `.xml.bz2` dump.
- No Python installation is required to build or run this Rust implementation.

The Rust implementation reuses the streaming XML and fact-pattern primitives
from the sibling `rust-engine` crate. Python remains available during the
migration for behavior comparison.

## Build and test

From the repository root:

```bash
cargo test --manifest-path rust-engine/Cargo.toml
cargo test --manifest-path rust-version/Cargo.toml
cargo build --release --manifest-path rust-version/Cargo.toml
```

## Run the Rust pipeline

Import, analyse and export in one command:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run
```

If the dump is not in `data/raw/`, pass its path:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run --dump data/raw/uespwiki-2026-11-01-current.xml.bz2
```


For a safe first end-to-end test, import and analyse only the first 1,000 pages:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run --limit 1000
```

You can later run the same command without `--limit`; the importer skips pages already present and adds the remaining pages.

Batch sizes can be controlled independently. Import batches control SQLite insert transactions;
analysis batches control how many stored pages are fetched for each analysis batch:
the default is 5,000 pages. In the 50,000-page write benchmark, 5,000 was the fastest
of the tested sizes (250, 1,000 and 5,000). Larger batches reduce commit overhead but
can make individual transactions larger; set `--analysis-batch-size` explicitly if
you prefer shorter transactions.

```bash
# 50,000-page run, using batches of 250 for both stages
cargo run --release --manifest-path rust-version/Cargo.toml -- run --limit 50000 --import-batch-size 250 --analysis-batch-size 250

# Re-run analysis on the already imported 50,000 pages with a different analysis batch size
cargo run --release --manifest-path rust-version/Cargo.toml -- run --skip-import --analysis-batch-size 1000
```

For a fair analysis-batch comparison, import the sample once, then use `--skip-import`
and change only `--analysis-batch-size` between runs. Each analysis run rebuilds the
derived analysis tables, so compare elapsed analysis time and output counts. Import
batch-size comparisons require a fresh, separate database for each run because pages
already imported are skipped as duplicates.

The `analyse` and `run` commands print analysis stage timings, including cleanup
time per derived table, page counting, province loading and pattern preparation, each fetched batch,
content/fact extraction, SQLite writes, time to the first page and progress update,
and overall pages per second. Page-processing time includes extraction and writes;
those subtotals are also shown separately.
Template-parameter and link write timings are aggregated per page to avoid
per-row clock reads in the hot loop; those timings include binding and loop overhead.

Compare logical derived-table outputs using read-only SHA-256 fingerprints:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- hash-derived --dump-id 1 --db data/database/tamriel_intelligence_rust.db
```

The command streams the five derived tables without changing the database schema or data.
Fingerprints include every logical column but omit generated row IDs and
`page_analysis.analysed_at`, so they can be compared across analysis runs.

Use an already imported dump in the Rust database:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run --skip-import
```

Useful commands:

```bash
# Initialise the separate Rust database
cargo run --release --manifest-path rust-version/Cargo.toml -- init-db

# Import only
cargo run --release --manifest-path rust-version/Cargo.toml -- import

# Analyse a Rust database dump ID
cargo run --release --manifest-path rust-version/Cargo.toml -- analyse --dump-id 1

# Inspect database row counts
cargo run --release --manifest-path rust-version/Cargo.toml -- stats

# Measure source, database and generated-output disk usage (read-only)
cargo run --release --manifest-path rust-version/Cargo.toml -- storage-report

# Ask a question
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "Where do dragons live?"

# Review exported candidates
cargo run --release --manifest-path rust-version/Cargo.toml -- clean

# Export typed candidates and user/mod observations to a new file.
# The output path must not already exist.
cargo run --release --manifest-path rust-version/Cargo.toml -- build-typed-candidates --dump-id 1 --output rust-version/data/typed_candidates.json

# Prepare a completed dump into the separate ai_pages table in batches.
cargo run --release --manifest-path rust-version/Cargo.toml -- prepare-ai-pages --dump-id 1 --batch-size 250

# Explicitly regenerate all prepared pages for the dump.
cargo run --release --manifest-path rust-version/Cargo.toml -- prepare-ai-pages --dump-id 1 --force

# Stream prepared records to a new JSONL file; existing files are not replaced.
cargo run --release --manifest-path rust-version/Cargo.toml -- export-ai-pages --dump-id 1 --output rust-version/data/ai_pages.jsonl
```

All commands accept `--db PATH` to select a database. The default is
`data/database/tamriel_intelligence_rust.db`, intentionally separate from
the Python database. The default knowledge export is
`rust-version/data/knowledge_base.json`.

## Storage usage report

Run the read-only storage inventory at any point, including before and after a
benchmark:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- storage-report
```

The report lists the compressed source dump, SQLite database files and WAL/SHM
sidecars, and generated files under `rust-version/data/` plus the Python
reference `knowledge_base.json`. It reports the SQLite page allocation,
free pages and row counts for the known tables. Use `--db PATH` to inspect a
different Rust database.

The report does not create, vacuum, checkpoint, or otherwise modify a database.
SQLite table row counts are included, but individual table byte sizes are not
reported; SQLite page allocation is for the database as a whole. File totals
include any WAL/SHM sidecars found at the time of the report.

The knowledge-base JSON contains relationship candidates from
`candidate_facts`. It does not contain race, occupation or book observations
from `entity_candidates`; those records are exported separately with
`build-typed-candidates`. That export retains source page, evidence, extraction
method and UESP/user/mod provenance. It refuses to replace an existing output
file. Typed-candidate counts and exported fact counts therefore describe
different tables and are not expected to match.

`prepare-ai-pages` stores a separate derived record for each page in a
completed dump. It includes readable text, headings, templates and parameters,
wiki links, categories, external HTTP(S) links, a SHA-256 source-text hash and
the processor version. Each batch commits independently; rerunning skips pages
already prepared with the current version, while `--force` rebuilds all
prepared rows. The source `pages` records are not modified. Preparation uses
the Rust structural parser, so its markup handling is conservative and may
differ from Python's `mwparserfromhell`. `export-ai-pages` streams the prepared
records as JSON Lines, verifies every source page has a current-version
prepared record, and refuses to replace an existing file. The source hash is
provenance metadata rather than automatic invalidation; if source page text is
changed, rerun preparation with `--force`.

## Top-Down retrieval

The `ask` command supports structured relationship lookups, typed race,
occupation and book observations, evidence queries for a named subject or
claim, entity counts, page search, and a bounded knowledge overview. For
example:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "What happened in Saarthal?"
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "What evidence supports Saarthal?"
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "How many races are there?"
```

Retrieved facts and typed observations include their source and stored
evidence. Page-search snippets are normalized from wikitext, but are labeled
as search results rather than verified answers. The overview reports database
row counts and shows at most five example facts to avoid producing an
unbounded response. The CLI does not keep conversation state: ask for evidence
using a named subject or claim rather than referring to “this answer.”

Counts describe the available structured records, not necessarily every
in-world entity. Province counts come from the curated reference catalogue.

## Historical full-dump benchmark

One completed Rust pipeline run processed the full 477,491-page UESP dump:

| Measure | Recorded result |
|---|---:|
| Analysis time | 2,340.285 seconds |
| Total pipeline time | 2,388.79 seconds |
| Overall analysis throughput | 204 pages/second |
| Wiki links | 3,216,015 |
| Template parameters | 4,065,404 |
| Structured candidate facts | 2,742 |
| Typed candidates | 76,452 |

This is a historical observed run, not a controlled benchmark. The runtime
environment and exact dump checksum were not recorded alongside these figures,
so use it as a reference point rather than a reproducible cross-machine
comparison. The candidate-fact and typed-candidate totals come from separate
tables and represent different extraction outputs.

## Current limitations — read before using full dump

This is a working Rust implementation, but it is not yet a feature-for-feature
replacement for the Python implementation.

1. **Wikitext parsing:** the Rust parser is a conservative structural parser,
   not a complete MediaWiki parser. It handles nested template boundaries and
   top-level template separators, but parser functions, comments, extension
   tags, complex tables, and unusual nested markup need more parity testing.
   Python's `mwparserfromhell` remains the stronger parser at present.
2. **Markup stripping:** Rust uses a lightweight normaliser. Its output may
   differ from `mwparserfromhell.strip_code()`; fact counts can therefore differ.
3. **Question understanding:** Rust handles overview, random-fact,
   relationship, named lookup, evidence, entity-count and page-search
   questions, but its intent detection and supported relations remain narrower
   than Python's. Evidence follow-ups must name a subject or claim because the
   CLI is stateless.
4. **Knowledge Cleaner:** Rust applies required-field, fragment, pronoun,
   relationship and evidence checks and emits a review report. It remains a
   rule-based first pass, not a replacement for human review or all Python
   cleaner behavior.
5. **External observations:** Rust stores user and mod observations separately
   and can import them from JSON with `import-observations`; it does not yet
   provide a dedicated editing or management interface.
6. **Incremental updates, content hashing and extractor-version tracking** are
   future work. The analysis command currently rebuilds derived tables for the
   selected dump, as the Python pipeline does.
7. **Separate data stores:** Rust and Python databases/exports are independent.
   Running the Rust pipeline does not delete or edit Python data.

## Development order

1. Run Rust tests and compile fixes.
2. Test against the committed tiny XML fixture.
3. Compare imported page fields with Python.
4. Compare template, link, heading, tag and fact output on the same pages.
5. Audit the nine provinces and inspect unexpected candidates.
6. Run the full dump only after sample parity and backup checks.
7. Expand Top-Down coverage and add user/mod observation workflows.
8. Benchmark full-pipeline elapsed time, throughput, peak memory and result parity.

Correctness and evidence preservation take priority over raw speed.
