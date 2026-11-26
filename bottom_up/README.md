# Bottom-up AI – Lore Discovery System

This guide documents the Python reference implementation and its analysis
utilities. The primary Rust pipeline and setup instructions are in the
[Rust implementation guide](../rust-version/README.md).

## Purpose

The Bottom-Up AI examines UESP wiki data, identifies recurring structures,
and proposes knowledge supported by source evidence. A discovered pattern is
a candidate for further analysis; it is not automatically a verified lore fact.

## Current components

- **Full-dump pipeline:** imports MediaWiki XML into SQLite and analyses pages,
  wiki links, templates and candidate facts.
- **Sentence-pattern discovery:** identifies shared structures and variable
  values.
- **Province reference audit:** compares extracted province candidates with a
  separate catalogue of Tamriel's nine traditional provinces.
- **Evidence retention:** each candidate stores its source page, original
  evidence, extraction method and confidence.

## Nine-province catalogue

The reference file is `data/reference/provinces.json`:

1. Skyrim
2. Morrowind
3. Cyrodiil
4. Hammerfell
5. High Rock
6. Valenwood
7. Elsweyr
8. Black Marsh
9. Summerset Isles

The catalogue is a checklist for discovery, not a claim that the extractor
has independently found all nine. The audit reports which names have
evidence-backed candidates, which are still missing, and which candidates
fall outside the expected list. This also helps flag errors such as a region
being incorrectly labelled as a province.

## Province extraction

The full-dump extractor now checks for explicit phrasings such as
`Skyrim is one of the nine provinces of Tamriel`. It uses the reference list
to target candidate names, but only emits a candidate when the source sentence
contains a matching province/Tamriel context. Evidence is retained.

Inspect current discovery coverage with:\n\n```bash\npython -m bottom_up.province_catalog\n```\n\nThe report separates discovered provinces, missing names and unexpected candidates.\n\nAfter changing extraction rules, rerun the analysis stage for the imported
dump so existing pages are re-analysed:

```bash
python -m bottom_up.run_full_pipeline --skip-import
```

## Sentence-pattern discovery

The implementation is in `pattern_discovery.py`. It uses longest-common-
subsequence alignment, allowing multi-word values such as `High Rock` and
variables at the beginning, middle or end of sentences.

## Full UESP workflow

Keep the original UESP XML dump under `data/raw/` (not committed to Git).
Run:

```bash
python -m bottom_up.run_full_pipeline
```

If the dump is already imported:

```bash
python -m bottom_up.run_full_pipeline --skip-import
```

## Tests

Run all automated tests from the repository root:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
