# XML parser comparison experiment

This experiment checks whether the PyPI package `streaming-xml-parser` (installed as
`xmlstream`) can preserve the information required by the Tamriel Intelligence
System before it is considered as an alternative to the current importer.

## Important distinction

The production importer is not a hand-written XML parser. It uses
`lxml.etree.iterparse` through `src/ingestion/xml_reader.py`, reads the
`.bz2` dump incrementally, and extracts the latest revision's text and IDs.

The candidate package describes itself as a parser for real-time XML streams,
including language-model output. Its documented API accepts text chunks and
emits events. That does not, by itself, demonstrate that it can reproduce the
nested MediaWiki page structure, namespaces, attributes, revision metadata,
and full wikitext required here.

For that reason this branch deliberately does **not** change
`requirements.txt` or the production importer. The candidate is an optional
experiment only.

## Setup

From the repository root, install the candidate package separately:

```bash
python -m pip install xmlstream
```

The package's PyPI distribution is named `streaming-xml-parser`, while its
documented installation/import name is `xmlstream`.

## Run the compatibility probe

```bash
python -m experiments.xml_parser_comparison.probe_xmlstream
```

The probe feeds a small MediaWiki-shaped XML document to the candidate parser
in chunks and reports the events and callback data it produces. It checks
whether the API exposes enough information to reconstruct page records. This
is a compatibility check, not a performance result.

## Compare against the real dump

Only if the compatibility probe proves that the candidate can reproduce all
required fields should a full-dump benchmark be added. The comparison must use
the same input pages and verify:

- page ID
- title
- namespace ID
- latest revision ID
- complete latest revision text, including markup and entities
- number of pages read and any skipped/failed records

A speed result is meaningful only after the candidate produces matching
records. Also measure peak memory and include bzip2 decompression in both
timings.

## Current decision

Keep `lxml.etree.iterparse` as the production parser unless the candidate
passes the data-equivalence checks. Do not merge a faster parser that loses
attributes, nested structure, or page text.
