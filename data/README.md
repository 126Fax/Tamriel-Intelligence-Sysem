# Data Sources and Preparation

The importer and Python commands in this guide cover the reference
implementation. For the primary Rust workflow, see the
[Rust implementation guide](../rust-version/README.md); Rust uses its own
database and knowledge export.

## Overview

The Tamriel Intelligence System uses XML exports from the Unofficial Elder Scrolls Pages (UESP) wiki as its main data source.

The full XML dump is large and is not stored in Git. Keep the compressed dump in `data/raw/`. The directory is committed, but the dump itself is excluded by `.gitignore`.

## Full UESP dump

Place the compressed export (for example, `uespwiki-2026-11-01-current.xml.bz2`) in:

`data/raw/`

The importer automatically selects the only `.xml.bz2` file in that folder. If you keep multiple dumps there, set `XML_DUMP_PATH` in the ignored `config/local.py` file to choose the one to import.

Run the importer from the repository root:

```bash
python -m tests.test_database_import
```

The importer streams the bzip2 XML instead of loading the entire dump into memory, reads the namespace map, and inserts pages into SQLite in batches. The default batch size is 1,000 pages. It records import status and can be run again without duplicating pages for the same source dump.

## Correctness tests

Run the automated tests:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

The importer tests use a tiny synthetic XML fixture and a temporary SQLite database. They check page counts, import status, repeat-import duplicate handling, invalid batch sizes, and automatic discovery of the raw dump folder. They do not need the full UESP dump.

## Import performance benchmark

To compare batch sizes against the full dump:

```bash
python -m tests.benchmark_import
```

This benchmark runs the import three times (batch sizes 250, 1,000 and 2,500), each time using a fresh temporary database. It rereads the complete dump for every run, so it can take a while and requires temporary disk space. Compare the results on the same machine; the fastest batch size may depend on storage and available memory.

## Small committed sample

A miniature sample from the 1 November 2026 UESP dump is committed at:

`data/samples/uesp_sample_5_pages.xml.bz2.base64`

It contains five real main-namespace pages: Morrowind, Arena, Bloodmoon, Oblivion and Daggerfall. The compressed XML is Base64-encoded so it can be stored as a small text fixture in Git.

To import it, run:

```bash
python -m bottom_up.run_sample_import
```

The runner writes to `data/database/tamriel_sample.db`, not the main database. Re-running it does not duplicate pages.

## Data considerations

The XML dump may contain duplicate content, redirects, templates, markup, missing information and pages that are not relevant to the project. These need to be considered during analysis.

The original source and relevant licensing or attribution requirements should be acknowledged when the data is used or redistributed.
