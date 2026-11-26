use anyhow::{bail, Context, Result};
use regex::Regex;
use rusqlite::{params, Connection, OptionalExtension, Row};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::sync::LazyLock;
use std::{
    fs::OpenOptions,
    io::{BufWriter, Write},
    path::Path,
};

use crate::{database, wiki};

pub const PROCESSOR_VERSION: &str = "1.0";

static EXTERNAL_LINK_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[(https?://[^\s\]]+)(?:\s+([^\]]+))?\]").unwrap());

const FORCE_PAGE_BATCH: &str = "
    SELECT dump_id,page_id,title,namespace_id,namespace_name,revision_id,page_text
    FROM pages
    WHERE dump_id=?1 AND page_id>?2
    ORDER BY page_id
    LIMIT ?3
";

const UNPREPARED_PAGE_BATCH: &str = "
    SELECT p.dump_id,p.page_id,p.title,p.namespace_id,p.namespace_name,
           p.revision_id,p.page_text
    FROM pages AS p
    LEFT JOIN ai_pages AS a ON a.dump_id=p.dump_id AND a.page_id=p.page_id
    WHERE p.dump_id=?1 AND p.page_id>?2
      AND (a.page_id IS NULL OR a.processor_version<>?3)
    ORDER BY p.page_id
    LIMIT ?4
";

#[derive(Debug)]
struct SourcePage {
    dump_id: i64,
    page_id: i64,
    title: String,
    namespace_id: i64,
    namespace_name: String,
    revision_id: Option<i64>,
    page_text: String,
}

fn read_source_page(row: &Row<'_>) -> rusqlite::Result<SourcePage> {
    Ok(SourcePage {
        dump_id: row.get(0)?,
        page_id: row.get(1)?,
        title: row.get(2)?,
        namespace_id: row.get(3)?,
        namespace_name: row.get(4)?,
        revision_id: row.get(5)?,
        page_text: row.get(6)?,
    })
}

#[derive(Debug, Deserialize, Serialize)]
struct PreparedHeading {
    level: usize,
    text: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct PreparedTemplateParameter {
    name: String,
    value: String,
    raw_value: String,
    explicit_name: bool,
}

#[derive(Debug, Deserialize, Serialize)]
struct PreparedTemplate {
    name: String,
    parameters: Vec<PreparedTemplateParameter>,
    evidence: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct PreparedLink {
    destination: String,
    display_text: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct PreparedExternalLink {
    url: String,
    display_text: String,
}

#[derive(Debug, Serialize)]
struct PreparedPage {
    dump_id: i64,
    page_id: i64,
    title: String,
    namespace_id: i64,
    namespace_name: String,
    revision_id: Option<i64>,
    readable_text: String,
    headings: Vec<PreparedHeading>,
    templates: Vec<PreparedTemplate>,
    links: Vec<PreparedLink>,
    categories: Vec<String>,
    external_links: Vec<PreparedExternalLink>,
    source_text_hash: String,
    processor_version: String,
}

fn extract_headings(page: &SourcePage) -> Vec<PreparedHeading> {
    page.page_text
        .lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            let level = trimmed.chars().take_while(|ch| *ch == '=').count();
            let trailing_equals = trimmed.chars().rev().take_while(|ch| *ch == '=').count();
            if level == 0 || level > 6 || trailing_equals != level || trimmed.len() < level * 2 {
                return None;
            }
            let title = &trimmed[level..trimmed.len() - level];
            let text = wiki::analyse_wikitext(page.page_id, &page.title, title)
                .plain_text
                .trim()
                .to_string();
            (!text.is_empty()).then_some(PreparedHeading { level, text })
        })
        .collect()
}

fn extract_external_links(page: &SourcePage) -> Vec<PreparedExternalLink> {
    EXTERNAL_LINK_RE
        .captures_iter(&page.page_text)
        .filter_map(|captures| {
            let url = captures.get(1)?.as_str().trim().to_string();
            let display_text = captures
                .get(2)
                .map(|value| {
                    wiki::analyse_wikitext(page.page_id, &page.title, value.as_str()).plain_text
                })
                .unwrap_or_default();
            Some(PreparedExternalLink { url, display_text })
        })
        .collect()
}

fn readable_text(plain_text: &str) -> String {
    EXTERNAL_LINK_RE
        .replace_all(plain_text, |captures: &regex::Captures<'_>| {
            captures
                .get(2)
                .or_else(|| captures.get(1))
                .map(|value| value.as_str())
                .unwrap_or_default()
                .to_string()
        })
        .trim()
        .to_string()
}

fn prepare_page(page: &SourcePage) -> Result<PreparedPage> {
    let analysis = wiki::analyse_wikitext(page.page_id, &page.title, &page.page_text);
    let mut templates = analysis
        .templates
        .into_iter()
        .map(|template| PreparedTemplate {
            name: template.name,
            parameters: Vec::new(),
            evidence: template.evidence,
        })
        .collect::<Vec<_>>();
    for parameter in analysis.parameters {
        let template = templates
            .get_mut(parameter.template_index)
            .with_context(|| {
                format!(
                    "template parameter on page {} refers to missing template index {}",
                    page.page_id, parameter.template_index
                )
            })?;
        template.parameters.push(PreparedTemplateParameter {
            name: parameter.parameter_name,
            value: parameter.value,
            raw_value: parameter.raw_value,
            explicit_name: parameter.is_named,
        });
    }

    let links = analysis
        .links
        .iter()
        .map(|link| PreparedLink {
            destination: link.destination.clone(),
            display_text: link.display_text.clone(),
        })
        .collect::<Vec<_>>();
    let categories = analysis
        .links
        .iter()
        .filter_map(|link| {
            let (namespace, category) = link.destination.split_once(':')?;
            namespace
                .eq_ignore_ascii_case("category")
                .then(|| category.trim().to_string())
        })
        .filter(|category| !category.is_empty())
        .collect();
    let source_text_hash = format!("{:x}", Sha256::digest(page.page_text.as_bytes()));

    Ok(PreparedPage {
        dump_id: page.dump_id,
        page_id: page.page_id,
        title: page.title.clone(),
        namespace_id: page.namespace_id,
        namespace_name: page.namespace_name.clone(),
        revision_id: page.revision_id,
        readable_text: readable_text(&analysis.plain_text),
        headings: extract_headings(page),
        templates,
        links,
        categories,
        external_links: extract_external_links(page),
        source_text_hash,
        processor_version: PROCESSOR_VERSION.to_string(),
    })
}

fn fetch_page_batch(
    connection: &Connection,
    dump_id: i64,
    last_page_id: i64,
    batch_size: i64,
    force: bool,
) -> Result<Vec<SourcePage>> {
    if force {
        let mut statement = connection.prepare(FORCE_PAGE_BATCH)?;
        let rows =
            statement.query_map(params![dump_id, last_page_id, batch_size], read_source_page)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    } else {
        let mut statement = connection.prepare(UNPREPARED_PAGE_BATCH)?;
        let rows = statement.query_map(
            params![dump_id, last_page_id, PROCESSOR_VERSION, batch_size],
            read_source_page,
        )?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }
}

fn save_prepared_batch(connection: &mut Connection, pages: &[PreparedPage]) -> Result<()> {
    let transaction = connection.transaction()?;
    {
        let mut statement = transaction.prepare_cached(
            "INSERT INTO ai_pages (
                 dump_id,page_id,title,namespace_id,namespace_name,revision_id,
                 readable_text,headings_json,templates_json,links_json,
                 categories_json,external_links_json,source_text_hash,
                 processor_version,prepared_at
             ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
             ON CONFLICT(dump_id,page_id) DO UPDATE SET
                 title=excluded.title,
                 namespace_id=excluded.namespace_id,
                 namespace_name=excluded.namespace_name,
                 revision_id=excluded.revision_id,
                 readable_text=excluded.readable_text,
                 headings_json=excluded.headings_json,
                 templates_json=excluded.templates_json,
                 links_json=excluded.links_json,
                 categories_json=excluded.categories_json,
                 external_links_json=excluded.external_links_json,
                 source_text_hash=excluded.source_text_hash,
                 processor_version=excluded.processor_version,
                 prepared_at=CURRENT_TIMESTAMP",
        )?;
        for page in pages {
            statement.execute(params![
                page.dump_id,
                page.page_id,
                page.title,
                page.namespace_id,
                page.namespace_name,
                page.revision_id,
                page.readable_text,
                serde_json::to_string(&page.headings)?,
                serde_json::to_string(&page.templates)?,
                serde_json::to_string(&page.links)?,
                serde_json::to_string(&page.categories)?,
                serde_json::to_string(&page.external_links)?,
                page.source_text_hash,
                page.processor_version,
            ])?;
        }
    }
    transaction.commit()?;
    Ok(())
}

pub fn prepare_dump(
    database_path: &Path,
    dump_id: i64,
    batch_size: usize,
    force: bool,
) -> Result<usize> {
    let batch_size =
        i64::try_from(batch_size).context("AI preparation batch size exceeds SQLite limits")?;
    if batch_size < 1 {
        bail!("AI preparation batch size must be at least 1");
    }

    let mut connection = database::connect(database_path)?;
    let status: Option<String> = connection
        .query_row(
            "SELECT import_status FROM source_dumps WHERE dump_id=?",
            [dump_id],
            |row| row.get(0),
        )
        .optional()?;
    match status.as_deref() {
        None => bail!("dump ID {dump_id} does not exist"),
        Some("completed") => {}
        Some(status) => bail!("dump ID {dump_id} is not completed (status: {status})"),
    }

    let mut processed = 0usize;
    let mut last_page_id = -1;
    loop {
        let source_pages = fetch_page_batch(&connection, dump_id, last_page_id, batch_size, force)?;
        if source_pages.is_empty() {
            break;
        }
        let prepared_pages = source_pages
            .iter()
            .map(prepare_page)
            .collect::<Result<Vec<_>>>()?;
        save_prepared_batch(&mut connection, &prepared_pages)?;
        processed += prepared_pages.len();
        last_page_id = source_pages
            .last()
            .expect("non-empty batch checked above")
            .page_id;
    }
    Ok(processed)
}

pub fn export_prepared_dump(
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
        bail!("dump ID {dump_id} does not exist");
    }
    let page_count: i64 = connection.query_row(
        "SELECT COUNT(*) FROM pages WHERE dump_id=?1",
        [dump_id],
        |row| row.get(0),
    )?;
    let prepared_count: i64 = connection.query_row(
        "SELECT COUNT(*) FROM ai_pages WHERE dump_id=?1 AND processor_version=?2",
        params![dump_id, PROCESSOR_VERSION],
        |row| row.get(0),
    )?;
    if page_count == 0 {
        bail!("dump ID {dump_id} has no prepared AI-readable pages");
    }
    if prepared_count != page_count {
        bail!(
            "dump ID {dump_id} has {prepared_count} of {page_count} pages prepared with the current version; run prepare-ai-pages first"
        );
    }

    let mut statement = connection.prepare(
        "SELECT dump_id,page_id,title,namespace_id,namespace_name,revision_id,
                readable_text,headings_json,templates_json,links_json,categories_json,
                external_links_json,source_text_hash,processor_version
         FROM ai_pages WHERE dump_id=?1 ORDER BY page_id",
    )?;
    if let Some(parent) = output_path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
    {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("creating export directory {}", parent.display()))?;
    }
    let file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(output_path)
        .with_context(|| {
            format!(
                "creating AI-readable export without replacing an existing file: {}",
                output_path.display()
            )
        })?;
    let mut output = BufWriter::new(file);
    let write_result = (|| -> Result<usize> {
        let mut rows = statement.query([dump_id])?;
        let mut written = 0usize;
        while let Some(row) = rows.next()? {
            let page = PreparedPage {
                dump_id: row.get(0)?,
                page_id: row.get(1)?,
                title: row.get(2)?,
                namespace_id: row.get(3)?,
                namespace_name: row.get(4)?,
                revision_id: row.get(5)?,
                readable_text: row.get(6)?,
                headings: serde_json::from_str(&row.get::<_, String>(7)?)?,
                templates: serde_json::from_str(&row.get::<_, String>(8)?)?,
                links: serde_json::from_str(&row.get::<_, String>(9)?)?,
                categories: serde_json::from_str(&row.get::<_, String>(10)?)?,
                external_links: serde_json::from_str(&row.get::<_, String>(11)?)?,
                source_text_hash: row.get(12)?,
                processor_version: row.get(13)?,
            };
            serde_json::to_writer(&mut output, &page)?;
            output.write_all(b"\n")?;
            written += 1;
        }
        output.flush()?;
        output.get_ref().sync_all()?;
        Ok(written)
    })();
    match write_result {
        Ok(written) => Ok(written),
        Err(error) => {
            drop(output);
            if let Err(cleanup_error) = std::fs::remove_file(output_path) {
                return Err(error.context(format!(
                    "also failed to remove incomplete export {}: {cleanup_error}",
                    output_path.display()
                )));
            }
            Err(error)
        }
    }
}
