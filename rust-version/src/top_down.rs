use anyhow::Result;
use rusqlite::{Connection, params};
use std::path::Path;

fn normalise(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ").to_lowercase()
}

fn fact_lines(connection: &Connection, relationship: Option<&str>, term: Option<&str>, limit: usize) -> Result<Vec<String>> {
    let mut output = Vec::new();
    let mut statement = connection.prepare(
        "SELECT subject,relationship,object,source_title,evidence_text
         FROM candidate_facts
         WHERE (?1 IS NULL OR lower(relationship)=lower(?1) OR (?1='province' AND lower(relationship)='province of'))
           AND (?2 IS NULL OR subject LIKE ?2 OR object LIKE ?2 OR evidence_text LIKE ?2)
         ORDER BY confidence DESC LIMIT ?3"
    )?;
    let pattern = term.map(|value| format!("%{value}%"));
    let rows = statement.query_map(params![relationship,pattern,limit as i64], |row| {
        Ok((row.get::<_,String>(0)?,row.get::<_,String>(1)?,row.get::<_,String>(2)?,
            row.get::<_,String>(3)?,row.get::<_,String>(4)?))
    })?;
    for row in rows {
        let (subject,relation,object,source,evidence) = row?;
        output.push(format!("- {subject} — {relation} — {object}.\n  Source: {source}. Evidence: {evidence}"));
    }
    Ok(output)
}

pub fn answer_question(database_path: &Path, question: &str) -> Result<String> {
    let question = question.trim();
    if question.is_empty() { anyhow::bail!("question cannot be empty"); }
    let lowered = normalise(question);
    let connection = Connection::open(database_path)?;

    if lowered.contains("what do you know") || lowered.contains("knowledge overview") {
        let count: i64 = connection.query_row("SELECT COUNT(*) FROM candidate_facts", [], |row| row.get(0))?;
        let pages: i64 = connection.query_row("SELECT COUNT(*) FROM pages", [], |row| row.get(0))?;
        let links: i64 = connection.query_row("SELECT COUNT(*) FROM page_links", [], |row| row.get(0))?;
        return Ok(format!("My database currently contains {pages} imported pages, {links} wiki links and {count} candidate facts. These are extracted records, not all independently verified lore."));
    }

    if lowered.contains("how many") && lowered.contains("province") {
        let path = crate::config::project_root().join("rust-version/data/reference/provinces.json");
        let provinces: Vec<String> = serde_json::from_slice(&std::fs::read(path)?)?;
        return Ok(format!("The reference catalogue contains {} traditional provinces of Tamriel: {}. This is a curated reference count, not proof that the extractor independently discovered all of them.", provinces.len(), provinces.join(", ")));
    }

    let entity_type = if lowered.contains("race") { Some("race") }
        else if lowered.contains("occupation") || lowered.contains("profession") || lowered.contains("job") { Some("occupation") }
        else if lowered.contains("book") { Some("book") } else { None };
    if let Some(kind) = entity_type {
        if lowered.contains("how many") {
            let count: i64 = connection.query_row(
                "SELECT COUNT(DISTINCT value) FROM (
                    SELECT value FROM entity_candidates WHERE entity_type=?1
                    UNION SELECT value FROM external_observations WHERE entity_type=?1
                 )", [kind], |row| row.get(0)
            )?;
            return Ok(format!("The current Rust database contains {count} distinct {kind} value(s) across its UESP, user and mod records. This is a database count, not a claim that the catalogue is complete."));
        }
        let mut output = Vec::new();
        let mut statement = connection.prepare(
            "SELECT subject,value,source_type,source_id,COALESCE(mod_id,''),evidence_text
             FROM entity_candidates WHERE entity_type=?1
             UNION ALL
             SELECT subject,value,source_type,source_id,COALESCE(mod_id,''),evidence
             FROM external_observations WHERE entity_type=?1
             LIMIT 20"
        )?;
        let rows = statement.query_map([kind], |row| Ok((
            row.get::<_,String>(0)?,row.get::<_,String>(1)?,row.get::<_,String>(2)?,
            row.get::<_,String>(3)?,row.get::<_,String>(4)?,row.get::<_,String>(5)?
        )))?;
        for row in rows {
            let (subject,value,source_type,source_id,mod_id,evidence) = row?;
            let source = if mod_id.is_empty() { format!("{source_type}:{source_id}") }
                else { format!("{source_type}:{source_id} (mod {mod_id})") };
            output.push(format!("- {subject}: {value} [{source}] {evidence}"));
        }
        if !output.is_empty() {
            return Ok(format!("Recorded {kind} observations (sources are kept separate):\\n{}",output.join("\\n")));
        }
    }

    let (relationship, term) = if lowered.contains("live") || lowered.contains("lives") {
        let subject = lowered.split("live").next().unwrap_or("").trim()
            .trim_start_matches("where do ").trim_start_matches("where does ")
            .trim_start_matches("where ").trim();
        (Some("lives in"), if subject.is_empty() { None } else { Some(subject.to_string()) })
    } else if lowered.contains("province") && (lowered.contains("belong") || lowered.contains("province of")) {
        (Some("province"), None)
    } else {
        (None, Some(question.trim_matches(|c: char| c.is_ascii_punctuation()).to_string()))
    };

    let rows = fact_lines(&connection, relationship, term.as_deref(), 15)?;
    if !rows.is_empty() {
        return Ok(format!("Here is what the structured database records:\n{}", rows.join("\n")));
    }

    let search_term = term.unwrap_or_else(|| question.to_string());
    let pages = connection.prepare(
        "SELECT title,namespace_name,page_text FROM pages
         WHERE title LIKE ?1 OR page_text LIKE ?1
         ORDER BY CASE WHEN title LIKE ?1 THEN 0 ELSE 1 END,text_length DESC LIMIT 8"
    )?;
    let mut output = Vec::new();
    let matches = pages.query_map([format!("%{search_term}%")], |row| {
        Ok((row.get::<_,String>(0)?,row.get::<_,String>(1)?,row.get::<_,String>(2)?))
    })?;
    for row in matches {
        let (title,namespace,text) = row?;
        let snippet = text.split_whitespace().take(45).collect::<Vec<_>>().join(" ");
        output.push(format!("- {title} ({namespace}): {snippet}"));
    }
    if output.is_empty() {
        Ok("I could not find matching structured facts or source pages in the Rust database yet. Try a named person, place, faction or creature.".to_string())
    } else {
        Ok(format!("I found source-page matches. These are search results, not automatically verified answers:\n{}",output.join("\n")))
    }
}
