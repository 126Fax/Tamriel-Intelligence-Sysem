# Data Sources and Preparation

## Overview

The Tamriel Intelligence System uses XML exports from the Unofficial Elder Scrolls Pages (UESP) wiki as its main data source.

The full XML dump is large and is not stored in Git. Each developer keeps their own local copy and configures its path in the ignored `config/local.py` file.

## Small committed sample

A miniature sample from the 1 November 2026 UESP dump is committed at:

`data/samples/uesp_sample_5_pages.xml.bz2.base64`

It contains five real main-namespace pages: Morrowind, Arena, Bloodmoon, Oblivion and Daggerfall. The compressed XML is Base64-encoded so it can be stored as a small text fixture in Git.

To import it, run the dedicated sample runner from the repository root:

```bash
python -m bottom_up.run_sample_import
```

The runner temporarily decodes the fixture and passes it through the existing XML reader, namespace reader and database batch-import functions. It writes to `data/database/tamriel_sample.db`, not the main database. Re-running it does not duplicate pages.

The sample runner is opt-in: importing other project modules does not execute it. The sample database is generated locally and is ignored by Git.

## Full data preparation

The full-dump workflow will:

1. Read the XML dump and extract individual wiki pages.
2. Select relevant content and namespaces.
3. Preserve the latest revision text for each page.
4. Store page metadata and text in SQLite.
5. Make the stored pages available to the bottom-up and top-down systems.

The existing XML reader and database modules provide the foundations for this process. The complete full-dump import workflow is still under development.

## Data considerations

The XML dump may contain duplicate content, redirects, templates, markup, missing information and pages that are not relevant to the project. These need to be considered during analysis.

The original source and relevant licensing or attribution requirements should be acknowledged when the data is used or redistributed.
