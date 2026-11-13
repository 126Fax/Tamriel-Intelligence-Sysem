# Tamriel Intelligence System

## Project overview

The Tamriel Intelligence System is a Python AI project that explores two approaches to working with Elder Scrolls lore from the UESP Wiki:

- **Bottom-up AI:** examines wiki content, identifies recurring features and patterns, and uses those patterns to organise or classify information.
- **Top-down AI:** takes a user's question, interprets what information is needed, retrieves relevant lore, and produces an answer using the stored knowledge.

The aim is to build small, understandable working examples of both approaches and evaluate how they differ. The project is not intended to recreate the entire UESP website or build a production-scale search engine.

## Development approach

The project is being developed in three broad stages:

1. **Shared foundations:** reliable XML reading, a small test dataset, storage of page content, and reusable retrieval functions.
2. **AI prototypes:** a simple bottom-up pattern-discovery prototype and a simple top-down question-and-retrieval prototype.
3. **Evaluation:** test both approaches against a consistent set of lore questions or analysis tasks, record their limitations, and compare their results.

Data preparation is deliberately kept proportionate to the AI objectives. The synthetic MediaWiki fixture allows development and testing without repeatedly processing the full UESP dump.

## Current foundations

- Reads compressed MediaWiki XML exports.
- Reads namespace information from the export.
- Extracts the latest revision of each page.
- Analyses basic dataset and page-length statistics.
- Imports page metadata and full page text into SQLite in batches.
- Provides basic keyword retrieval from stored page titles and text.
- Includes a synthetic XML fixture and integration tests.

## Technologies

- Python
- SQLite
- XML processing with lxml
- Wiki markup parsing with mwparserfromhell
- Git and GitHub

## Data setup

The full UESP XML dump is not stored in Git. Configure its location locally in config/local.py using XML_DUMP_PATH. The example configuration should contain a path on the machine running the project.

The committed synthetic fixture is used by automated tests and does not require the full dump.

## Project status

The shared foundations are being completed before the two AI prototypes are developed. The next major milestone is to build and evaluate the first simple AI behaviour, rather than expanding the data pipeline indefinitely.
