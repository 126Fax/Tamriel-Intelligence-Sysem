# Expanded Knowledge Candidates Experiment

This isolated experiment explores three additional knowledge categories:

- **Race** — for example, a character's race or species.
- **Occupation** — for example, a character's profession or job.
- **Books** — book entities and explicit book fields.

It also tests source provenance for three origins:

- \`uesp\` — extracted from a named UESP XML dump.
- \`user\` — explicitly supplied by a user.
- \`mod\` — supplied by a named mod, with a \`mod_id\`.

## Important design rule

Observations from different origins are kept separate. A mod observation must
not silently overwrite a UESP observation, and a user observation must not be
presented as canonical UESP lore.

The experiment does not identify users or collect personal identity details.
The \`source_id\` should identify a submission or source record, not a person's
private identity.

## What it currently extracts

The UESP extractor conservatively recognises explicit template fields:

- \`race\` and \`species\`
- \`occupation\`, \`profession\` and \`job\`
- \`book\`, \`books\`, \`book title\`, \`book name\`, and associated-book fields

A template whose name contains \`book\` also marks its page as a book candidate.
A generic \`title\` field is deliberately not treated as a book field, because
many unrelated templates use that name.

This is a candidate extractor, not a complete lore interpreter. It does not
yet infer relationships from arbitrary prose, resolve conflicting values, or
write to the production database or \`knowledge_base.json\`.

## Run the tests

From the repository root:

\`\`\`bash
python -m unittest tests.test_expanded_knowledge_candidates -v
\`\`\`

Alternatively, run all tests:

\`\`\`bash
python -m unittest discover -s tests -p "test_*.py" -v
\`\`\`

## Next evaluation

Before connecting this experiment to Bottom-Up, evaluate it against real UESP
pages and manually check precision and coverage. In particular, inspect actual
template names and parameter names used on character and book pages. Only then
should we design persistent storage and Top-Down retrieval for these categories.
