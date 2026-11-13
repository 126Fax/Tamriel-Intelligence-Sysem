# Development Roadmap

This roadmap reflects the current repository state. It focuses the remaining work on the two AI systems rather than repeatedly expanding the data-import tooling.

## Phase 1 – Shared foundations

- [x] Set up the Python project and Git repository.
- [x] Read compressed MediaWiki XML exports.
- [x] Extract the latest revision of each page.
- [x] Read namespace definitions.
- [x] Store source page text and metadata in SQLite.
- [x] Add a small synthetic XML fixture and a five-page UESP sample.
- [x] Add basic page retrieval.
- [x] Add a page-aware XML splitter for large local dumps.
- [x] Add a separate AI-readable data-preparation pipeline.
- [ ] Run the complete automated test suite locally after the latest pipeline changes.
- [ ] Complete and verify a full local UESP import.

## Phase 2 – Bottom-Up AI

- [ ] Connect the Bottom-Up prototype to prepared pages in SQLite.
- [ ] Choose a narrow, measurable discovery task.
- [ ] Identify recurring structures or candidate patterns.
- [ ] Record the source evidence for each proposed finding.
- [ ] Present discoveries for human review before accepting them.
- [ ] Evaluate the accuracy and usefulness of the discoveries.

## Phase 3 – Top-Down AI

- [ ] Connect question analysis to the shared knowledge store.
- [ ] Identify question intent and relevant entities or concepts.
- [ ] Retrieve supporting pages and evidence.
- [ ] Generate answers that distinguish supported facts from missing information.
- [ ] Test and improve answer reliability.

## Phase 4 – Evaluation and integration

- [ ] Create a consistent set of evaluation questions and discovery examples.
- [ ] Test both systems against the same source knowledge.
- [ ] Record accuracy, unsupported conclusions and limitations.
- [ ] Compare the two approaches.
- [ ] Document improvements and future work.

## Development principle

Keep data handling reliable and understandable, but do not let it become the whole project. The main objective is to build, test and explain the Bottom-Up and Top-Down AI behaviours.
