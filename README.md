# Tamriel Intelligence System

A Rust-based project for processing Elder Scrolls lore from the UESP Wiki and making the resulting knowledge searchable and usable by a question-answering system.

The current application is implemented in **Rust**. The earlier Python implementation is retained in the repository as a reference and comparison point; the Rust application uses its own SQLite database and knowledge-base export.

## How it works

The project follows a Bottom-Up and Top-Down approach:

- **Bottom-Up processing** imports the compressed UESP MediaWiki XML dump, analyses wiki pages, extracts links, template parameters and candidate facts, and records the source evidence.
- **Knowledge storage** keeps imported source pages, analysis results and evidence-backed candidates in SQLite. The Rust pipeline can export candidate knowledge to JSON.
- **Top-Down retrieval** accepts a question, identifies supported search intents and retrieves relevant structured facts or source pages.
- **Review and external observations** provide a first-pass candidate cleaner and a separate import path for user/mod observations. External observations remain distinct from UESP source records.

The aim is to build a traceable knowledge system: extracted information should retain where it came from, rather than becoming an unsupported statement.

## Rust implementation

The main Rust application is in [`rust-version/`](rust-version/README.md). Its reusable XML and fact-processing primitives are in [`rust-engine/`](rust-engine/).

### Requirements

- Rust stable toolchain and Cargo.
- The UESP compressed XML dump (`.xml.bz2`) for real-data processing.
- Python is not required to build or run the Rust application.

### Build and test

Run these commands from the repository root:

```bash
cargo test --manifest-path rust-engine/Cargo.toml
cargo test --manifest-path rust-version/Cargo.toml
cargo build --release --manifest-path rust-version/Cargo.toml
```

### Run the Rust pipeline

Run a small end-to-end test first:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run --limit 1000
```

Run the full pipeline:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run
```

If the dump is outside the default `data/raw/` location, provide its path:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run --dump data/raw/uespwiki-2026-11-01-current.xml.bz2
```

The pipeline imports the dump, runs Bottom-Up analysis and exports the knowledge base. To repeat analysis using pages already imported into the Rust database:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run --skip-import
```

### Other useful commands

```bash
# Initialise the Rust database
cargo run --release --manifest-path rust-version/Cargo.toml -- init-db

# Show database row counts
cargo run --release --manifest-path rust-version/Cargo.toml -- stats

# Ask the Top-Down prototype a question
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "What happened in Saarthal?"

# Review an exported candidate-fact file
cargo run --release --manifest-path rust-version/Cargo.toml -- clean
```

See [the Rust implementation guide](rust-version/README.md) for command options, batch-size comparisons, database locations, architecture and known limitations.

## Python reference implementation

The original Python implementation remains in the repository. It is useful for comparing behaviour and checking the Rust port, but it is not the primary application entry point. The Rust and Python databases are separate; running the Rust pipeline does not overwrite the Python database or its generated knowledge base.

## Current status and limitations

The Rust application has working import, analysis, knowledge export, Top-Down retrieval, candidate review and external-observation import commands. Automated Rust tests and release builds have been run successfully during development.

This is still an experimental implementation rather than a complete MediaWiki or production AI system. In particular:

- The Rust wikitext parser is intentionally conservative and is not a full MediaWiki parser.
- Extraction results and question-answering coverage still need broader parity checks against the Python reference.
- Candidate facts require validation; extracted candidates should not automatically be treated as verified lore.
- Full-dump performance, memory use, evidence quality and output parity remain ongoing evaluation work.

Correctness, repeatability and source evidence take priority over speed alone.

## Repository layout

- `rust-version/` — main Rust application and CLI.
- `rust-engine/` — reusable Rust XML and fact-processing engine.
- Python project files — original reference implementation and comparison tests.
- `data/` — local databases, exports, fixtures and source-data locations. The full UESP dump is not committed to Git.

