# AI Development Plan

## Purpose

Keep development centred on the AI techniques being demonstrated. The project needs enough reliable data handling to support meaningful AI experiments, but it does not need a complete replica of the UESP data platform.

## Stage 1 — Shared foundations

These components support both AI approaches:

- [x] Read compressed MediaWiki XML.
- [x] Extract the latest revision of each page.
- [x] Read namespace definitions.
- [x] Analyse basic dataset structure.
- [x] Maintain a small synthetic XML fixture for tests.
- [x] Store page metadata in SQLite.
- [x] Store the complete page text in SQLite.
- [x] Provide basic title and text keyword retrieval.
- [x] Add a small, repeatable set of sample questions and expected source pages for evaluation.
- [ ] Optional: verify one import against the full UESP dump when it is available locally. This is not a blocker for starting the AI prototypes.

The remaining work is intentionally limited. Advanced parsing of every wiki template, full historical revision storage, distributed processing, and large-scale search infrastructure are outside the initial prototype scope unless later testing proves they are needed.

## Stage 2 — Simple AI prototypes

- [ ] First bottom-up prototype: TF-IDF text features and unsupervised K-means page clustering, with representative terms for each group. Awaiting test run.


### Bottom-up prototype

Start with a narrow task that can be tested:

1. Examine a controlled set of wiki pages.
2. Extract simple features such as recurring terms, wiki links, and selected templates.
3. Identify repeated patterns or groups.
4. Produce a human-readable report showing what it found.
5. Check whether the patterns are supported by the source pages.

The first version should be explainable and measurable. It does not need to train a large language model.

### Top-down prototype

Start with a narrow question-answering workflow:

1. Accept a question in ordinary language.
2. Identify important search terms.
3. Retrieve relevant pages from SQLite.
4. Use the retrieved text as evidence for an answer.
5. Show which pages were used and say when the available evidence is insufficient.

The first version can use straightforward NLP and retrieval before adding a local language model.

## Stage 3 — Evaluation

Use the same small evaluation set to check:

- Whether the correct pages or patterns are found;
- Whether results are supported by the source text;
- How often irrelevant results appear;
- How the systems behave when information is missing;
- How understandable and repeatable their results are.

Compare the bottom-up and top-down approaches, explain their strengths and weaknesses, and identify improvements.

## Guiding principle

Build the smallest reliable foundation that lets the AI work. Spend the majority of development effort demonstrating, testing, and evaluating the AI behaviour—not endlessly collecting or restructuring the source data.
