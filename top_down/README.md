# Top-down AI – Lore Assistant

## Current working prototype

The first end-to-end rule-based question-answering prototype is now runnable. It connects three stages:

1. **Question analysis** – recognises a small set of natural-language question patterns and extracts subject/object hints.
2. **Knowledge retrieval** – loads and validates `knowledge_base.json`, then finds matching subject–relationship–object records.
3. **Answer generation** – turns matching records into a short answer and refuses to guess when no matching fact is stored.

This is an explainable Python prototype, not an LLM. Its language understanding is intentionally limited to the patterns described below.

## Run it

From the repository root:

```bash
python -m top_down.chat
```

You can also ask one question from a Python script:

```python
from top_down.assistant import answer_question

result = answer_question("Where do dragons live?")
print(result["answer"])
print(result["facts"])
```

The default knowledge-base path is the repository's root-level `knowledge_base.json`. To use a different JSON file, pass its path as the second argument to `answer_question`.

## Supported question patterns

| Example | Expected behaviour |
|---|---|
| `Which provinces belong to the Empire?` | Finds all records with relationship `province` and object `Empire`. |
| `Where do dragons live?` | Finds the `lives in` fact for `Dragons`. |
| `Who rules Skyrim?` | Searches for a `rules` relationship pointing to Skyrim; currently returns an honest no-information answer because the sample data has no such fact. |

The current six sample records are manually supplied prototype data. They are not claimed to have been discovered automatically from the 477,491-page UESP dump.

## Test it

Run the full repository test suite:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

The top-down tests cover question parsing, retrieval, answer generation, unknown questions, and malformed knowledge-base files.

## Current limitations

- Pattern-based question recognition; it does not understand arbitrary natural language.
- Exact entity matching after case and whitespace normalisation.
- No inference beyond the stored triples.
- No source-page provenance is currently attached to the sample facts.
- The sample knowledge base is small and manually authored.
- It is not yet connected to facts extracted from the full UESP database.

## Next development steps

1. Add source-page IDs and evidence snippets to every extracted fact.
2. Connect retrieval to the bottom-up system's structured output.
3. Expand question patterns and test paraphrases.
4. Evaluate answer accuracy against a larger set of questions.
5. Consider semantic retrieval only after the rule-based baseline is measurable.
