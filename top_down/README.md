# Top-down AI – Lore Assistant

## Current capabilities

The Top-Down AI is an explainable, rule-based assistant. It now combines:

1. **Question analysis** – recognises count questions, named-subject questions,
   relationship questions and general searches.
2. **Structured fact retrieval** – searches the exported
   `knowledge_base.json` subject–relationship–object records.
3. **SQLite retrieval** – searches imported page titles and text, plus
   evidence-backed `candidate_facts`.
4. **Count queries** – counts distinct entities only where structured
   occupation/type data exists. It does not mistake the number of keyword
   mentions or pages for the number of people.
5. **Evidence-aware answers** – shows source pages and extracts where
   available, and says when the stored data cannot support a reliable answer.

This is still a deterministic Python system, not a general-purpose LLM. It
cannot understand every possible wording yet. Its language analyser and
retrieval rules are designed to be extended with tests.

## Run it

From the repository root:

```bash
python -m top_down.chat
```

Example questions:

- `What do you know?` (full stored knowledge overview)\n- `Tell me a random fact` (no-repeat cycle through stored facts)\n- `What do you know about Skyrim?`
- `Who is Vivec?`
- `Where do dragons live?`
- `How many farmers are there?`
- `How many continents are there?`
- `How many provinces are there?`

The province question uses the traditional nine-province reference catalogue.
Other counts require structured evidence in the SQLite analysis tables. If
there is no reliable structured data, the assistant reports that it cannot
give a count rather than guessing.

## Data sources

- `knowledge_base.json`: extracted candidate subject–relationship–object facts.
- `data/database/tamriel_intelligence.db`: imported wiki pages, template
  parameters and candidate facts (generated locally and not committed).
- `data/reference/provinces.json`: the nine-name traditional province
  reference catalogue. This catalogue is kept separate from discoveries.

## Current limitations

- The question analyser is pattern-based; unusual wording may need a new
  tested pattern.
- Counting farmers depends on occupation/profession/job fields being present
  and correctly extracted from the imported wiki templates.
- Counting continents depends on explicit continent type/relationship data.
  The assistant will not infer a count from page mentions.
- Search results are source material. A matching page or extracted candidate
  is not automatically a verified lore fact.
