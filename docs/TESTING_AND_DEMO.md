# Testing and running the current project

Run commands from the repository root.

## 1. Install dependencies

```bash
python -m pip install -r requirements.txt
```

## 2. Run the automated test suite

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

These tests use temporary databases and the committed fixtures/sample data. They do not need the full UESP dump and should not overwrite the full-dump database.

The suite covers:

- XML page reading, latest-revision extraction and namespace handling;
- dataset and page-structure statistics;
- SQLite schema, migration, insertion, duplicate handling, search and import status;
- full-dump importer validation, repeatability and path selection;
- wiki markup, templates, parameters, nested templates, links, headings and tags;
- the current hardcoded bottom-up prototype's word, phrase, sentence-pattern and relationship functions;
- top-down question normalisation and basic intent/relationship recognition;
- the committed five-page UESP sample import and analysis workflow.

The shared `tests/fixtures/extraction_parity.json` fixture is also run through
the Python and Rust extraction tests. It checks semantic signals and retained
evidence/provenance for templates, links, headings, categories, facts and typed
candidates. Run the focused checks with:

```bash
python -m unittest discover -s tests -p test_extraction_parity.py -v
cargo test --manifest-path rust-version/Cargo.toml --test extraction_parity_tests
```

The parity contract intentionally compares extracted meaning rather than
requiring the two parsers to produce identical internal representations.

To compare selected real pages from the completed Rust database, run:

```bash
python scripts/run_real_data_extraction_parity.py
```

This opens the source database read-only, writes only temporary fixtures and
test databases, and removes sampled page text when the run ends. See
[Rust/Python parity status](./RUST_PYTHON_PARITY.md) for sample scope,
database/export compatibility, feature gaps, and CI coverage.

## 3. Run the demonstration

```bash
python -m bottom_up.run_demo
```

This imports five committed UESP pages into `data/database/tamriel_sample.db`, analyses their wiki markup and prints outgoing wiki-link references.

The sample database is separate from the full-dump database. The demo can be run repeatedly; existing sample pages are not duplicated.

## 4. Work with the full UESP dump

Place exactly one `.xml.bz2` dump in `data/raw/`, or set `XML_DUMP_PATH` in your ignored local configuration.

Import the full dump:

```bash
python -m tests.test_database_import
```

Run a dataset namespace scan:

```bash
python -m tests.test_dataset_scanner
```

Run page-length analysis:

```bash
python -m tests.test_page_structure
```

Inspect Year template usage:

```bash
python -m tests.test_year_templates
```

Benchmark Year-template filtering and parsing:

```bash
python -m tests.benchmark_year_analysis
```

Benchmark importer batch sizes:

```bash
python -m tests.benchmark_import
```

The full-dump commands can take time and use local disk/CPU. They are not part of the fast automated test suite.

## 5. What the tests do not prove yet

Passing tests prove that the currently implemented functions behave as expected for the tested cases. They do not prove that the system has learned general lore semantics or discovered accurate facts across the full UESP dump.

The current `bottom_up/bottom_up_ai.py` is still a scaffold. The more developed prototype uses hardcoded example sentences. The sample analyser currently extracts structural features and outgoing wiki-link references; a wiki link is not automatically a semantic relationship.

The next AI milestone is to connect explainable feature extraction to pages retrieved from SQLite, discover candidate patterns across real pages, retain evidence/source pages, and evaluate candidate findings against labelled examples.
