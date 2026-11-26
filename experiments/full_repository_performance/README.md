# Full repository performance experiment

This experiment measures the existing repository without changing production
modules. It is designed to separate basic application/test costs from the
expensive Bottom-Up data pipeline.

## Safe first run

From the repository root:

```bash
python -m experiments.full_repository_performance.profile_repository
```

The default run:
- records SQLite row counts before and after;
- runs the automated unittest suite;
- times four representative Top-Down questions end to end;
- writes a timestamped JSON report under `data/performance/`.

The default run does **not** rebuild the database, import the XML dump, or
replace `knowledge_base.json`.

## Profile the full Bottom-Up analysis

Once ready to rebuild the derived analysis:

```bash
python -m experiments.full_repository_performance.profile_repository --run-bottom-up
```

This finds the latest imported dump in SQLite, runs Bottom-Up analysis, exports
the knowledge base, and saves Python profiler files plus readable top-function
reports under `data/performance/`.

**Important:** the current `analyse_dump()` implementation clears and rebuilds
the derived tables (`page_analysis`, `page_template_parameters`,
`page_links`, and `candidate_facts`) for the selected dump. The export step
also replaces `knowledge_base.json`. This is why rebuilding is opt-in. It
does not delete the imported `pages` table.

To choose a particular imported dump:

```bash
python -m experiments.full_repository_performance.profile_repository --run-bottom-up --dump-id 1
```

## Include XML import

To time XML import as well as analysis and export:

```bash
python -m experiments.full_repository_performance.profile_repository --run-bottom-up --include-import
```

The configured `.xml.bz2` dump must exist under `data/raw/` (or be selected
through the local path configuration). Import uses the existing importer and
its duplicate protection. It streams the dump; it does not load the XML file
into memory as one object.

## Options

- `--skip-tests`: omit the unit-test run.
- `--run-bottom-up`: explicitly rebuild derived analysis and export the KB.
- `--include-import`: include XML import; requires `--run-bottom-up`.
- `--dump-id N`: choose an existing imported dump.
- `--import-batch-size N`: XML import batch size (default 2500).
- `--analysis-batch-size N`: analysis batch size (default 32000).

## What the measurements mean

- Unit-test duration measures the current test suite, not AI inference.
- Top-Down timings include question interpretation, retrieval and answer
  construction. Some queries also search SQLite page text, so timings depend
  on database size and indexes.
- Bottom-Up stage timings separate page fetching, wiki parsing, template
  extraction/storage, link extraction/storage, fact extraction/storage and
  commits. The cProfile reports identify expensive Python functions beneath
  those stages.
- Import time includes the existing namespace read, compressed XML parsing and
  SQLite insertion path.
- The profiler is diagnostic: it does not change the production algorithms or
  claim that a faster run is automatically more accurate.

Run tests for this experiment with:

```bash
python -m py_compile experiments/full_repository_performance/profile_repository.py
```
