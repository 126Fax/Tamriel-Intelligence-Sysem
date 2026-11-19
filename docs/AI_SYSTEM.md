# Tamriel Intelligence System — AI Documentation

## 1. Purpose and scope

The Tamriel Intelligence System is a Python project for exploring and answering
questions about the Elder Scrolls universe using information originating from
the UESP Wiki.

This document describes the AI application and its knowledge flow. The current
working application is the **Top-Down AI**: a user asks a question, the system
interprets it, retrieves relevant stored facts and produces a readable answer.

The Bottom-Up AI is not part of the current working question-answering
application. Its development is paused while the Top-Down AI is completed.

## 2. Current working version

The Top-Down AI is a transparent, rule-based question-answering system. It
currently uses three stages:

1. **Question analysis** — normalises the question and identifies a recognised
   relationship such as `province` or `lives in`.
2. **Knowledge retrieval** — finds known names in the question and retrieves
   matching records from `knowledge_base.json`.
3. **Answer generation** — turns the retrieved records into a short answer or
   reports that the current knowledge base does not contain a match.

The interactive command-line application connects these stages.

## 3. Architecture

```text
User question
     |
     v
Question analyser
     |
     v
Analysed question
     |
     v
Knowledge retriever <---- knowledge_base.json
     |
     v
Matching facts
     |
     v
Answer generator
     |
     v
Response to user
```

### 3.1 Question analyser

File: `top_down/question_analyser.py`

The analyser:
- checks that the question is not empty;
- removes surrounding whitespace and normalises letter case;
- identifies the broad question shape;
- maps supported wording to a relationship used by the knowledge base.

It uses readable Python rules and regular expressions. This makes its behaviour
easy to inspect and test, but it does not understand every possible way a person
might phrase a question.

### 3.2 Knowledge retriever

File: `top_down/knowledge_retriever.py`

The retriever:
- loads the JSON knowledge base;
- checks that each record contains a subject, relationship and object;
- finds known subject or object names mentioned in the question;
- filters facts by the recognised relationship and entity.

A knowledge record has this structure:

```json
{
  "subject": "Skyrim",
  "relationship": "province",
  "object": "Empire"
}
```

This means that the record states that Skyrim has the relationship `province`
to the Empire. The retriever only returns stored records; it does not treat a
page link or a word appearing nearby as proof of a lore fact.

### 3.3 Answer generator

File: `top_down/answer_generator.py`

The answer generator converts retrieved records into readable sentences. It
also handles an empty result by explaining that the current knowledge base
does not contain an answer. This is important: missing information should not
be replaced with an invented answer.

### 3.4 Application entry point

Files: `top_down/main.py` and `top_down/__main__.py`

The entry point loads the knowledge base, accepts questions in a loop and
passes each question through the three AI stages. The application can be
started as a Python module.

## 4. Knowledge base

The current demonstration knowledge base is stored in the repository root as
`knowledge_base.json`. It contains a small number of structured facts, not the
full contents of the UESP dump.

The knowledge base is the information source used by the current Top-Down AI.
The system can only answer questions supported by records that have been
added to it. A future version can replace or extend this JSON source with a
larger structured knowledge store without changing the overall question →
retrieval → answer design.

## 5. Data preparation and source material

The UESP source material is distributed as a MediaWiki XML dump. The
repository includes a separate data-ingestion pipeline that reads the
compressed XML, extracts page and revision information, and stores page text
and metadata in SQLite. Supporting code also reads namespace information and
can inspect MediaWiki markup.

This pipeline makes the source dump accessible to the wider project; it is
data preparation and storage, not part of the Top-Down AI's question-answering
logic. The current Top-Down AI reads the demonstration facts in
`knowledge_base.json`; it does not yet query every page in the SQLite database.

*Data-preparation note: the project uses its existing XML-reading, namespace
and SQLite-import code to make the UESP dump accessible as structured source
data for later AI development.*

## 6. Run the application

Run these commands from the repository root:

```bash
python -m top_down
```

Example questions for the current demonstration data:

- `Which provinces belong to the Empire?`
- `Where do dragons live?`
- `What do we know about Skyrim?`

Type `exit` or `quit` to close the application.

## 7. Run the tests

Run:

```bash
python -m unittest discover -s tests -v
```

The tests use small in-memory example records for predictable checks. They do
not require a full UESP dump or a populated local SQLite database.

## 8. Current limitations

- The knowledge base contains only a small demonstration set of facts.
- Question understanding is rule-based and supports a limited set of
  relationships and wording.
- The system does not currently search the full SQLite page database.
- It does not use a large language model or train a machine-learning model.
- It cannot reliably answer questions whose facts are absent from the
  knowledge base.
- The generated responses are based on retrieved records, not independent
  verification against the original wiki page.

## 9. Sensible next improvements

1. Add more reviewed facts to the knowledge base.
2. Expand the relationship and question patterns with tests.
3. Record the source page and evidence for each fact so answers can be traced.
4. Add a database-backed knowledge source once the structured facts are ready.
5. Improve entity recognition and support alternative names and spelling.

These improvements should be introduced one at a time and tested against
known questions so that new behaviour does not silently reduce answer quality.
