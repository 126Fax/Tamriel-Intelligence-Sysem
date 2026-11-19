# Top-down AI – Lore Assistant

## Overview

The Top-down AI is a rule-based question analyser and knowledge retrieval prototype
for Elder Scrolls lore. It recognises question intent and retrieves information
from the project's stored knowledge sources.

## Current capabilities

- Normalises natural-language questions.
- Recognises basic question intents and relationships.
- Recognises requests such as **"What do you know?"** and **"Tell me everything you know"**.
- Reports every structured subject–relationship–object fact currently in
  `knowledge_base.json`.
- Reports the number of imported wiki pages, page counts by namespace, and
  source-dump import status from the SQLite database.
- Clearly distinguishes explicit structured facts from imported wiki source
  pages. Imported pages are not automatically treated as facts the AI has
  understood or verified.

## Asking for a knowledge overview

From the project root, run:

```bash
python -m top_down.question_analyser
```

The program opens an interactive terminal prompt. Type **"What do you know?"**
(or **"Tell me everything you know"**) and the AI prints its current knowledge
overview. Type `exit` or `quit` to close it.

In code, call `answer_question("What do you know?")`; it returns the overview
text for this intent and `None` for questions handled by other parts of the
question pipeline.

You can also run the overview directly:

```bash
python -m top_down.knowledge_overview
```

The overview lists all structured facts. It summarises the imported page
collection rather than printing every page's full text, which could be millions
of words. Individual pages can be retrieved separately when a user asks about
a specific subject.

## Data sources

- `knowledge_base.json`: explicit extracted facts.
- `data/database/tamriel_intelligence.db`: imported wiki pages and source-dump
  metadata, when the database has been created and populated.

## Limitations

This is an inventory of what is stored, not a claim that the AI understands all
of the UESP dump. A stored wiki page is source material. A structured fact is
an extracted candidate and should still be checked against its source evidence.
