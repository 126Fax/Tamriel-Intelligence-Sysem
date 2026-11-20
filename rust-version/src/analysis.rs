use anyhow::Result;
use rusqlite::{params, Connection};
use crate::wiki::analyse_wikitext;
use crate::config::project_root;
use std::time::Instant;

#[derive(Debug, Default, Clone)]
pub struct AnalysisSummary {
    pub pages_analysed: u64,
    pub wiki_links_extracted: u64,
    pub candidate_facts_extracted: u64,
    pub template_parameters_extracted: u64,
    pub entity_candidates_extracted: u64,
}

pub fn analyse_dump(database_path: &std::path::Path, dump_id: i64, batch_size: usize) -> Result<AnalysisSummary> {
    analyse_dump_with_progress_and_limit(database_path, dump_id, batch_size, None, |_, _, _, _| {})
}

/// Rebuild analysis tables and report live progress as pages are processed.
/// The callback receives (summary, pages_processed, total_pages, elapsed_seconds).
pub fn analyse_dump_with_progress<F>(
    database_path: &std::path::Path,
    dump_id: i64,
    batch_size: usize,
    progress: F,
) -> Result<AnalysisSummary>
where
    F: FnMut(&AnalysisSummary, u64, u64, f64),
{
    analyse_dump_with_progress_and_limit(database_path, dump_id, batch_size, None, progress)
}

/// Rebuild analysis tables for at most page_limit pages and report live progress.
/// The callback receives (summary, pages_processed, pages_to_process, elapsed_seconds).
pub fn analyse_dump_with_progress_and_limit<F>(
    database_path: &std::path::Path,
    dump_id: i64,
    batch_size: usize,
    page_limit: Option<usize>,
    mut progress: F,
) -> Result<AnalysisSummary>
where
    F: FnMut(&AnalysisSummary, u64, u64, f64),
{
    if batch_size == 0 { anyhow::bail!("analysis batch size must be at least 1"); }
    let read_connection = Connection::open(database_path)?;
    let mut write_connection = Connection::open(database_path)?;
    write_connection.execute_batch("PRAGMA foreign_keys=ON;")?;
    let exists: bool = write_connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM source_dumps WHERE dump_id=?)", [dump_id], |row| row.get(0)
    )?;
    if !exists { anyhow::bail!("dump ID {dump_id} does not exist"); }

    // Derived tables are rebuilt, while imported source pages are retained.
    write_connection.execute("DELETE FROM candidate_facts WHERE dump_id=?", [dump_id])?;
    write_connection.execute("DELETE FROM entity_candidates WHERE dump_id=?", [dump_id])?;
    write_connection.execute("DELETE FROM page_template_parameters WHERE dump_id=?", [dump_id])?;
    write_connection.execute("DELETE FROM page_links WHERE dump_id=?", [dump_id])?;
    write_connection.execute("DELETE FROM page_analysis WHERE dump_id=?", [dump_id])?;

    let source_name: String = write_connection.query_row(
        "SELECT source_name FROM source_dumps WHERE dump_id=?", [dump_id], |row| row.get(0)
    )?;
    let total_pages: u64 = read_connection.query_row(
        "SELECT COUNT(*) FROM pages WHERE dump_id=?", [dump_id], |row| row.get::<_, i64>(0)
    )? as u64;
    let total_pages = page_limit.map(|limit| total_pages.min(limit as u64)).unwrap_or(total_pages);
    let started = Instant::now();
    let progress_interval = (total_pages / 100).max(1).min(500);
    let province_path = project_root().join("rust-version/data/reference/provinces.json");
    let provinces: Vec<String> = serde_json::from_slice(&std::fs::read(province_path)?)?;
    let mut summary = AnalysisSummary::default();
    let mut last_page_id = 0i64;

    loop {
        if summary.pages_analysed >= total_pages { break; }
        let remaining = total_pages - summary.pages_analysed;
        let current_batch_size = (batch_size as u64).min(remaining) as i64;
        let mut statement = read_connection.prepare(
            "SELECT page_id,title,page_text FROM pages WHERE dump_id=? AND page_id>? ORDER BY page_id LIMIT ?"
        )?;
        let rows = statement.query_map(params![dump_id,last_page_id,current_batch_size], |row| {
            Ok((row.get::<_,i64>(0)?,row.get::<_,String>(1)?,row.get::<_,String>(2)?))
        })?;
        let mut pages = Vec::new();
        for row in rows { pages.push(row?); }
        drop(statement);
        if pages.is_empty() { break; }

        let transaction = write_connection.transaction()?;
        for (page_id,title,text) in &pages {
            let wiki = analyse_wikitext(*page_id,title,text);
            transaction.execute(
                "INSERT INTO page_analysis(dump_id,page_id,template_count,wikilink_count,heading_count,tag_count) VALUES(?,?,?,?,?,?)",
                params![dump_id,page_id,wiki.template_count,wiki.link_count,wiki.heading_count,wiki.tag_count]
            )?;
            for parameter in &wiki.parameters {
                transaction.execute(
                    "INSERT INTO page_template_parameters
                     (dump_id,source_page_id,source_title,template_index,template_name,
                      parameter_index,parameter_name,is_named,parameter_value,raw_value,evidence_text,extraction_method)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    params![dump_id,page_id,title,parameter.template_index,parameter.template_name,
                        parameter.parameter_index,parameter.parameter_name,parameter.is_named as i64,
                        parameter.value,parameter.raw_value,parameter.evidence,"template_parameter_rust_v1"]
                )?;
            }
            // Promote only explicit, recognised template fields into typed candidates.
            for parameter in &wiki.parameters {
                let field = parameter.parameter_name.to_lowercase().replace(' ', "_");
                let entity_type = match field.as_str() {
                    "race" | "species" => Some("race"),
                    "occupation" | "profession" | "job" | "role" => Some("occupation"),
                    "book" | "books" | "book_title" | "book_titles" | "book_name" | "associated_book" | "associated_books" => Some("book"),
                    _ => None,
                };
                if let Some(entity_type) = entity_type {
                    transaction.execute(
                        "INSERT INTO entity_candidates
                         (dump_id,source_page_id,source_title,entity_type,value,evidence_text,
                          extraction_method,source_type,source_id)
                         VALUES(?,?,?,?,?,?,?,?,?)",
                        params![dump_id,page_id,title,entity_type,parameter.value,parameter.evidence,
                            "explicit_template_field_rust_v1","uesp",source_name]
                    )?;
                    summary.entity_candidates_extracted += 1;
                }
                if parameter.template_name.to_lowercase().contains("book") {
                    transaction.execute(
                        "INSERT INTO entity_candidates
                         (dump_id,source_page_id,source_title,entity_type,value,evidence_text,
                          extraction_method,source_type,source_id)
                         VALUES(?,?,?,?,?,?,?,?,?)",
                        params![dump_id,page_id,title,"book",title,parameter.evidence,
                            "book_template_page_title_rust_v1","uesp",source_name]
                    )?;
                    summary.entity_candidates_extracted += 1;
                    break;
                }
            }
            for link in &wiki.links {
                transaction.execute(
                    "INSERT INTO page_links(dump_id,source_page_id,source_title,destination,display_text) VALUES(?,?,?,?,?)",
                    params![dump_id,page_id,title,link.destination,link.display_text]
                )?;
            }
            let facts = crate::wiki::extract_facts(&wiki.plain_text,*page_id,title,&provinces);
            for fact in &facts {
                transaction.execute(
                    "INSERT OR IGNORE INTO candidate_facts
                     (dump_id,source_page_id,source_title,subject,relationship,object,
                      evidence_text,extraction_method,confidence)
                     VALUES(?,?,?,?,?,?,?,?,?)",
                    params![dump_id,page_id,title,fact.subject,fact.relationship,fact.object,
                        fact.evidence,fact.extraction_method,fact.confidence]
                )?;
            }
            summary.pages_analysed += 1;
            summary.wiki_links_extracted += wiki.links.len() as u64;
            summary.template_parameters_extracted += wiki.parameters.len() as u64;
            summary.candidate_facts_extracted += facts.len() as u64;

            if summary.pages_analysed % progress_interval == 0 || summary.pages_analysed == total_pages {
                progress(&summary, summary.pages_analysed, total_pages, started.elapsed().as_secs_f64());
            }
        }
        transaction.commit()?;
        last_page_id = pages.last().map(|page| page.0).unwrap_or(last_page_id);
    }
    if summary.pages_analysed == 0 {
        progress(&summary, 0, total_pages, started.elapsed().as_secs_f64());
    }
    Ok(summary)
}
