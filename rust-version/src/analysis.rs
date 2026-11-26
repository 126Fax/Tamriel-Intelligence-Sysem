use crate::config::project_root;
use crate::wiki::analyse_wikitext;
use anyhow::Result;
use rusqlite::{params, types::ValueRef, Connection, OpenFlags};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::time::Instant;

#[derive(Debug, Default, Clone)]
pub struct SQLiteTableWriteTiming {
    pub table: &'static str,
    pub rows_written: u64,
    pub statement_execution_calls: u64,
    pub statement_execution_seconds: f64,
}

impl SQLiteTableWriteTiming {
    fn record(&mut self, rows_written: usize, calls: u64, elapsed_seconds: f64) {
        self.rows_written += rows_written as u64;
        self.statement_execution_calls += calls;
        self.statement_execution_seconds += elapsed_seconds;
    }
}

#[derive(Debug, Default, Clone)]
pub struct TransactionCommitTiming {
    pub pages: u64,
    pub rows_written: u64,
    pub commit_seconds: f64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DerivedTableHash {
    pub table: &'static str,
    pub rows: u64,
    pub sha256: String,
}

#[derive(Debug, Default, Clone)]
pub struct AnalysisTimings {
    pub clear_tables: Vec<(String, f64)>,
    pub clear_tables_total_seconds: f64,
    pub count_pages_seconds: f64,
    pub load_provinces_seconds: f64,
    pub prepare_fact_extractor_seconds: f64,
    pub batch_fetches: Vec<(u64, f64)>,
    pub page_processing_seconds: f64,
    pub wiki_extraction_seconds: f64,
    pub fact_extraction_seconds: f64,
    pub sqlite_storage_seconds: f64,
    pub sqlite_table_write_timings: Vec<SQLiteTableWriteTiming>,
    pub prepared_statement_execution_seconds: f64,
    pub transaction_begin_seconds: f64,
    pub statement_prepare_seconds: f64,
    pub transaction_commit_seconds: f64,
    pub transaction_commit_timings: Vec<TransactionCommitTiming>,
    pub seconds_to_first_page: Option<f64>,
    pub seconds_to_first_progress: Option<f64>,
    pub total_seconds: f64,
}

#[derive(Debug, Default, Clone)]
pub struct AnalysisSummary {
    pub pages_analysed: u64,
    pub wiki_links_extracted: u64,
    pub candidate_facts_extracted: u64,
    pub template_parameters_extracted: u64,
    pub entity_candidates_extracted: u64,
    pub timings: AnalysisTimings,
}

fn normalized_entity_field(value: &str) -> String {
    value
        .replace('_', " ")
        .split_whitespace()
        .map(str::to_lowercase)
        .collect::<Vec<_>>()
        .join(" ")
}

fn entity_type_for_field(value: &str) -> Option<&'static str> {
    match normalized_entity_field(value).as_str() {
        "race" | "species" => Some("race"),
        "occupation" | "profession" | "job" | "role" => Some("occupation"),
        "book" | "books" | "book title" | "book titles" | "book name" | "associated book"
        | "associated books" => Some("book"),
        _ => None,
    }
}

fn clean_entity_value(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .trim_matches(|ch: char| ch.is_whitespace() || ".,;:|".contains(ch))
        .to_string()
}

pub fn analyse_dump(
    database_path: &std::path::Path,
    dump_id: i64,
    batch_size: usize,
) -> Result<AnalysisSummary> {
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
    let analysis_started = Instant::now();
    if batch_size == 0 {
        anyhow::bail!("analysis batch size must be at least 1");
    }
    let read_connection = Connection::open(database_path)?;
    let mut write_connection = Connection::open(database_path)?;
    read_connection.execute_batch("PRAGMA cache_size=-65536;")?;
    write_connection.execute_batch("PRAGMA cache_size=-65536;")?;
    write_connection.execute_batch("PRAGMA foreign_keys=ON;")?;
    let exists: bool = write_connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM source_dumps WHERE dump_id=?)",
        [dump_id],
        |row| row.get(0),
    )?;
    if !exists {
        anyhow::bail!("dump ID {dump_id} does not exist");
    }

    // Derived tables are rebuilt, while imported source pages are retained.
    let mut clear_tables = Vec::new();
    let clear_started = Instant::now();
    for (table, sql) in [
        (
            "candidate_facts",
            "DELETE FROM candidate_facts WHERE dump_id=?",
        ),
        (
            "entity_candidates",
            "DELETE FROM entity_candidates WHERE dump_id=?",
        ),
        (
            "page_template_parameters",
            "DELETE FROM page_template_parameters WHERE dump_id=?",
        ),
        ("page_links", "DELETE FROM page_links WHERE dump_id=?"),
        ("page_analysis", "DELETE FROM page_analysis WHERE dump_id=?"),
    ] {
        let started = Instant::now();
        write_connection.execute(sql, [dump_id])?;
        clear_tables.push((table.to_string(), started.elapsed().as_secs_f64()));
    }
    let clear_tables_total_seconds = clear_started.elapsed().as_secs_f64();

    let source_name: String = write_connection.query_row(
        "SELECT source_name FROM source_dumps WHERE dump_id=?",
        [dump_id],
        |row| row.get(0),
    )?;
    let count_started = Instant::now();
    let total_pages: u64 = read_connection.query_row(
        "SELECT COUNT(*) FROM pages WHERE dump_id=?",
        [dump_id],
        |row| row.get::<_, i64>(0),
    )? as u64;
    let count_pages_seconds = count_started.elapsed().as_secs_f64();
    let total_pages = page_limit
        .map(|limit| total_pages.min(limit as u64))
        .unwrap_or(total_pages);
    let started = Instant::now();
    let progress_interval = (total_pages / 100).max(1).min(500);
    let province_path = project_root().join("rust-version/data/reference/provinces.json");
    let provinces_started = Instant::now();
    let provinces: Vec<String> = serde_json::from_slice(&std::fs::read(province_path)?)?;
    let load_provinces_seconds = provinces_started.elapsed().as_secs_f64();
    let fact_extractor_started = Instant::now();
    let fact_extractor = crate::wiki::FactExtractor::new(&provinces);
    let prepare_fact_extractor_seconds = fact_extractor_started.elapsed().as_secs_f64();
    let mut summary = AnalysisSummary::default();
    let mut last_page_id = 0i64;
    let mut page_processing_seconds = 0.0;
    let mut wiki_extraction_seconds = 0.0;
    let mut fact_extraction_seconds = 0.0;
    let mut sqlite_storage_seconds = 0.0;
    let mut sqlite_table_write_timings = vec![
        SQLiteTableWriteTiming {
            table: "page_analysis",
            ..Default::default()
        },
        SQLiteTableWriteTiming {
            table: "page_template_parameters",
            ..Default::default()
        },
        SQLiteTableWriteTiming {
            table: "page_links",
            ..Default::default()
        },
        SQLiteTableWriteTiming {
            table: "candidate_facts",
            ..Default::default()
        },
        SQLiteTableWriteTiming {
            table: "entity_candidates",
            ..Default::default()
        },
    ];
    let mut prepared_statement_execution_seconds = 0.0;
    let mut transaction_begin_seconds = 0.0;
    let mut statement_prepare_seconds = 0.0;
    let mut transaction_commit_seconds = 0.0;
    let mut transaction_commit_timings = Vec::new();
    let mut batch_fetches = Vec::new();
    let mut seconds_to_first_page = None;
    let mut seconds_to_first_progress = None;

    loop {
        if summary.pages_analysed >= total_pages {
            break;
        }
        let remaining = total_pages - summary.pages_analysed;
        let current_batch_size = (batch_size as u64).min(remaining) as i64;
        let fetch_started = Instant::now();
        let mut statement = read_connection.prepare(
            "SELECT page_id,title,page_text FROM pages WHERE dump_id=? AND page_id>? ORDER BY page_id LIMIT ?"
        )?;
        let rows =
            statement.query_map(params![dump_id, last_page_id, current_batch_size], |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            })?;
        let mut pages = Vec::new();
        for row in rows {
            pages.push(row?);
        }
        drop(statement);
        if pages.is_empty() {
            break;
        }
        batch_fetches.push((pages.len() as u64, fetch_started.elapsed().as_secs_f64()));

        let processing_started = Instant::now();
        let transaction_started = Instant::now();
        let transaction = write_connection.transaction()?;
        let transaction_begin_elapsed = transaction_started.elapsed().as_secs_f64();
        sqlite_storage_seconds += transaction_begin_elapsed;
        transaction_begin_seconds += transaction_begin_elapsed;
        let mut transaction_rows_written = 0u64;
        let statement_prepare_started = Instant::now();
        let mut page_analysis_statement = transaction.prepare(
            "INSERT INTO page_analysis(dump_id,page_id,template_count,wikilink_count,heading_count,tag_count) VALUES(?,?,?,?,?,?)"
        )?;
        let mut template_parameter_statement = transaction.prepare(
            "INSERT INTO page_template_parameters
             (dump_id,source_page_id,source_title,template_index,template_name,
              parameter_index,parameter_name,is_named,parameter_value,raw_value,evidence_text,extraction_method)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
        )?;
        let mut entity_candidate_statement = transaction.prepare(
            "INSERT INTO entity_candidates
             (dump_id,source_page_id,source_title,entity_type,value,evidence_text,
              extraction_method,source_type,source_id)
             VALUES(?,?,?,?,?,?,?,?,?)",
        )?;
        let mut page_link_statement = transaction.prepare(
            "INSERT INTO page_links(dump_id,source_page_id,source_title,destination,display_text) VALUES(?,?,?,?,?)"
        )?;
        let mut candidate_fact_statement = transaction.prepare(
            "INSERT OR IGNORE INTO candidate_facts
             (dump_id,source_page_id,source_title,subject,relationship,object,
              evidence_text,extraction_method,confidence)
             VALUES(?,?,?,?,?,?,?,?,?)",
        )?;
        let statement_prepare_elapsed = statement_prepare_started.elapsed().as_secs_f64();
        sqlite_storage_seconds += statement_prepare_elapsed;
        statement_prepare_seconds += statement_prepare_elapsed;
        for (page_id, title, text) in &pages {
            if seconds_to_first_page.is_none() {
                seconds_to_first_page = Some(analysis_started.elapsed().as_secs_f64());
            }
            let extraction_started = Instant::now();
            let wiki = analyse_wikitext(*page_id, title, text);
            wiki_extraction_seconds += extraction_started.elapsed().as_secs_f64();

            let storage_started = Instant::now();
            let rows_written = page_analysis_statement.execute(params![
                dump_id,
                page_id,
                wiki.template_count,
                wiki.link_count,
                wiki.heading_count,
                wiki.tag_count
            ])?;
            let execution_seconds = storage_started.elapsed().as_secs_f64();
            sqlite_storage_seconds += execution_seconds;
            prepared_statement_execution_seconds += execution_seconds;
            sqlite_table_write_timings[0].record(rows_written, 1, execution_seconds);
            transaction_rows_written += rows_written as u64;
            let mut parameter_rows_written = 0;
            let mut parameter_execution_seconds = 0.0;
            if !wiki.parameters.is_empty() {
                let parameter_storage_started = Instant::now();
                for parameter in &wiki.parameters {
                    let rows_written = template_parameter_statement.execute(params![
                        dump_id,
                        page_id,
                        title,
                        parameter.template_index,
                        parameter.template_name,
                        parameter.parameter_index,
                        parameter.parameter_name,
                        parameter.is_named as i64,
                        parameter.value,
                        parameter.raw_value,
                        parameter.evidence,
                        "template_parameter_rust_v1"
                    ])?;
                    parameter_rows_written += rows_written;
                    transaction_rows_written += rows_written as u64;
                }
                parameter_execution_seconds = parameter_storage_started.elapsed().as_secs_f64();
                sqlite_storage_seconds += parameter_execution_seconds;
                prepared_statement_execution_seconds += parameter_execution_seconds;
            }
            sqlite_table_write_timings[1].record(
                parameter_rows_written,
                wiki.parameters.len() as u64,
                parameter_execution_seconds,
            );
            // Promote explicit template fields and book-template pages, retaining
            // distinct evidence while avoiding duplicate observations per page.
            let mut seen_typed_candidates = HashSet::new();
            for parameter in &wiki.parameters {
                let Some(entity_type) = entity_type_for_field(&parameter.parameter_name) else {
                    continue;
                };
                let value = clean_entity_value(&parameter.value);
                let evidence: String = parameter.evidence.chars().take(2000).collect();
                if value.is_empty()
                    || !seen_typed_candidates.insert((
                        entity_type.to_string(),
                        value.to_lowercase(),
                        evidence.clone(),
                    ))
                {
                    continue;
                }

                let storage_started = Instant::now();
                let rows_written = entity_candidate_statement.execute(params![
                    dump_id,
                    page_id,
                    title,
                    entity_type,
                    value,
                    evidence,
                    "explicit_template_field_rust_v1",
                    "uesp",
                    source_name
                ])?;
                let execution_seconds = storage_started.elapsed().as_secs_f64();
                sqlite_storage_seconds += execution_seconds;
                prepared_statement_execution_seconds += execution_seconds;
                sqlite_table_write_timings[4].record(rows_written, 1, execution_seconds);
                transaction_rows_written += rows_written as u64;
                summary.entity_candidates_extracted += rows_written as u64;
            }
            for template in &wiki.templates {
                if !template.name.to_lowercase().contains("book") {
                    continue;
                }
                let value = clean_entity_value(title);
                let evidence: String = template.evidence.chars().take(2000).collect();
                if value.is_empty()
                    || !seen_typed_candidates.insert((
                        "book".to_string(),
                        value.to_lowercase(),
                        evidence.clone(),
                    ))
                {
                    continue;
                }

                let storage_started = Instant::now();
                let rows_written = entity_candidate_statement.execute(params![
                    dump_id,
                    page_id,
                    title,
                    "book",
                    value,
                    evidence,
                    "book_template_page_title_rust_v1",
                    "uesp",
                    source_name
                ])?;
                let execution_seconds = storage_started.elapsed().as_secs_f64();
                sqlite_storage_seconds += execution_seconds;
                prepared_statement_execution_seconds += execution_seconds;
                sqlite_table_write_timings[4].record(rows_written, 1, execution_seconds);
                transaction_rows_written += rows_written as u64;
                summary.entity_candidates_extracted += rows_written as u64;
            }
            let mut link_rows_written = 0;
            let mut link_execution_seconds = 0.0;
            if !wiki.links.is_empty() {
                let link_storage_started = Instant::now();
                for link in &wiki.links {
                    let rows_written = page_link_statement.execute(params![
                        dump_id,
                        page_id,
                        title,
                        link.destination,
                        link.display_text
                    ])?;
                    link_rows_written += rows_written;
                    transaction_rows_written += rows_written as u64;
                }
                link_execution_seconds = link_storage_started.elapsed().as_secs_f64();
                sqlite_storage_seconds += link_execution_seconds;
                prepared_statement_execution_seconds += link_execution_seconds;
            }
            sqlite_table_write_timings[2].record(
                link_rows_written,
                wiki.links.len() as u64,
                link_execution_seconds,
            );
            let fact_extraction_started = Instant::now();
            let facts = fact_extractor.extract_facts(&wiki.plain_text, *page_id, title);
            fact_extraction_seconds += fact_extraction_started.elapsed().as_secs_f64();
            for fact in &facts {
                let storage_started = Instant::now();
                let rows_written = candidate_fact_statement.execute(params![
                    dump_id,
                    page_id,
                    title,
                    fact.subject,
                    fact.relationship,
                    fact.object,
                    fact.evidence,
                    fact.extraction_method,
                    fact.confidence
                ])?;
                let execution_seconds = storage_started.elapsed().as_secs_f64();
                sqlite_storage_seconds += execution_seconds;
                prepared_statement_execution_seconds += execution_seconds;
                sqlite_table_write_timings[3].record(rows_written, 1, execution_seconds);
                transaction_rows_written += rows_written as u64;
            }
            summary.pages_analysed += 1;
            summary.wiki_links_extracted += wiki.links.len() as u64;
            summary.template_parameters_extracted += wiki.parameters.len() as u64;
            summary.candidate_facts_extracted += facts.len() as u64;

            if summary.pages_analysed % progress_interval == 0
                || summary.pages_analysed == total_pages
            {
                if seconds_to_first_progress.is_none() {
                    seconds_to_first_progress = Some(analysis_started.elapsed().as_secs_f64());
                }
                progress(
                    &summary,
                    summary.pages_analysed,
                    total_pages,
                    started.elapsed().as_secs_f64(),
                );
            }
        }
        drop(candidate_fact_statement);
        drop(page_link_statement);
        drop(entity_candidate_statement);
        drop(template_parameter_statement);
        drop(page_analysis_statement);
        let commit_started = Instant::now();
        transaction.commit()?;
        let commit_elapsed = commit_started.elapsed().as_secs_f64();
        sqlite_storage_seconds += commit_elapsed;
        transaction_commit_seconds += commit_elapsed;
        transaction_commit_timings.push(TransactionCommitTiming {
            pages: pages.len() as u64,
            rows_written: transaction_rows_written,
            commit_seconds: commit_elapsed,
        });
        page_processing_seconds += processing_started.elapsed().as_secs_f64();
        last_page_id = pages.last().map(|page| page.0).unwrap_or(last_page_id);
    }
    if summary.pages_analysed == 0 {
        seconds_to_first_progress = Some(analysis_started.elapsed().as_secs_f64());
        progress(&summary, 0, total_pages, started.elapsed().as_secs_f64());
    }
    summary.timings = AnalysisTimings {
        clear_tables,
        clear_tables_total_seconds,
        count_pages_seconds,
        load_provinces_seconds,
        prepare_fact_extractor_seconds,
        batch_fetches,
        page_processing_seconds,
        wiki_extraction_seconds,
        fact_extraction_seconds,
        sqlite_storage_seconds,
        sqlite_table_write_timings,
        prepared_statement_execution_seconds,
        transaction_begin_seconds,
        statement_prepare_seconds,
        transaction_commit_seconds,
        transaction_commit_timings,
        seconds_to_first_page,
        seconds_to_first_progress,
        total_seconds: analysis_started.elapsed().as_secs_f64(),
    };
    Ok(summary)
}

/// Hash logical derived-table rows without modifying the database.
///
/// Generated row IDs and `page_analysis.analysed_at` are omitted. Rows are
/// streamed in rowid order so the hash is repeatable for identical analysis runs.
pub fn hash_derived_tables(
    database_path: &std::path::Path,
    dump_id: i64,
) -> Result<Vec<DerivedTableHash>> {
    let connection = Connection::open_with_flags(database_path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let exists: bool = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM source_dumps WHERE dump_id=?)",
        [dump_id],
        |row| row.get(0),
    )?;
    if !exists {
        anyhow::bail!("dump ID {dump_id} does not exist");
    }

    let tables: [(&str, &[&str]); 5] = [
        (
            "page_analysis",
            &[
                "dump_id",
                "page_id",
                "template_count",
                "wikilink_count",
                "heading_count",
                "tag_count",
            ],
        ),
        (
            "page_template_parameters",
            &[
                "dump_id",
                "source_page_id",
                "source_title",
                "template_index",
                "template_name",
                "parameter_index",
                "parameter_name",
                "is_named",
                "parameter_value",
                "raw_value",
                "evidence_text",
                "extraction_method",
            ],
        ),
        (
            "page_links",
            &[
                "dump_id",
                "source_page_id",
                "source_title",
                "destination",
                "display_text",
            ],
        ),
        (
            "candidate_facts",
            &[
                "dump_id",
                "source_page_id",
                "source_title",
                "subject",
                "relationship",
                "object",
                "evidence_text",
                "extraction_method",
                "confidence",
            ],
        ),
        (
            "entity_candidates",
            &[
                "dump_id",
                "source_page_id",
                "source_title",
                "entity_type",
                "value",
                "evidence_text",
                "extraction_method",
                "source_type",
                "source_id",
                "mod_id",
            ],
        ),
    ];

    let mut results = Vec::with_capacity(tables.len());
    for (table, columns) in tables {
        let projection = columns.join(",");
        let sql = format!("SELECT {projection} FROM {table} WHERE dump_id=? ORDER BY rowid");
        let mut statement = connection.prepare(&sql)?;
        let mut rows = statement.query(params![dump_id])?;
        let mut hasher = Sha256::new();
        hasher.update(b"tamriel-derived-table-v1\0");
        update_hash_bytes(&mut hasher, table.as_bytes());
        for column in columns {
            update_hash_bytes(&mut hasher, column.as_bytes());
        }

        let mut row_count = 0u64;
        while let Some(row) = rows.next()? {
            for index in 0..columns.len() {
                update_hash_value(&mut hasher, row.get_ref(index)?);
            }
            hasher.update([0xff]);
            row_count += 1;
        }
        hasher.update(row_count.to_be_bytes());
        let digest = hasher.finalize();
        let sha256 = digest.iter().map(|byte| format!("{byte:02x}")).collect();
        results.push(DerivedTableHash {
            table,
            rows: row_count,
            sha256,
        });
    }

    Ok(results)
}

fn update_hash_bytes(hasher: &mut Sha256, bytes: &[u8]) {
    hasher.update((bytes.len() as u64).to_be_bytes());
    hasher.update(bytes);
}

fn update_hash_value(hasher: &mut Sha256, value: ValueRef<'_>) {
    match value {
        ValueRef::Null => hasher.update([0]),
        ValueRef::Integer(value) => {
            hasher.update([1]);
            hasher.update(value.to_be_bytes());
        }
        ValueRef::Real(value) => {
            hasher.update([2]);
            hasher.update(value.to_bits().to_be_bytes());
        }
        ValueRef::Text(value) => {
            hasher.update([3]);
            update_hash_bytes(hasher, value);
        }
        ValueRef::Blob(value) => {
            hasher.update([4]);
            update_hash_bytes(hasher, value);
        }
    }
}
