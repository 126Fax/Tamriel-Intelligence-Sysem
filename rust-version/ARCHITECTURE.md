# Rust port — architecture mapping

| Python component | Rust counterpart |
|---|---|
| `config/paths.py` | `src/config.rs` |
| `src/ingestion/xml_reader.py` and `namespaces.py` | `src/ingestion.rs` + `rust-engine` streaming reader |
| `src/ingestion/importer.py` | `src/ingestion.rs::import_dump` |
| `src/database/database.py` + `schema.sql` | `src/database.rs` |
| `bottom_up/full_pipeline.py` | `src/wiki.rs` + `src/analysis.rs` |
| `bottom_up/province_catalog.py` | `data/reference/provinces.json` + province evidence extraction |
| `knowledge_base.json` export | `src/knowledge.rs` |
| `top_down/question_analyser.py` | `src/top_down.rs` (initial subset) |
| `top_down/knowledge_retriever.py` and `database_retriever.py` | `src/top_down.rs` |
| `top_down/answer_generator.py` and `assistant.py` | `src/top_down.rs` |
| `cleaner/knowledge_cleaner.py` | `src/cleaner.rs` (initial rules) |

## Deliberate boundaries

- The Rust database is a separate file from the Python database.
- The Rust knowledge export is separate from the Python JSON file.
- Source pages and evidence are retained alongside every candidate fact.
- UESP, user and mod observations are distinct source categories.
- The Python implementation remains the reference baseline during parity work.

The first port focuses on a complete, runnable vertical path. It does not claim
that its current MediaWiki markup handling or question interpretation is
feature-identical to the mature Python libraries and modules.
