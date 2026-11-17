# Top-Down AI — Lore Question Answering

The Top-Down AI is a small rule-based question-answering application for the
Elder Scrolls universe. It analyses a user's question, retrieves matching
subject–relationship–object facts from the project's JSON knowledge base, and
generates a readable answer.

## Run it

From the repository root:

```bash
python -m top_down
```

Ask a question and type `exit` to close the application.

Example questions supported by the current demonstration knowledge base:

- Which provinces belong to the Empire?
- Where do dragons live?
- What do we know about Skyrim?

## Test it

From the repository root:

```bash
python -m unittest discover -s tests -v
```

## How it works

1. `question_analyser.py` normalises the question and identifies a relationship.
2. `knowledge_retriever.py` finds known entities and retrieves matching facts.
3. `answer_generator.py` turns the retrieved facts into a response.
4. `main.py` connects the stages in an interactive command-line application.

The current implementation uses explicit Python rules. It is not a trained
language model and it does not invent facts when the knowledge base has no match.

See [the AI system documentation](../docs/AI_SYSTEM.md) for the full design,
data flow, setup, testing and limitations.
