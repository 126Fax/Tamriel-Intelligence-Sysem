# Source-title normalisation experiment

This branch contains a reproducible, isolated prototype for removing duplicated
`source_title` text from four Rust-derived tables:

- `page_template_parameters`
- `page_links`
- `candidate_facts`
- `entity_candidates`

The candidate removes the column from independent copies and reconstructs it
with a join on **both** `(dump_id, source_page_id)` to `pages(dump_id, page_id)`.
It never joins source pages by title. The production Rust schema and supplied
source database are not modified.

## Safety and requirements

- Python 3.10+; standard library only, no pip installs.
- Run commands from the repository root.
- The source database is opened read-only and copied with SQLite's backup API.
- `VACUUM`, `ANALYZE`, schema changes and benchmarks run only on copies.
- Each output directory must be new; existing results are never overwritten.
- Do not point Rust ingestion/analysis at the candidate database. This is a
  schema prototype, not a production migration.

## 1. Check branch and database

```bash
git status --short --branch
ls -lh data/database/tamriel_intelligence_rust.db
```

If you want to start with a 50k/100k experiment database, use its path instead.
Do not switch branches if `git status` shows uncommitted work you need to keep.

## 2. Audit `ai_pages`

```bash
python3 scripts/audit_ai_pages_usage.py \
  --output data/experiments/source-title-normalisation/ai-pages-audit.json
```

The report scans both `rust-version/src` and `rust-engine/src`. It lists direct
`ai_pages` references and separately flags possible dynamic SQL, macros,
`format!`/`concat!`, query-builder and query-execution sites for manual review.
The second list contains false positives; this is a static audit aid, not a
complete Rust parser.

## 3. Capture a standalone SQLite baseline

```bash
python3 scripts/capture_sqlite_baseline.py \
  --source data/database/tamriel_intelligence_rust.db \
  --output-dir data/experiments/source-title-normalisation/baseline
```

The report records the source's SQLite version, journal mode, page size,
page/freelist counts and WAL/SHM sizes before copying. It then checkpoints WAL
on the copy if needed, runs `VACUUM`, then `ANALYZE`, and records the compacted
copy's metrics and integrity checks.

## 4. Run the source-title comparison

```bash
python3 scripts/benchmark_source_title_normalisation.py \
  --source data/database/tamriel_intelligence_rust.db \
  --output-dir data/experiments/source-title-normalisation/source-title-test \
  --repeats 5
```

Use a new output directory for every run. The benchmark creates one consistent
SQLite backup, clones that snapshot for the candidate, then prepares both arms
with the same `VACUUM` and `ANALYZE` sequence. The candidate drops `source_title`
from the four tables and reconstructs it through the composite page identity.

It produces `baseline.sqlite`, `candidate-no-source-title.sqlite` and
`comparison.json`.

## What is validated

- Every logical row in all four affected tables is reconstructed and compared
  against the baseline. Records are canonicalised, sorted and SHA-256 hashed;
  SQLite's implicit row order is never trusted.
- Fingerprints include evidence, extraction method, confidence, provenance,
  link destination, display text and reconstructed title.
- Duplicate page titles across dumps are counted and examples are recorded.
- A synthetic test proves duplicate titles in different dumps resolve to the
  correct source page and unresolved link text survives unchanged.
- `EXPLAIN QUERY PLAN` is captured for baseline direct source-title lookup and
  candidate join lookup using `(dump_id, source_page_id)`.
- Repeated per-page lookup and full-table reconstruction timings are recorded.
- SQLite `integrity_check` and `foreign_key_check` must pass on both copies.
- Schema checks confirm the candidate has removed `source_title` while
  retaining `dump_id` and `source_page_id`.

The experiment fails if any reconstructed fingerprint differs, even when row
counts match.

## Storage measurements

The report keeps these measures separate:

1. **Physical:** main database file bytes; WAL and SHM sidecars are reported
   separately.
2. **Allocated:** `(page_count - freelist_count) * page_size`.
3. **Logical payload:** summed `dbstat.payload`, where SQLite supports `dbstat`.

SQLite version and relevant pragmas are recorded. Query plans are captured
after `ANALYZE`. The original source configuration is recorded before copying.

## Important limitations

The benchmark does not update Rust writers, Top-Down queries or exports. It
uses a direct schema prototype to measure the storage and read-reconstruction
trade-off. If the result is promising, production migration will need to update
all writers/readers together and rerun behavioural equivalence tests.

The experiment changes only source-title storage. Page size, WAL policy,
`WITHOUT ROWID`, dictionary encoding and wiki-link destination references remain
separate experiments.
