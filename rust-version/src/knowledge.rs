use anyhow::Result;
use rusqlite::Connection;
use std::path::Path;
use crate::models::KnowledgeFact;

pub fn export_knowledge_base(database_path: &Path, dump_id: i64, output_path: &Path) -> Result<usize> {
    let connection = Connection::open(database_path)?;
    let mut statement = connection.prepare(
        "SELECT subject,relationship,object,source_title,source_page_id,
                evidence_text,extraction_method,confidence
         FROM candidate_facts WHERE dump_id=? ORDER BY fact_id"
    )?;
    let rows = statement.query_map([dump_id], |row| Ok(KnowledgeFact {
        subject: row.get(0)?, relationship: row.get(1)?, object: row.get(2)?,
        source_page: row.get(3)?, source_page_id: row.get(4)?, evidence: row.get(5)?,
        extraction_method: row.get(6)?, confidence: row.get(7)?,
    }))?;
    let mut facts = Vec::new();
    for row in rows { facts.push(row?); }
    if let Some(parent) = output_path.parent() { std::fs::create_dir_all(parent)?; }
    let temporary = output_path.with_extension("json.tmp");
    std::fs::write(&temporary, serde_json::to_vec_pretty(&facts)?)?;
    std::fs::rename(&temporary, output_path)?;
    Ok(facts.len())
}
