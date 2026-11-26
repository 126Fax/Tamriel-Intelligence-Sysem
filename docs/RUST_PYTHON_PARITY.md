# Python/Rust parity status

Python remains the reference implementation. The parity tests compare output
from both implementations using the same page text; they do not establish that
an extracted candidate is true lore.

## Running real-page parity checks

From the repository root, run:

```bash
python scripts/run_real_data_extraction_parity.py
```

By default, the runner opens the latest completed dump in
`data/database/tamriel_intelligence_rust.db` read-only and tests four
representative pages: `Bloodmoon:Skaal` (2388), `Eye of Argonia` (159542),
`Discord` (302203), and `Lore:Rethandus` (507839). Select another database,
dump, or page set with `--database`, `--dump-id`, and repeated `--page-id`
arguments.

The runner derives the expected extraction from the Python reference, places
the selected page text in a temporary fixture, and runs the Python and Rust
parity tests against it. Temporary fixtures and test databases are removed
afterward. The full dump, source database, committed fixtures, and exports are
not modified. A selected page set is a regression sample, not an exhaustive
full-dump comparison or an independent truth-labelled evaluation.

The shared fixture and parity tests cover template inventory and parameters,
links and aliases, categories, headings, references, redirects, candidate
facts, typed candidates, evidence, and provenance. Parameter values are
compared after normalizing line-leading list markers and HTML `<br>` spacing;
the original template evidence remains stored and checked. Knowledge JSON
exports are compared against the same expected records, including confidence
and evidence.

## Feature coverage

| Python capability | Rust status | Current evidence and remaining gap |
|---|---|---|
| XML dump ingestion and core page metadata | Implemented separately | Both have sample-import tests; this parity runner starts from identical stored page text and does not compare the two full importers on the complete dump. |
| Templates, parameters, links, headings, categories and references | Partial parser parity | Synthetic fixture plus four real pages pass. Rust now handles nested links, external-link labels, `{{=}}`/`{{!}}`, and inline `nowiki` in tested cases. It is still a lightweight parser, not a complete MediaWiki implementation; complex tables, parser functions and unusual extension markup remain risks. |
| Conservative relationship facts | Comparable on the sample | Shared output, extraction method, confidence, evidence and page provenance are checked. The rule-based extractors and four-page sample do not prove full-dump completeness or correctness. |
| Race, occupation and book observations | Rust persistence is implemented | Python's extractor is experimental; Rust stores typed candidates in its own table. The extraction is tested on shared fixture and real pages, but the Python nested `provenance` JSON object and Rust flattened export are not a shared serialized contract. |
| AI-readable prepared pages | Rust-only addition | Rust stores normalized text, headings, templates, links, categories, external links, source hash and processor version. There is no equivalent production Python export to compare. |
| Top-Down lookup, evidence, search and counts | Partial port | Rust supports overview, random fact, evidence lookup, several named questions, structured counts and page search. It does not reproduce every Python intent/answer behavior: matching rules and result limits differ, and Rust random selection does not use Python's no-repeat cycle. |
| Knowledge Cleaner | Similar first-pass rule set | Both preserve original records and classify candidates as approved, rejected or needs review. This is not exhaustive behavioral parity and remains a rule-based review aid, not fact verification. |
| Pattern discovery, comparison and performance experiments | Python tooling retained | These are development/experiment utilities, not required runtime features of the Rust application. No equivalent Rust feature was found in the reviewed production path. |
| Page-aligned split-dump import | Python-only workflow | The Rust importer currently consumes a single compressed XML dump; it does not yet import manifest-verified split parts. |

Accordingly, the review does **not** establish complete feature parity with every
Python module. It demonstrates extraction parity for selected structural and
semantic outputs while identifying the gaps above. Python should remain
available until broader representative datasets, question behavior and any
required experimental utilities have explicit acceptance criteria.

## Database and export compatibility

Read-only schema inspection found identical column names and order for these
shared tables: `source_dumps`, `pages`, `page_analysis`,
`page_template_parameters`, `page_links`, and `candidate_facts`. Rust adds
`entity_candidates`, `external_observations`, and `ai_pages`. This is a
shared-table column comparison, not a guarantee that every constraint, index,
migration, or database file is interchangeable. The implementations use
separate databases and should continue to do so during the transition.

The Python and Rust knowledge-base JSON records share these fields:
`subject`, `relationship`, `object`, `source_page`, `source_page_id`,
`evidence`, `extraction_method`, and `confidence`. The shared-fixture tests
compare all field values. This confirms compatibility for that contract, not
for every historical export or consumer.

## CI coverage

`.github/workflows/tests.yml` runs:

- Python reference tests via unittest discovery;
- the Rust comparison engine tests and release build (`rust-engine`);
- Rust application tests and release build (`rust-version`).

The committed synthetic parity fixture is exercised by both test suites. The
real-page runner is intentionally opt-in because CI does not have the local
full-dump database. CI therefore does not certify full-dump parity.

## Migration and promotion checks

Rust is the primary development path, but this parity sample does not by itself
certify a complete replacement for Python. Keep the Python implementation and
its CI tests during promotion. Do not copy, migrate, or overwrite the Python
database or exports as part of the Rust rollout; the two data stores have
separate ownership and only selected shared-table/export contracts have been
compared.

Before promoting Rust to `main`:

1. Run the Python reference suite, both Rust test suites, and release builds
   from the proposed promotion branch.
2. Run the synthetic parity tests and the opt-in real-page comparison. Treat
   the real-page set as a regression sample, not exhaustive parity.
3. Review any changes to evidence, extraction methods, confidence, or
   provenance. The source pages remain the recoverable source of truth.
4. If repeating the full-dump benchmark, use a separate database copy. The
   recorded 204 pages/second result is historical and does not include a
   reproducible environment or dump checksum.
5. Promote through a reviewed, non-rewriting pull request. Change the default
   branch only after the promotion has been accepted and the repository's
   branch protections and release workflows have been checked.

Known decisions still affecting parity include whether Rust needs the Python
split-dump workflow, whether its bounded overview and stateless random-fact
selection are acceptable, and whether Python-only experimental tools need Rust
counterparts. The Rust parser remains lightweight, and selected-page tests do
not demonstrate full-dump extraction equivalence.
