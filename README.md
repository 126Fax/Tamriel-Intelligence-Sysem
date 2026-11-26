# Tamriel Intelligence System

## Project overview

Rust is the primary implementation and default execution path for processing
the full UESP dump. Its promotion to the repository's default branch is
subject to review; Python remains available as the reference implementation
while parity is evaluated.
The implementations use separate databases and are not yet feature-equivalent.

- **Bottom-up analysis:** imports wiki pages, records structure and evidence,
  and extracts conservative relationship candidates.
- **Top-down retrieval:** answers a limited set of questions from those
  structured records and source pages.

## Development setup and tests

The Codespace does not install Rust during container creation. Run the setup-and-test script when you want to prepare the toolchains and execute the complete automated test suite:

```bash
bash scripts/setup-and-test.sh
```

The script installs stable Rust with rustup only when Rust/Cargo/rustup are missing, ensures Clippy and rustfmt are available, prepares the Python virtual environment, runs both Rust test suites, builds both Rust crates in release mode, and runs the Python reference tests. Subsequent runs reuse the installed toolchains and virtual environment. It does not import or process the full UESP dump.

## Rust quick start

From the repository root, build and run the Rust tests:

```bash
cargo test --manifest-path rust-engine/Cargo.toml
cargo test --manifest-path rust-version/Cargo.toml
cargo build --release --manifest-path rust-version/Cargo.toml
```

If the local Rust database already exists, inspect it and try a question
without re-importing the dump:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- stats
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "Where do dragons live?"
```

The Rust database is `data/database/tamriel_intelligence_rust.db`, and its
knowledge export is `rust-version/data/knowledge_base.json`. These generated
files are local and are not stored in Git.

## Full UESP data

The compressed dump is kept locally under `data/raw/` and is not stored in Git.
On a fresh checkout, import and analyse it with:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run
```

`--skip-import` skips only XML import; it still rebuilds all analysis tables.
See [rust-version/README.md](rust-version/README.md) for batch settings, commands
and current Rust limitations.

## Python reference implementation

Python remains available during the Rust migration. Set up its environment and
run its tests with:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py" -v
```

The Python demos, cleaner and pipeline remain documented in
[docs/TESTING_AND_DEMO.md](docs/TESTING_AND_DEMO.md) and
[docs/FULL_DUMP_PIPELINE.md](docs/FULL_DUMP_PIPELINE.md). Python should not be
removed until the Rust parser, question handling, cleaner and tests cover the
needed behavior.

## Migration status and promotion

The Rust pipeline imports the compressed dump, stores source pages and
evidence-backed extraction results in its own SQLite database, and supports
evidence-aware retrieval. AI-readable page preparation is an optional,
resumable stage. Python remains in the repository with its own tests and CI;
do not treat its database or exports as interchangeable with Rust's.

Promotion is intended to happen through a reviewed pull request to `main`,
without rewriting history or deleting the Python reference. The completed
full-dump benchmark is historical, not a controlled comparison; rerun
benchmarks only against a separate database copy.

Parity currently covers a shared synthetic fixture and a small set of real
pages, not the entire dump. The Rust wikitext parser and question handling
remain narrower than Python's. Review [Rust/Python parity and migration
status](docs/RUST_PYTHON_PARITY.md) for the comparison scope, known gaps, and
promotion checks.

See [docs/TESTING_AND_DEMO.md](docs/TESTING_AND_DEMO.md) for test instructions
and [rust-version/README.md](rust-version/README.md) for Rust commands and
limitations.
