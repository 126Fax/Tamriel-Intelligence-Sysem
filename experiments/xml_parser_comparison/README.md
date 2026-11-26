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
python -m pip install -r experiments/xml_parser_comparison/requirements.txt
```

The PyPI distribution is pinned as `streaming-xml-parser==1.0.0`; the
documented Python import name is `xmlstream`. The package page's own quick
start uses `pip install xmlstream`, so this experiment records the actual
distribution name shown on the PyPI release page rather than relying on that
inconsistent install snippet.

## Run the compatibility probe

```bash
python -m experiments.xml_parser_comparison.probe_xmlstream
```

The probe feeds a small MediaWiki-shaped XML document to the candidate parser
in chunks and reports the events and callback data it produces. It checks
whether the API exposes enough information to reconstruct page records. This
is a compatibility check, not a performance result.

## Run the optional test

After installing the optional package, run:

```bash
python -m unittest discover -s tests -p "test_xmlstream_compatibility.py" -v
```

The test compares the candidate's reconstructed fields with the same sample
parsed by the current lxml implementation. It is expected to fail if the
candidate cannot preserve the nested page structure; that failure is useful
evidence, not a reason to change the production importer.

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
