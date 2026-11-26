# Knowledge Cleaner prototype

This guide covers the Python reference cleaner. The Rust implementation has a
separate `clean` command; see the
[Rust implementation guide](../rust-version/README.md) for its setup and
behavior.

The Knowledge Cleaner is a separate review stage between bottom-up extraction
and top-down retrieval.

## Run it

From the repository root:

\`\`\`bash
python -m cleaner.run_cleaner
\`\`\`

By default it reads the candidate records in \`knowledge_base.json\` and writes
an auditable report to \`data/cleaner/cleaner_results.json\`. You can choose
other paths:

\`\`\`bash
python -m cleaner.run_cleaner --input knowledge_base.json --output data/cleaner/review.json
\`\`\`

The input file is never modified. Each result retains the original candidate,
including its source page, evidence, extraction method and confidence.

## Decisions

- **approved:** required fields are present, the subject/object are structurally
  plausible, and the evidence sentence explicitly expresses the supported
  relationship pattern.
- **rejected:** the record is malformed or has strong signs of a sentence
  fragment, such as a subject beginning with a conjunction/pronoun, a subject
  containing a clause, or a pronoun as the object.
- **needs_review:** evidence does not clearly support the triple, the subject
  is unusually long, or the relationship has no evidence-checking rule yet.

## Current limits

This is version 0.1.0: explainable Python rules, not an LLM. It checks only the
three relationship patterns currently extracted by the bottom-up pipeline:
\`province\`, \`lives in\`, and \`located in\`. It does not independently verify
lore truth, resolve aliases, compare contradictions, or infer new facts.
"Approved" means that a candidate passed these limited structural and evidence
checks; it is not a guarantee of truth.

The review report is deliberately separate from \`knowledge_base.json\`.
Nothing is automatically fed to the top-down assistant yet. This lets us
measure the cleaner against labelled examples before trusting it with the
production knowledge flow.
