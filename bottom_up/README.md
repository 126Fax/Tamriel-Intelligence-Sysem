# Bottom-up AI – Lore Discovery System

## Purpose

The bottom-up system examines UESP wiki data, identifies recurring structures,
and proposes organised knowledge supported by source evidence. A discovered
pattern is a candidate for further analysis; it is not automatically a verified
lore fact.

## Current components

- **Full-dump pipeline:** imports MediaWiki XML into SQLite and analyses pages,
  wiki links, templates and candidate facts.
- **Sample import and analysis:** works with the committed five-page sample
  without requiring the full UESP dump.
- **Sentence-pattern discovery:** compares controlled sentence collections,
  identifies shared structures and records variable values.
- **Prototype relationship extraction:** demonstrates early manually specified
  relationship patterns. These rules are experimental and are not yet a
  general semantic extraction system.

## Sentence-pattern discovery

The implementation is in `pattern_discovery.py`. It uses longest-common-
subsequence alignment rather than comparing words at fixed positions. This
allows a variable to contain multiple words (such as `High Rock`) and allows
variable spans at the beginning, middle or end of a sentence.

```python
from bottom_up.pattern_discovery import (
    discover_shared_patterns,
    find_specialisations,
)

sentences = [
    "The capital of Skyrim is Solitude",
    "The capital of High Rock is Daggerfall",
    "The capital of Morrowind is Vivec",
]
patterns = discover_shared_patterns(sentences, minimum_support=3)
specialisations = find_specialisations(patterns)
```

Each discovered pattern records:

- Its readable pattern string, using `[VARIABLE]` placeholders.
- Original supporting sentences and a distinct-sentence support count.
- The captured values in positional tuples (one tuple per distinct value set).
- A flattened unique `words` list retained for compatibility with the original
  prototype.
- Variable positions and the number of fixed tokens.

The defaults require at least two fixed tokens and two supporting sentences.
Both thresholds can be configured. The specialisation helper identifies
patterns that retain a general pattern's fixed tokens while filling one or
more of its variable slots.

This is an explainable first-stage technique. Longest-common-subsequence
alignment can still produce accidental similarities, and sentence patterns do
not establish subject/object meaning. Source evidence, template semantics and
later validation are required before candidate patterns become knowledge-base
facts.

## Sample data workflow

From the repository root:

```bash
python -m bottom_up.run_sample_import
python -m bottom_up.run_sample_analysis
```

The sample database is local generated data and is ignored by Git. The sample
workflow does not overwrite the full-dump database or `knowledge_base.json`.

## Full UESP workflow

Keep the original UESP XML dump under `data/raw/` (it is intentionally not
committed to Git). Run:

```bash
python -m bottom_up.run_full_pipeline
```

If the dump has already been imported and only analysis needs repeating:

```bash
python -m bottom_up.run_full_pipeline --skip-import
```

See [the full-dump pipeline guide](../docs/FULL_DUMP_PIPELINE.md) for database
tables, batch settings and current extraction limits.

## Tests

Run all automated tests from the repository root:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
