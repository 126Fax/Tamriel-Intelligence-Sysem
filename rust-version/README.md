# Tamriel Intelligence System — Rust implementation

This is an independent Rust implementation based on the architecture and current
working behaviour of the Python project. It is deliberately kept in
`rust-version/`; it does not replace Python, share its database, or overwrite
the Python `knowledge_base.json`.

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
- `src/knowledge.rs` — atomic JSON knowledge-base export.
- `src/top_down.rs` — question handling, structured fact lookup and page search.
- `src/cleaner.rs` — non-destructive candidate review report.
- `data/reference/provinces.json` — nine-province reference catalogue.

## Requirements

- Rust stable toolchain and Cargo.
- The existing UESP `.xml.bz2` dump.
- No Python installation is required to build or run this Rust implementation.

The Rust engine reuses the isolated streaming XML and fact-pattern primitives
from the sibling `rust-engine` crate. The Python application remains unchanged.

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

# Ask a question
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "Where do dragons live?"

# Review exported candidates
cargo run --release --manifest-path rust-version/Cargo.toml -- clean
```

All commands accept `--db PATH` to select a database. The default is
`data/database/tamriel_intelligence_rust.db`, intentionally separate from
the Python database. The default knowledge export is
`rust-version/data/knowledge_base.json`.

## Current limitations — read before using full dump

This is a working architectural port, not yet a feature-for-feature equivalent
of the Python implementation.

1. **Wikitext parsing:** the Rust parser is a conservative structural parser,
   not a complete MediaWiki parser. It handles nested template boundaries and
   top-level template separators, but parser functions, comments, extension
   tags, complex tables, and unusual nested markup need more parity testing.
   Python's `mwparserfromhell` remains the stronger parser at present.
2. **Markup stripping:** Rust uses a lightweight normaliser. Its output may
   differ from `mwparserfromhell.strip_code()`; fact counts can therefore differ.
3. **Question understanding:** the Rust Top-Down prototype supports a small
   set of intents and relationships. It does not yet match all Python question
   analyser, overview, random-fact, entity-count and retrieval behaviour.
4. **Knowledge Cleaner:** the first pass applies simple field/evidence checks.
   It is not a replacement for human review or the Python cleaner's full rules.
5. **External observations:** the schema separates user and mod submissions,
   but a dedicated import/management interface is not yet implemented.
6. **Incremental updates, content hashing and extractor-version tracking** are
   future work. The analysis command currently rebuilds derived tables for the
   selected dump, as the Python pipeline does.
7. **No production integration:** the Rust database and exported JSON are
   separate. The Rust version never deletes or edits Python data.

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
