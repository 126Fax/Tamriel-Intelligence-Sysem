use crate::models::{KnowledgeFact, TypedKnowledgeObservation};
use anyhow::{Context, Result};
use rusqlite::Connection;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

pub fn export_knowledge_base(
    database_path: &Path,
    dump_id: i64,
    output_path: &Path,
) -> Result<usize> {
    let connection = Connection::open(database_path)?;
    let mut statement = connection.prepare(
        "SELECT subject,relationship,object,source_title,source_page_id,
                evidence_text,extraction_method,confidence
         FROM candidate_facts WHERE dump_id=? ORDER BY fact_id",
    )?;
    let rows = statement.query_map([dump_id], |row| {
        Ok(KnowledgeFact {
            subject: row.get(0)?,
            relationship: row.get(1)?,
            object: row.get(2)?,
            source_page: row.get(3)?,
            source_page_id: row.get(4)?,
            evidence: row.get(5)?,
            extraction_method: row.get(6)?,
            confidence: row.get(7)?,
        })
    })?;
    let mut facts = Vec::new();
    for row in rows {
        facts.push(row?);
    }
    if let Some(parent) = output_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let temporary = output_path.with_extension("json.tmp");
    std::fs::write(&temporary, serde_json::to_vec_pretty(&facts)?)?;
    std::fs::rename(&temporary, output_path)?;
    Ok(facts.len())
}

/// Export typed UESP candidates for one dump alongside separately sourced
/// user/mod observations. Existing output files are never replaced.
pub fn export_typed_candidates(
    database_path: &Path,
    dump_id: i64,
    output_path: &Path,
) -> Result<usize> {
    let connection = Connection::open(database_path)?;
    let dump_exists: bool = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM source_dumps WHERE dump_id=?1)",
        [dump_id],
        |row| row.get(0),
    )?;
    if !dump_exists {
        anyhow::bail!("dump ID {dump_id} does not exist");
    }

    let mut statement = connection.prepare(
        "SELECT dump_id,entity_type,source_title,value,source_page_id,source_title,
                evidence_text,extraction_method,source_type,source_id,mod_id
         FROM entity_candidates WHERE dump_id=?1
         UNION ALL
         SELECT NULL,entity_type,subject,value,NULL,NULL,evidence,NULL,
                source_type,source_id,mod_id
         FROM external_observations
         ORDER BY entity_type,source_title,source_type,source_id,source_page_id",
    )?;
    let rows = statement.query_map([dump_id], |row| {
        Ok(TypedKnowledgeObservation {
            dump_id: row.get(0)?,
            entity_type: row.get(1)?,
            subject: row.get(2)?,
            value: row.get(3)?,
            source_page_id: row.get(4)?,
            source_page: row.get(5)?,
            evidence: row.get(6)?,
            extraction_method: row.get(7)?,
            source_type: row.get(8)?,
            source_id: row.get(9)?,
            mod_id: row.get(10)?,
        })
    })?;
    let observations = rows.collect::<rusqlite::Result<Vec<_>>>()?;
    let serialized = serde_json::to_vec_pretty(&observations)?;

    if let Some(parent) = output_path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("creating export directory {}", parent.display()))?;
    }
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(output_path)
        .with_context(|| {
            format!(
                "creating typed-candidate export without replacing an existing file: {}",
                output_path.display()
            )
        })?;
    output.write_all(&serialized)?;
    output.write_all(b"\n")?;
    output.sync_all()?;
    Ok(observations.len())
}
