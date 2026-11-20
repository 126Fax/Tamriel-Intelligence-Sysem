use anyhow::{Context, Result};
use bzip2::read::MultiBzDecoder;
use quick_xml::{events::Event, Reader};
use rusqlite::params;
use std::collections::HashMap;
use std::fs::File;
use std::io::BufReader;
use std::path::Path;
use tamriel_processing::for_each_page;

fn read_namespaces(path: &Path) -> Result<HashMap<i64, String>> {
    let file = File::open(path)?;
    let decoder = MultiBzDecoder::new(file);
    let mut reader = Reader::from_reader(BufReader::new(decoder));
    reader.config_mut().trim_text(true);
    let mut buffer = Vec::new();
    let mut inside_namespaces = false;
    let mut current_key: Option<i64> = None;
    let mut result = HashMap::new();
    loop {
        match reader.read_event_into(&mut buffer)? {
            Event::Start(event) => {
                let name = event.local_name();
                if name.as_ref() == b"namespaces" { inside_namespaces = true; }
                else if inside_namespaces && name.as_ref() == b"namespace" {
                    for attribute in event.attributes().with_checks(false) {
                        let attribute = attribute?;
                        if attribute.key.local_name().as_ref() == b"key" {
                            current_key = Some(std::str::from_utf8(&attribute.value)?.parse()?);
                        }
                    }
                }
            }
            Event::Text(event) if current_key.is_some() => {
                let value = event.decode()?;
                let key = current_key.take().unwrap();
                result.insert(key, value.into_owned());
            }
            Event::End(event) => {
                let name = event.local_name();
                if name.as_ref() == b"namespaces" { inside_namespaces = false; }
                if name.as_ref() == b"namespace" { current_key = None; }
            }
            Event::Eof => break,
            _ => {}
        }
        buffer.clear();
    }
    if result.is_empty() {
        result.insert(0, "".to_string());
    }
    Ok(result)
}

pub fn import_dump(path: &Path, database_path: &Path, batch_size: usize) -> Result<(i64, u64)> {
    if batch_size == 0 { anyhow::bail!("batch size must be at least 1"); }
    if !path.is_file() { anyhow::bail!("XML dump not found: {}", path.display()); }
    if !path.to_string_lossy().ends_with(".bz2") {
        anyhow::bail!("The importer expects a compressed .bz2 XML dump.");
    }

    let namespaces = read_namespaces(path).context("reading MediaWiki namespace catalogue")?;
    let mut connection = crate::database::connect(database_path)?;
    let dump_id = crate::database::register_dump(
        &connection,
        path.file_name().and_then(|name| name.to_str()).unwrap_or("uesp.xml.bz2")
    )?;
    crate::database::set_dump_status(&connection, dump_id, "importing")?;

    let file = File::open(path)?;
    let decoder = MultiBzDecoder::new(file);
    let mut batch = Vec::with_capacity(batch_size);
    let mut inserted = 0u64;
    let result = for_each_page(BufReader::new(decoder), None, |page| {
        let page_id: i64 = page.page_id.parse().map_err(|error| format!("invalid page ID: {error}"))?;
        let namespace_id: i64 = page.namespace.parse().map_err(|error| format!("invalid namespace ID: {error}"))?;
        let revision_id: Option<i64> = page.revision_id.parse().ok();
        let namespace_name = namespaces.get(&namespace_id).cloned()
            .unwrap_or_else(|| format!("Unknown ({namespace_id})"));
        batch.push((page_id, page.title, namespace_id, namespace_name, revision_id, page.text));
        if batch.len() >= batch_size {
            inserted += insert_batch(&mut connection, dump_id, &batch).map_err(|error| error.to_string())?;
            batch.clear();
        }
        Ok(())
    });
    if let Err(error) = result {
        crate::database::set_dump_status(&connection, dump_id, "failed")?;
        return Err(anyhow::anyhow!("streaming XML import failed: {error}"));
    }
    if !batch.is_empty() {
        inserted += insert_batch(&mut connection, dump_id, &batch)?;
    }
    crate::database::set_dump_status(&connection, dump_id, "completed")?;
    Ok((dump_id, inserted))
}

fn insert_batch(
    connection: &mut rusqlite::Connection,
    dump_id: i64,
    batch: &[(i64, String, i64, String, Option<i64>, String)],
) -> Result<u64> {
    let transaction = connection.transaction()?;
    let mut statement = transaction.prepare(
        "INSERT OR IGNORE INTO pages
         (dump_id,page_id,title,namespace_id,namespace_name,revision_id,text_length,page_text)
         VALUES (?,?,?,?,?,?,?,?)"
    )?;
    let mut inserted = 0u64;
    for (page_id,title,namespace_id,namespace_name,revision_id,text) in batch {
        inserted += statement.execute(params![
            dump_id,page_id,title,namespace_id,namespace_name,revision_id,
            text.chars().count(),text
        ])? as u64;
    }
    drop(statement);
    transaction.commit()?;
    Ok(inserted)
}
