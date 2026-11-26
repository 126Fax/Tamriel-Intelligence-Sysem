# Python vs Rust processing comparison

This branch contains an isolated Rust prototype. It does **not** replace the
production Python pipeline or write to the production database.

## Components

- `rust-engine/`: Rust crate with a streaming MediaWiki XML reader for
  `.xml.bz2` dumps, a lightweight regex-based wikitext structure counter,
  the three explicit sentence fact patterns currently used in
  `bottom_up/full_pipeline.py`, and an isolated SQLite batch writer.
- `experiments/rust_python_comparison/compare.py`: benchmark harness that
  compares XML page records, wikitext structure counts, explicit fact
  candidates, and equivalent writes into temporary SQLite databases.

## Requirements

- Python project dependencies installed (`lxml`, `mwparserfromhell`).
- Rust stable toolchain with Cargo.
- The normal UESP dump configured in `config.paths`.

Run the Rust unit tests, then build once in release mode:

```bash
cargo test --manifest-path rust-engine/Cargo.toml
cargo build --release --manifest-path rust-engine/Cargo.toml
```

Run a 10,000-page comparison:

```bash
python -m experiments.rust_python_comparison.compare --limit 10000
```

Run the full XML comparison (both implementations read the dump independently):

```bash
python -m experiments.rust_python_comparison.compare --full
```

The harness writes a JSON report under `data/performance/`. It reports
elapsed time, throughput, peak-RSS observations where supported, exact XML
record parity, wikitext structure-count parity, fact parity, and SQLite row
parity. The default is a 10,000-page XML sample and 1,000 pages for the other
stages; `--full` opts into the complete XML dump. Use `--fact-pages` to alter
the wikitext/fact sample size and `--db-batch-size` to alter the database
batch size. The fact comparison deliberately uses an empty province catalogue
so it isolates the three shared sentence patterns; province-reference
extraction remains Python-only in this first iteration.

## Safety and interpretation

- The harness is read-only: it does not import pages, clear analysis tables,
  update SQLite, or replace `knowledge_base.json`.
- Rust XML output is streamed to a temporary JSONL file, not loaded into RAM
  as one large list by the benchmark harness.
- Compare results only after a successful release build and a correct parity
  result. A faster implementation that drops or changes pages is not a win.
- First-run Cargo compilation is not included in the benchmark timings.
- The XML benchmark measures parser + decompression + JSON serialisation for
  Rust, versus the current Python XML reader and its page extraction path.
  Treat it as an end-to-end ingestion component comparison, not a pure
  instruction-level parser benchmark.
- The Rust wikitext counter is intentionally a simple regex candidate. It is
  not a MediaWiki parser: nested templates, complex links, comments, parser
  functions and tag edge cases can produce mismatches. A mismatch is useful
  evidence that this shortcut is not a safe replacement for
  `mwparserfromhell`.
- Rust fact extraction consumes plain text prepared by the Python harness.
  The benchmark isolates the fact-pattern stage; it does not yet replace
  MediaWiki markup stripping or province-catalogue extraction.
- The SQLite test uses a small experimental table in disposable databases.
  It does not reproduce all production indexes, foreign keys, page inserts,
  migrations, or the full Bottom-Up transaction pattern.
- Full end-to-end Rust Bottom-Up processing, template/link row materialisation,
  and production-schema integration are not implemented yet. Do not connect
  this prototype to the live project database.
