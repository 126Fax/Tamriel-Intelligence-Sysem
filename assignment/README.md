# AI Programming Assignment Prototype

This branch connects the existing Tamriel Intelligence System to the practical
AI artefacts for the HND assignment. It is an experimental branch; it does not
replace `main` or `implementation/rust-native`.

## Assignment focus

The practical work is deliberately centred on two contrasting approaches:

1. **Top-Down AI — rule-based question answering.** The user enters a question
   in the terminal. Explicitly programmed rules identify a supported question
   type, select a retrieval route, and return database records with source
   evidence. The current implementation is
   `rust-version/src/top_down.rs`, called by the `ask` CLI command.
2. **Bottom-Up AI — data-driven pattern discovery.** The prototype compares
   evidence sentences, finds shared token sequences, and replaces differing
   spans with `[VARIABLE]`. It reports recurring patterns and examples without
   assigning a meaning automatically. The implementation is
   `rust-version/src/bottom_up.rs`, called by `discover-patterns`.

Both are terminal-based and use the same Rust project and stored evidence, but
they demonstrate different ways of producing useful behaviour.

## Why these count as different approaches

### Top-Down

The Top-Down component follows an explicit, developer-authored decision path.
For example, the question handler checks for phrases such as "what do you
know", "how many provinces", and "where do ... live", then performs a
corresponding SQL query. This is explainable and repeatable, but its question
coverage is limited by the rules that have been written.

Relevant code:
- `rust-version/src/main.rs` — the `ask` terminal command.
- `rust-version/src/top_down.rs` — question normalisation, intent checks,
  SQL retrieval and evidence-aware response formatting.

### Bottom-Up

The new Bottom-Up prototype does not contain a predefined list of sentence
templates or a hardcoded mapping from a pattern to a lore relationship. It
compares a bounded sample of evidence sentences pairwise, uses longest-common-
subsequence alignment to identify shared tokens, and groups matching patterns.
The support count indicates how many distinct evidence sentences contributed
to a discovered pattern. Example sentences are printed so a person can inspect
the result.

Relevant code:
- `rust-version/src/main.rs` — the `discover-patterns` terminal command.
- `rust-version/src/bottom_up.rs` — token comparison, pattern discovery,
  database sampling and unit tests.
- `rust-version/src/analysis.rs` and `rust-version/src/wiki.rs` — upstream
  candidate extraction that supplies evidence sentences.

**Important limitation:** the Bottom-Up prototype learns recurring sentence
structure from the evidence already extracted by the wider pipeline. The
upstream extraction stage still uses programmed parsing and extraction rules.
The prototype therefore demonstrates data-driven pattern discovery, not a
fully autonomous system that learns all facts or understands their meaning.
A discovered pattern is a candidate for investigation, not a verified fact.

## Running the prototype

Run commands from the repository root.

Build and test:

```bash
cargo test --manifest-path rust-version/Cargo.toml
cargo build --release --manifest-path rust-version/Cargo.toml
```

Run the existing import, analysis and knowledge-export pipeline (requires the
local UESP XML dump):

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- run --limit 1000
```

Ask the Top-Down system:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "What do you know?"
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "Where do dragons live?"
cargo run --release --manifest-path rust-version/Cargo.toml -- ask "What happened in Saarthal?"
```

Run Bottom-Up pattern discovery against stored candidate evidence:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- discover-patterns
```

Adjust the sample and discovery thresholds:

```bash
cargo run --release --manifest-path rust-version/Cargo.toml -- discover-patterns --limit 500 --minimum-support 3 --minimum-fixed-tokens 3
```

The sample limit is intentional: pairwise sentence comparison grows
quadratically with the number of input sentences. The initial prototype is
designed for a manageable demonstration sample, not an unrestricted full-dump
pattern comparison. The current query orders evidence text alphabetically;
this makes a run repeatable but is not a statistically representative sample.

## Suggested practical evaluation

Use the same database snapshot for repeatable demonstrations and record:

| Evaluation | Top-Down | Bottom-Up |
|---|---|---|
| Input | Natural-language question | Stored evidence sentences |
| Main mechanism | Explicit intent rules and SQL retrieval | Pairwise sequence comparison and support counting |
| Output | Matching facts/pages with evidence | Shared patterns, support and example sentences |
| Success measure | Correct retrieval for supported questions; clear fallback otherwise | Repeated structures found without a hardcoded pattern catalogue |
| Main limitation | Narrow question coverage and phrasing sensitivity | Depends on upstream extracted evidence; patterns have no automatic semantics |

Useful test questions include a supported overview question, a relationship
question, a named-page search, and an unsupported or ambiguous question. For
Bottom-Up, use several evidence sentences that share a structure and a
different pair that should not meet the support threshold.

## Data-processing footnote for the report

*The system uses information from the UESP Wiki. The source dump is imported,
processed and stored in a structured SQLite database before the AI components
use the resulting records and evidence. The assignment focuses on the Top-Down
and Bottom-Up approaches rather than documenting the full data pipeline.*

## Development status

- [x] Create an isolated assignment prototype branch from
      `implementation/rust-native`.
- [x] Connect the existing Top-Down question-answering component to the
      assignment description.
- [x] Add a separate Bottom-Up sentence-pattern discovery module and terminal
      command.
- [x] Add unit tests for repeated-pattern discovery and insufficient support.
- [ ] Run the Rust test suite and release build in the development environment.
- [ ] Demonstrate both components against the same local database snapshot.
- [ ] Record test results, limitations and screenshots for the report and viva.

Do not describe the unchecked items as completed until they have been run and
recorded.
