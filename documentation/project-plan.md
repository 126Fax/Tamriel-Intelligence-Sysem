# Project Plan

## 1. Project Description

The Tamriel Intelligence System is a Python AI project that explores two cooperating approaches to Elder Scrolls lore using information from the Unofficial Elder Scrolls Pages (UESP) Wiki.

## 2. Project Aims

- Develop a Top-Down AI that interprets questions and retrieves relevant lore.
- Develop a Bottom-Up AI that examines source information, discovers patterns and proposes structured knowledge.
- Use a shared source dataset while keeping the responsibilities of the two AI systems separate.
- Trace proposed knowledge and answers back to their supporting wiki pages.
- Evaluate and compare the two approaches.

## 3. Planned Applications

### 3.1 Top-Down AI

A question-answering system that interprets a user's question, identifies the information required, retrieves relevant knowledge and produces an evidence-based answer.

Potential techniques include keyword recognition, pattern matching, question classification and structured retrieval.

### 3.2 Bottom-Up AI

A discovery system that analyses wiki content to identify recurring structures, patterns and candidate relationships. It should record supporting evidence and allow proposed discoveries to be reviewed before they become accepted knowledge.

Potential techniques include statistical analysis, natural language processing, similarity measures, clustering and supervised learning where suitable.

## 4. Data Source and Preparation

The primary source is a UESP MediaWiki XML dump. The original page content is imported into SQLite. A separate preparation process creates readable text and structured representations while retaining source identifiers and provenance.

The current importer stores the latest revision of each page. Full historical revision storage is not part of the current implementation.

A wiki link is treated as a reference between pages, not automatic proof of a semantic relationship.

## 5. Development Technologies

- Python
- SQLite
- lxml
- mwparserfromhell
- Git and GitHub
- Natural language processing and machine learning techniques selected during development

## 6. Current Development Position

The repository contains the shared XML and database foundations, a small real-data sample, early AI prototypes, a page-aware dump splitter and an AI-readable preparation pipeline. The next priority is to connect the Bottom-Up discovery process to the prepared database and evaluate a narrow discovery task.
