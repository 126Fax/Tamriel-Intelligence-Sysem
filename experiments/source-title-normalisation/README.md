# Source-title normalisation experiment

This branch contains a reproducible, isolated prototype for removing duplicated
`source_title` text from four derived tables:

- `page_template_parameters`
- `page_links`
- `candidate_facts`
- `entity_candidates`

The candidate stores the source identity as the existing composite key
`(dump_id, source_page_id)`. It reconstructs the original `source_title`
column through read-only compatibility views, joining to `pages` on **both**
key columns. It never resolves a source page by title alone.

## Safety

- The supplied source database is opened read-only.
- The script creates a separate baseline copy and candidate copy.
- `VACUUM`, `ANALYZE`, schema migration and benchmarks run only on those copies.
- The output directory must not already exist.
- No Rust production writer or reader is changed by this experiment.
- Compatibility views preserve the old SELECT shape but are intentionally not writable.

## Run it in Codespaces

From the repository root, first check that you are on this branch and that the
source database exists:

```bash
git status --short --branch
ls -lh data/experiments/lossless-storage/100k-source/tamriel_100k.db
```

If you have a different sample database, substitute its path below. Start with
the 50k or 100k sample rather than the full dump:

```bash
python3 scripts/benchmark_source_title_normalisation.py \
  --source data/experiments/lossless-storage/100k-source/tamriel_100k.db \
  --output-dir data/experiments/source-title-normalisation/100k
```

The output directory must be new. If you want to repeat the experiment, choose
a new output directory (for example `100k-run-2`) so the previous evidence is
preserved.

Python 3's standard library is sufficient; no additional Python packages are
required.

## What the script measures

### SQLite baseline metadata

- `SELECT sqlite_version()`
- `PRAGMA journal_mode`
- `PRAGMA page_size`
- `PRAGMA page_count`
- `PRAGMA freelist_count`
- Main database, WAL and SHM file sizes
- Allocated live pages: `(page_count - freelist_count) * page_size`
- Total allocated pages and freelist bytes
- `dbstat` B-tree allocated, payload and unused bytes when supported
- `PRAGMA integrity_check` and `PRAGMA foreign_key_check`

The script records the source's existing configuration, then makes an independent
baseline copy and applies the same `journal_mode=DELETE`, `VACUUM`, `ANALYZE`
sequence to the baseline and candidate before comparing them. This avoids
crediting the schema change for pre-existing freelist fragmentation.

### Candidate schema

Each physical candidate table is stored under a `*_normalised` name without
`source_title`. A view under the original table name reconstructs the original
column layout by joining:

```sql
ON pages.dump_id = derived.dump_id
AND pages.page_id = derived.source_page_id
```

The unresolved wiki-link destination and its display text remain untouched.
This experiment does not yet add integer destination-page references.

### Integrity and behavioural equivalence

The report checks:

- SQLite integrity and foreign-key constraints.
- Deterministically ordered SHA-256 fingerprints for every reconstructed row
  in all four affected logical tables.
- Deterministic fingerprints for every unaffected user table.
- Source-title lookups.
- Fact retrieval with source-title reconstruction.
- Wiki-link traversal, including unresolved destinations.
- A synthetic edge case with the same page title in two different dumps and
  an unresolved link whose destination text must survive.
- Query plans and seven-run median timings for source-title reconstruction
  and a representative fact lookup.

A matching row count alone is not considered sufficient. The candidate only
passes if the reconstructed logical records and behavioural checks match.

### ai_pages static audit

The JSON report includes every literal `ai_pages` reference found in the Rust
source, with file and line number, plus likely SQL-construction points such as
`format!`, `prepare` and query-builder calls for manual review. This is a
static source scan, not proof that no dynamically assembled reference exists.

## Output files

The new output directory contains:

- `baseline.sqlite` — compacted unchanged copy.
- `candidate-source-title-normalised.sqlite` — isolated candidate copy.
- `comparison.json` — full configuration, size, query-plan, timing, audit and
  integrity report.

The script exits with code 0 only when all acceptance checks pass; otherwise
it exits non-zero and leaves both copies and the report available for inspection.

## Important limitations

This is a schema/storage prototype, not a production migration. The Rust
analysis writer still expects physical `source_title` columns, and the
compatibility views are read-only. Do not point the normal Rust ingestion or
analysis pipeline at the candidate database. Do not copy the candidate over
your working database.

The experiment intentionally changes one independent variable: source-title
storage. Page size, `WITHOUT ROWID`, dictionary encoding, WAL policy and
relationship/link representation remain separate experiments.
