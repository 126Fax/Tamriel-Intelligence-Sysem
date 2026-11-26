use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use std::path::Path;

pub const SCHEMA: &str = r#"
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS source_dumps (
    dump_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    dump_date TEXT,
    import_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (import_status IN ('pending','importing','completed','failed')),
    completed_at TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pages (
    dump_id INTEGER NOT NULL,
    page_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    namespace_id INTEGER NOT NULL,
    namespace_name TEXT NOT NULL,
    revision_id INTEGER,
    text_length INTEGER NOT NULL,
    page_text TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (dump_id, page_id),
    FOREIGN KEY (dump_id) REFERENCES source_dumps(dump_id)
);
CREATE INDEX IF NOT EXISTS idx_pages_title ON pages(title);
CREATE INDEX IF NOT EXISTS idx_pages_namespace ON pages(namespace_id);
CREATE TABLE IF NOT EXISTS page_analysis (
    dump_id INTEGER NOT NULL, page_id INTEGER NOT NULL,
    template_count INTEGER NOT NULL, wikilink_count INTEGER NOT NULL,
    heading_count INTEGER NOT NULL, tag_count INTEGER NOT NULL,
    analysed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dump_id,page_id),
    FOREIGN KEY (dump_id,page_id) REFERENCES pages(dump_id,page_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS page_template_parameters (
    parameter_id INTEGER PRIMARY KEY, dump_id INTEGER NOT NULL,
    source_page_id INTEGER NOT NULL, source_title TEXT NOT NULL,
    template_index INTEGER NOT NULL, template_name TEXT NOT NULL,
    parameter_index INTEGER NOT NULL, parameter_name TEXT NOT NULL,
    is_named INTEGER NOT NULL, parameter_value TEXT NOT NULL,
    raw_value TEXT NOT NULL, evidence_text TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    FOREIGN KEY (dump_id,source_page_id) REFERENCES pages(dump_id,page_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_template_parameters_lookup
    ON page_template_parameters(template_name,parameter_name);
CREATE INDEX IF NOT EXISTS idx_template_parameter_name_value
    ON page_template_parameters(parameter_name COLLATE NOCASE,parameter_value COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_template_parameters_source
    ON page_template_parameters(dump_id,source_page_id);
CREATE TABLE IF NOT EXISTS page_links (
    link_id INTEGER PRIMARY KEY, dump_id INTEGER NOT NULL,
    source_page_id INTEGER NOT NULL, source_title TEXT NOT NULL,
    destination TEXT NOT NULL, display_text TEXT NOT NULL,
    FOREIGN KEY (dump_id,source_page_id) REFERENCES pages(dump_id,page_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_page_links_destination ON page_links(destination);
CREATE INDEX IF NOT EXISTS idx_page_links_source ON page_links(dump_id,source_page_id);
CREATE TABLE IF NOT EXISTS candidate_facts (
    fact_id INTEGER PRIMARY KEY, dump_id INTEGER NOT NULL,
    source_page_id INTEGER NOT NULL, source_title TEXT NOT NULL,
    subject TEXT NOT NULL, relationship TEXT NOT NULL, object TEXT NOT NULL,
    evidence_text TEXT NOT NULL, extraction_method TEXT NOT NULL,
    confidence REAL NOT NULL,
    FOREIGN KEY (dump_id,source_page_id) REFERENCES pages(dump_id,page_id) ON DELETE CASCADE,
    UNIQUE(dump_id,source_page_id,subject,relationship,object,evidence_text)
);
CREATE INDEX IF NOT EXISTS idx_candidate_facts_lookup
    ON candidate_facts(relationship,subject,object);
CREATE TABLE IF NOT EXISTS external_observations (
    observation_id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    value TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('user','mod')),
    source_id TEXT NOT NULL,
    mod_id TEXT,
    evidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(source_type != 'mod' OR mod_id IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS entity_candidates (
    entity_candidate_id INTEGER PRIMARY KEY,
    dump_id INTEGER NOT NULL,
    source_page_id INTEGER NOT NULL,
    source_title TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK(entity_type IN ('race','occupation','book')),
    value TEXT NOT NULL,
    evidence_text TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'uesp' CHECK(source_type IN ('uesp','user','mod')),
    source_id TEXT NOT NULL,
    mod_id TEXT,
    FOREIGN KEY (dump_id,source_page_id) REFERENCES pages(dump_id,page_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_entity_candidates_type_value
    ON entity_candidates(entity_type,value COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_entity_candidates_source
    ON entity_candidates(source_type,source_id,mod_id);
CREATE INDEX IF NOT EXISTS idx_external_observations_source
    ON external_observations(source_type,source_id,mod_id);
CREATE TABLE IF NOT EXISTS ai_pages (
    dump_id INTEGER NOT NULL,
    page_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    namespace_id INTEGER NOT NULL,
    namespace_name TEXT NOT NULL,
    revision_id INTEGER,
    readable_text TEXT NOT NULL,
    headings_json TEXT NOT NULL,
    templates_json TEXT NOT NULL,
    links_json TEXT NOT NULL,
    categories_json TEXT NOT NULL,
    external_links_json TEXT NOT NULL,
    source_text_hash TEXT NOT NULL,
    processor_version TEXT NOT NULL,
    prepared_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dump_id,page_id),
    FOREIGN KEY (dump_id,page_id) REFERENCES pages(dump_id,page_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ai_pages_processor
    ON ai_pages(dump_id,processor_version);
"#;

pub fn connect(path: &Path) -> Result<Connection> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("creating database directory {}", parent.display()))?;
    }
    let connection =
        Connection::open(path).with_context(|| format!("opening database {}", path.display()))?;
    connection.execute_batch(SCHEMA)?;
    Ok(connection)
}

pub fn register_dump(connection: &Connection, source_name: &str) -> Result<i64> {
    if let Some(id) = connection
        .query_row(
            "SELECT dump_id FROM source_dumps WHERE source_name=? ORDER BY dump_id DESC LIMIT 1",
            [source_name],
            |row| row.get::<_, i64>(0),
        )
        .ok()
    {
        return Ok(id);
    }
    connection.execute(
        "INSERT INTO source_dumps(source_name) VALUES (?)",
        [source_name],
    )?;
    Ok(connection.last_insert_rowid())
}

pub fn set_dump_status(connection: &Connection, dump_id: i64, status: &str) -> Result<()> {
    connection.execute(
        "UPDATE source_dumps SET import_status=?,
         completed_at=CASE WHEN ?='completed' THEN CURRENT_TIMESTAMP ELSE NULL END
         WHERE dump_id=?",
        params![status, status, dump_id],
    )?;
    Ok(())
}

pub fn latest_dump_id(connection: &Connection, source_name: &str) -> Result<Option<i64>> {
    Ok(connection
        .query_row(
            "SELECT dump_id FROM source_dumps WHERE source_name=? ORDER BY dump_id DESC LIMIT 1",
            [source_name],
            |row| row.get(0),
        )
        .ok())
}
