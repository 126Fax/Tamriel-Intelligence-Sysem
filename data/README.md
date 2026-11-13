# Data Sources and Preparation

## Source data

The main source is an XML export of the Unofficial Elder Scrolls Pages (UESP) wiki.

Keep the original dump on your computer. Do not commit the full dump, split parts, or generated SQLite databases to Git. Configure the original dump path in the ignored `config/local.py` file:

```python
from pathlib import Path

XML_DUMP_PATH = Path("/path/to/uespwiki-current.xml.bz2")
```

## Small committed sample

`data/samples/uesp_sample_5_pages.xml.bz2.base64` contains five real main-namespace pages from the 1 November 2026 dump: Morrowind, Arena, Bloodmoon, Oblivion and Daggerfall.

Import it into its isolated sample database:

```bash
python -m bottom_up.run_sample_import
python -m bottom_up.run_sample_analysis
```

The sample database is written to `data/database/tamriel_sample.db`; it does not replace the main database.

## Full-dump workflow

### 1. Split the original dump

Large XML exports can be split into standalone MediaWiki XML files at complete page boundaries:

```bash
python -m tools.split_mediawiki_dump --input /path/to/uesp_dump.xml.bz2
```

By default, the tool writes compressed parts and a `manifest.json` under `data/processed/<dump-name>/`. The approximate part-size limit is 90 MB of uncompressed page XML. A single page is never cut in half.

### 2. Import the parts

Import all parts as one source dump:

```bash
python -m bottom_up.run_split_dump_import --manifest data/processed/<dump-name>/manifest.json
```

The importer uses the existing namespace and page readers and stores the latest revision of each page in SQLite. It can be rerun after an interruption because duplicate page IDs within the same source dump are ignored.

### 3. Prepare AI-readable records

After a successful import:

```bash
python -m bottom_up.run_data_preparation
```

This reads the original records and writes a separate `ai_pages` representation. It extracts readable text, headings, templates and parameters, wiki links, categories and external links, while retaining source identifiers and a hash of the original page text.

The preparation step does not infer semantic relationships or train a model. Those are later Bottom-Up AI responsibilities.

## Data handling principles

- Preserve original source text; store transformed representations separately.
- Keep provenance so prepared information can be traced to its source page and revision.
- Treat links as references, not proof of a relationship.
- Keep generated data and local databases out of Git.
- Acknowledge UESP attribution and applicable licensing requirements when using or redistributing source material.
