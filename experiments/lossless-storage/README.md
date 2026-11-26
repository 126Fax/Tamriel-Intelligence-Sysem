# Lossless storage experiments

This experiment branch is based on `feature/sql-optimisation`. It must not be merged into `main` until the experiments have been reviewed.

## Purpose

Measure an unchanged SQLite database against a separate optimised copy. The first experiment is deliberately limited to a physical SQLite rebuild using `VACUUM`. It does not change the schema, remove data, or claim to optimise the SQL statements used by the Rust pipeline.

The current 5,000-page analysed database is a useful initial sample:

- 5,000 imported pages
- 142,021 template parameters
- 174,209 wiki links
- 130 candidate facts
- 7,366 entity candidates
- 142.03 MiB allocated database size

## First comparison: unchanged vs VACUUM

Run from the repository root:

```bash
python3 scripts/benchmark_sql_storage.py \
  --source data/database/tamriel_intelligence_rust.db \
  --output-dir data/experiments/lossless-storage/5k-vacuum
```

The script:

1. Opens the source database read-only and backs it up to a new baseline copy.
2. Copies that baseline to a separate candidate database.
3. Runs `VACUUM` only on the candidate.
4. Measures database file sizes and elapsed VACUUM time.
5. Records row counts and SHA-256 hashes for every user table in both copies.
6. Runs SQLite integrity checks and reports per-object page usage when `dbstat` is available.
7. Writes a JSON report and exits unsuccessfully if any table's logical contents differ.

The original source database is never modified. The output directory must not already exist, to avoid overwriting previous experiment results.

## What this first experiment does not test

`VACUUM` tests physical page compaction only. It does not test:

- SQL statement/batch performance changes
- Index removal or redesign
- Template-parameter normalisation
- Link-table normalisation
- String dictionaries or integer references

Those require separate candidate implementations and controlled comparisons. Do not treat a smaller VACUUM result as proof that the Rust SQL pipeline itself is faster.

## Benchmark protocol for later schema changes

For each schema or query optimisation:

- Use the same source dump and exact same selected pages.
- Create independent baseline and candidate databases from the same imported source.
- Run each analysis from a clean, equivalent starting state.
- Record import and analysis time separately, plus table writes, commits, database size and index size.
- Compare row counts and deterministic logical hashes for all source and derived tables.
- Check `PRAGMA integrity_check`, foreign-key integrity, and representative application queries.
- Repeat timed runs and report median as well as individual results.
- Preserve original page text, evidence, provenance and all relationships.

The 5,000-page run is the quick check. Use 50,000 pages for the main comparison. Only attempt the full 477,491-page dump after the smaller tests pass.
