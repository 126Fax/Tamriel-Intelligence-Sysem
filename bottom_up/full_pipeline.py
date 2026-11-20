"""Full-dump bottom-up analysis with traceable SQLite evidence.

This first production-sized pass deliberately extracts conservative, explicit
relationships. It does not claim that every wiki link is a semantic fact.
"""
import json
import re
from pathlib import Path
from time import perf_counter

import mwparserfromhell

from src.database import database

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KNOWLEDGE_BASE_PATH = PROJECT_ROOT / "knowledge_base.json"
DEFAULT_BATCH_SIZE = 250

# Explicit sentence patterns only: every result retains the original sentence.
FACT_PATTERNS = (
    (
        "province",
        re.compile(
            r"\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+is\s+"
            r"(?:a|an)\s+province\s+of\s+"
            r"(?P<object>[A-Z][\w' -]{0,70}?)(?=[.!?;]|$)",
            re.IGNORECASE,
        ),
        0.95,
    ),
    (
        "lives in",
        re.compile(
            r"\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+"
            r"lives?\s+in\s+(?P<object>[A-Z][\w' -]{0,70}?)"
            r"(?=[.!?;]|$)",
            re.IGNORECASE,
        ),
        0.90,
    ),
    (
        "located in",
        re.compile(
            r"\b(?P<subject>[A-Z][\w' -]{0,70}?)\s+"
            r"is\s+located\s+in\s+"
            r"(?P<object>[A-Z][\w' -]{0,70}?)(?=[.!?;]|$)",
            re.IGNORECASE,
        ),
        0.90,
    ),
)


def ensure_analysis_schema(connection):
    """Create analysis tables without changing or deleting imported pages."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS page_analysis (
            dump_id INTEGER NOT NULL,
            page_id INTEGER NOT NULL,
            template_count INTEGER NOT NULL,
            wikilink_count INTEGER NOT NULL,
            heading_count INTEGER NOT NULL,
            tag_count INTEGER NOT NULL,
            analysed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (dump_id, page_id),
            FOREIGN KEY (dump_id, page_id)
                REFERENCES pages(dump_id, page_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS page_template_parameters (
            parameter_id INTEGER PRIMARY KEY,
            dump_id INTEGER NOT NULL,
            source_page_id INTEGER NOT NULL,
            source_title TEXT NOT NULL,
            template_index INTEGER NOT NULL,
            template_name TEXT NOT NULL,
            parameter_index INTEGER NOT NULL,
            parameter_name TEXT NOT NULL,
            is_named INTEGER NOT NULL,
            parameter_value TEXT NOT NULL,
            raw_value TEXT NOT NULL,
            evidence_text TEXT NOT NULL,
            extraction_method TEXT NOT NULL,
            FOREIGN KEY (dump_id, source_page_id)
                REFERENCES pages(dump_id, page_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_template_parameters_lookup
            ON page_template_parameters(template_name, parameter_name);

        CREATE INDEX IF NOT EXISTS idx_template_parameter_name_value
            ON page_template_parameters(parameter_name COLLATE NOCASE, parameter_value COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_template_parameters_source
            ON page_template_parameters(dump_id, source_page_id);

        CREATE TABLE IF NOT EXISTS page_links (
            link_id INTEGER PRIMARY KEY,
            dump_id INTEGER NOT NULL,
            source_page_id INTEGER NOT NULL,
            source_title TEXT NOT NULL,
            destination TEXT NOT NULL,
            display_text TEXT NOT NULL,
            FOREIGN KEY (dump_id, source_page_id)
                REFERENCES pages(dump_id, page_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_page_links_destination
            ON page_links(destination);
        CREATE INDEX IF NOT EXISTS idx_page_links_source
            ON page_links(dump_id, source_page_id);

        CREATE TABLE IF NOT EXISTS candidate_facts (
            fact_id INTEGER PRIMARY KEY,
            dump_id INTEGER NOT NULL,
            source_page_id INTEGER NOT NULL,
            source_title TEXT NOT NULL,
            subject TEXT NOT NULL,
            relationship TEXT NOT NULL,
            object TEXT NOT NULL,
            evidence_text TEXT NOT NULL,
            extraction_method TEXT NOT NULL,
            confidence REAL NOT NULL,
            FOREIGN KEY (dump_id, source_page_id)
                REFERENCES pages(dump_id, page_id) ON DELETE CASCADE,
            UNIQUE (
                dump_id, source_page_id, subject, relationship, object,
                evidence_text
            )
        );

        CREATE INDEX IF NOT EXISTS idx_candidate_facts_lookup
            ON candidate_facts(relationship, subject, object);
        """
    )


def _clean_entity(value):
    """Remove wiki leftovers and surrounding punctuation from an entity."""
    value = re.sub(r"\[\[([^]|]+)(?:\|([^]]+))?\]\]", lambda m: m.group(2) or m.group(1), value)
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" \t\r\n.,:;!?()[]{}'\"")
    value = re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.IGNORECASE)
    return value


def extract_template_parameters(wikicode, source_page_id, source_title):
    """Extract template fields as structured observations, not semantic facts.

    Raw values and the complete source template are retained so later discovery
    can interpret each template's schema without losing the original evidence.
    """
    parameters = []
    for template_index, template in enumerate(wikicode.filter_templates()):
        template_name = re.sub(r"\s+", " ", str(template.name)).strip()
        template_evidence = str(template)
        for parameter_index, parameter in enumerate(template.params):
            raw_value = str(parameter.value).strip()
            value = parameter.value.strip_code(
                normalize=True, collapse=True
            ).strip()
            if not template_name or not value:
                continue
            parameters.append({
                "source_page_id": int(source_page_id),
                "source_title": source_title,
                "template_index": template_index,
                "template_name": template_name,
                "parameter_index": parameter_index,
                "parameter_name": str(parameter.name).strip(),
                "is_named": bool(parameter.showkey),
                "parameter_value": value,
                "raw_value": raw_value,
                "evidence": template_evidence[:10000],
                "extraction_method": "template_parameter_v1",
            })
    return parameters


def extract_candidate_facts(plain_text, source_page_id, source_title,
                            provinces=None):
    """Extract explicit relations plus targeted evidence for known provinces.

    Pass a preloaded province catalogue when processing many pages so the
    catalogue is read once per analysis run, not once per page.
    """
    if provinces is None:
        from bottom_up.province_catalog import load_provinces
        provinces = load_provinces()

    facts = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", plain_text):
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if not sentence:
            continue

        for relationship, pattern, confidence in FACT_PATTERNS:
            for match in pattern.finditer(sentence):
                subject = _clean_entity(match.group("subject"))
                obj = _clean_entity(match.group("object"))
                if not subject or not obj or subject.casefold() == obj.casefold():
                    continue
                facts.append({
                    "source_page_id": int(source_page_id),
                    "source_page": source_title,
                    "subject": subject,
                    "relationship": relationship,
                    "object": obj,
                    "evidence": sentence[:2000],
                    "extraction_method": "explicit_sentence_pattern_v1",
                    "confidence": confidence,
                })

        # The reference catalogue helps the extractor look for less common
        # phrasings, but a province candidate is emitted only when the source
        # sentence explicitly connects that name to Tamriel's provinces.
        for province in provinces:
            escaped = re.escape(province)
            province_contexts = (
                rf"\b{escaped}\b.{{0,500}}\b(?:one of the |among the )?"
                rf"(?:nine )?provinces? of Tamriel\b",
                rf"\bprovinces? of Tamriel\b.{{0,500}}\b{escaped}\b",
                rf"\bTamriel['’]s (?:nine )?provinces?\b.{{0,500}}\b{escaped}\b",
            )
            if any(re.search(pattern, sentence, re.IGNORECASE)
                   for pattern in province_contexts):
                facts.append({
                    "source_page_id": int(source_page_id),
                    "source_page": source_title,
                    "subject": province,
                    "relationship": "province of",
                    "object": "Tamriel",
                    "evidence": sentence[:2000],
                    "extraction_method": "province_reference_context_v1",
                    "confidence": 0.92,
                })

    unique = []
    seen = set()
    for fact in facts:
        key = (fact["subject"].casefold(), fact["relationship"],
               fact["object"].casefold(), fact["evidence"])
        if key not in seen:
            seen.add(key)
            unique.append(fact)
    return unique

def analyse_dump(dump_id, batch_size=DEFAULT_BATCH_SIZE, progress_callback=None):
    """Analyse every imported page for one dump and persist evidence in SQLite."""
    if batch_size < 1:
        raise ValueError("Batch size must be at least 1.")

    connection = database.get_connection()
    processed = links_found = facts_found = template_parameters_found = 0
    timings = {"schema_setup": 0.0, "clear_previous_results": 0.0,
               "province_catalogue": 0.0, "page_selection": 0.0,
               "wiki_parsing": 0.0, "template_extraction_and_storage": 0.0,
               "link_extraction_and_storage": 0.0,
               "fact_extraction_and_storage": 0.0, "database_commits": 0.0}
    try:
        stage_started = perf_counter()
        ensure_analysis_schema(connection)
        timings["schema_setup"] += perf_counter() - stage_started
        dump = connection.execute(
            "SELECT dump_id FROM source_dumps WHERE dump_id = ?", (dump_id,)
        ).fetchone()
        if dump is None:
            raise ValueError(f"Dump ID {dump_id} does not exist.")

        # A rerun rebuilds only derived analysis for this dump.
        stage_started = perf_counter()
        connection.execute("DELETE FROM candidate_facts WHERE dump_id = ?", (dump_id,))
        connection.execute(
            "DELETE FROM page_template_parameters WHERE dump_id = ?", (dump_id,)
        )
        connection.execute("DELETE FROM page_links WHERE dump_id = ?", (dump_id,))
        connection.execute("DELETE FROM page_analysis WHERE dump_id = ?", (dump_id,))
        connection.commit()
        timings["clear_previous_results"] += perf_counter() - stage_started

        # Load this small reference catalogue once, rather than once per page.
        from bottom_up.province_catalog import load_provinces
        stage_started = perf_counter()
        provinces = load_provinces()
        timings["province_catalogue"] += perf_counter() - stage_started

        stage_started = perf_counter()
        cursor = connection.execute(
            """
            SELECT page_id, title, page_text
            FROM pages
            WHERE dump_id = ?
            ORDER BY page_id
            """,
            (dump_id,),
        )
        timings["page_selection"] += perf_counter() - stage_started
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for page in rows:
                stage_started = perf_counter()
                wikicode = mwparserfromhell.parse(page["page_text"] or "")
                templates = wikicode.filter_templates()
                links = wikicode.filter_wikilinks()
                headings = wikicode.filter_headings()
                tags = wikicode.filter_tags()
                plain_text = wikicode.strip_code(
                    normalize=True, collapse=True
                )
                timings["wiki_parsing"] += perf_counter() - stage_started
                stage_started = perf_counter()
                connection.execute(
                    """
                    INSERT INTO page_analysis
                    (dump_id, page_id, template_count, wikilink_count,
                     heading_count, tag_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (dump_id, page["page_id"], len(templates), len(links),
                     len(headings), len(tags)),
                )
                for parameter in extract_template_parameters(
                    wikicode, page["page_id"], page["title"]
                ):
                    connection.execute(
                        """
                        INSERT INTO page_template_parameters
                        (dump_id, source_page_id, source_title, template_index,
                         template_name, parameter_index, parameter_name,
                         is_named, parameter_value, raw_value, evidence_text,
                         extraction_method)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            dump_id, parameter["source_page_id"],
                            parameter["source_title"], parameter["template_index"],
                            parameter["template_name"], parameter["parameter_index"],
                            parameter["parameter_name"], int(parameter["is_named"]),
                            parameter["parameter_value"], parameter["raw_value"],
                            parameter["evidence"], parameter["extraction_method"],
                        ),
                    )
                    template_parameters_found += 1
                timings["template_extraction_and_storage"] += perf_counter() - stage_started

                stage_started = perf_counter()
                for link in links:
                    destination = str(link.title).strip()
                    display = (
                        str(link.text).strip()
                        if link.text is not None else destination
                    )
                    connection.execute(
                        """
                        INSERT INTO page_links
                        (dump_id, source_page_id, source_title, destination, display_text)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (dump_id, page["page_id"], page["title"],
                         destination, display),
                    )
                    links_found += 1
                timings["link_extraction_and_storage"] += perf_counter() - stage_started

                stage_started = perf_counter()
                for fact in extract_candidate_facts(
                    plain_text, page["page_id"], page["title"], provinces
                ):
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO candidate_facts
                        (dump_id, source_page_id, source_title, subject,
                         relationship, object, evidence_text,
                         extraction_method, confidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (dump_id, fact["source_page_id"], fact["source_page"],
                         fact["subject"], fact["relationship"], fact["object"],
                         fact["evidence"], fact["extraction_method"],
                         fact["confidence"]),
                    )
                    facts_found += 1
                timings["fact_extraction_and_storage"] += perf_counter() - stage_started
                processed += 1

            stage_started = perf_counter()
            connection.commit()
            timings["database_commits"] += perf_counter() - stage_started
            if progress_callback is not None:
                progress_callback(processed, links_found, facts_found)

        return {
            "pages_analysed": processed,
            "wiki_links_extracted": links_found,
            "candidate_facts_extracted": facts_found,
            "template_parameters_extracted": template_parameters_found,
            "stage_timings": timings,
        }
    finally:
        connection.close()


def build_knowledge_base(dump_id, output_path=DEFAULT_KNOWLEDGE_BASE_PATH):
    """Export candidate facts, including provenance, for top-down retrieval."""
    connection = database.get_connection()
    try:
        ensure_analysis_schema(connection)
        rows = connection.execute(
            """
            SELECT subject, relationship, object, source_page_id,
                   source_title, evidence_text, extraction_method, confidence
            FROM candidate_facts
            WHERE dump_id = ?
            ORDER BY relationship, subject COLLATE NOCASE, object COLLATE NOCASE
            """,
            (dump_id,),
        ).fetchall()
        facts = [
            {
                "subject": row["subject"],
                "relationship": row["relationship"],
                "object": row["object"],
                "source_page_id": row["source_page_id"],
                "source_page": row["source_title"],
                "evidence": row["evidence_text"],
                "extraction_method": row["extraction_method"],
                "confidence": row["confidence"],
            }
            for row in rows
        ]
    finally:
        connection.close()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)
    return {"knowledge_facts": len(facts), "knowledge_base_path": str(output_path)}
