# Tamriel Intelligence System

An evidence-focused, Rust-first lore intelligence project built around the UESP
(The Unofficial Elder Scrolls Pages) wiki dump. It combines a Bottom-Up data
pipeline with Top-Down retrieval, using SQLite to retain source pages,
extracted structures and supporting evidence.

Rust is the primary development and execution path. The earlier Python
implementation remains in the repository as a reference implementation for
comparison and regression testing. The two implementations use separate
databases and exports and are not yet feature-equivalent.

## What it does

- **Streaming ingestion:** imports the compressed MediaWiki XML dump into
  SQLite without loading the full dump into memory.
- **Bottom-Up analysis:** extracts page structure, templates, parameters,
  links and conservative relationship candidates.
- **Evidence and provenance:** retains source-page references and supporting
  text so extracted records can be checked against the original wiki material.
- **Top-Down retrieval:** supports structured lookups, evidence queries,
  entity counts, page search and a bounded knowledge overview.
- **AI-readable preparation:** optionally builds resumable, derived page
  records for later AI use without replacing the original source records.
- **Knowledge review:** includes a first-pass rule-based cleaner; its output
  is a review aid, not an automatic guarantee that a claim is true.

## Rust quick start

From the repository root, run the test suites and build the Rust application:

```bash
cargo test --manifest-path rust-engine/Cargo.toml
cargo test --manifest-path rust-version/Cargo.toml
cargo build --release --manifest-path rust-version/Cargo.toml
```

If the Rust database has already been imported, inspect it and try a question:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- stats
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "What happened in Saarthal?"
```

## Import and analyse the UESP dump

The compressed dump belongs in `data/raw/` and is not committed to Git. To
import and analyse it on a fresh checkout:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run
```

For a smaller initial test, limit the import:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run --limit 1000
```

Useful commands, batch-size settings, benchmark notes and current limitations
are documented in [rust-version/README.md](rust-version/README.md).

The Rust database defaults to
`data/database/tamriel_intelligence_rust.db`; its knowledge export defaults
to `rust-version/data/knowledge_base.json`. Generated databases and exports
are local data and are not stored in Git.

## Python reference implementation

Python remains available for comparison and regression testing. To set up its
environment and run its tests:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py" -v
```

The Python implementation has its own database and exports. Do not treat its
data as interchangeable with the Rust data. Python documentation remains in
[docs/TESTING_AND_DEMO.md](docs/TESTING_AND_DEMO.md) and
[docs/FULL_DUMP_PIPELINE.md](docs/FULL_DUMP_PIPELINE.md).

## Current status and limitations

The Rust pipeline is the primary project path, but it is not a complete
feature-for-feature replacement for Python. Current parity checks cover a
shared synthetic fixture and a small sample of real pages, not the entire
UESP dump. The Rust wikitext parser and question handling are narrower than
their Python counterparts, and cleaner results still require review.

The recorded full-dump benchmark is historical rather than a controlled
comparison. For benchmark work, use a separate database copy and record the
environment and input dump details.

See [docs/RUST_PYTHON_PARITY.md](docs/RUST_PYTHON_PARITY.md) for the parity
scope, known gaps and migration safeguards. See
[docs/TESTING_AND_DEMO.md](docs/TESTING_AND_DEMO.md) for test instructions.
