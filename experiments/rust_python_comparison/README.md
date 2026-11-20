# Python vs Rust processing comparison

This branch contains an isolated Rust prototype. It does **not** replace the
production Python pipeline or write to the production database.

## Components

- `rust-engine/`: Rust crate with a streaming MediaWiki XML reader for
  `.xml.bz2` dumps and a conservative implementation of the three explicit
  sentence fact patterns currently used in `bottom_up/full_pipeline.py`.
- `experiments/rust_python_comparison/compare.py`: benchmark harness that
  compares Python's existing XML reader with the Rust executable, checks
  extracted page records for exact equality, and compares explicit fact
  candidates on a selected page sample.

## Requirements

- Python project dependencies installed (`lxml`, `mwparserfromhell`).
- Rust stable toolchain with Cargo.
- The normal UESP dump configured in `config.paths`.

Build once in release mode:

```bash
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
elapsed time, pages/second, exact XML record parity, and fact-extraction parity
for the tested sample. The default is a 10,000-page sample; `--full` opts into
the complete dump. The fact comparison deliberately uses an empty province
catalogue so it isolates the three shared sentence patterns; the separate
province-reference extractor remains Python-only in this first iteration.

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
- Rust fact extraction is an early parity target, not a production replacement.
  It does not yet process wiki markup/templates/links. Those remain future
  benchmark stages.
