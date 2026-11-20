use anyhow::{Context, Result};
use bzip2::read::BzDecoder;
use quick_xml::events::Event;
use quick_xml::Reader;
use serde::Serialize;
use std::env;
use std::fs::File;
use std::io::{BufReader, Write};

#[derive(Default, Serialize)]
struct Page {
    page_id: String,
    title: String,
    namespace: String,
    revision_id: String,
    text: String,
}

#[derive(Clone, Copy)]
enum Field { None, Title, Namespace, PageId, RevisionId, Text }

fn local_name(name: &[u8]) -> &[u8] {
    name.rsplit(|byte| *byte == b':').next().unwrap_or(name)
}

fn append_field(page: &mut Page, field: Field, value: &str) {
    match field {
        Field::Title => page.title.push_str(value),
        Field::Namespace => page.namespace.push_str(value),
        Field::PageId => page.page_id.push_str(value),
        Field::RevisionId => page.revision_id.push_str(value),
        Field::Text => page.text.push_str(value),
        Field::None => {}
    }
}

fn main() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 || args.len() > 3 {
        anyhow::bail!("Usage: uesp-rust-reader <dump.xml.bz2> [page-limit]");
    }
    let limit: usize = args.get(2).map(|v| v.parse()).transpose()
        .context("page-limit must be a non-negative integer")?.unwrap_or(0);

    let file = File::open(&args[1]).with_context(|| format!("opening {}", args[1]))?;
    let decoder = BzDecoder::new(BufReader::new(file));
    let mut reader = Reader::from_reader(BufReader::new(decoder));
    reader.trim_text(false);

    let stdout = std::io::stdout();
    let mut output = std::io::BufWriter::new(stdout.lock());
    let mut buffer = Vec::new();
    let mut page: Option<Page> = None;
    let mut in_revision = false;
    let mut capture = Field::None;
    let mut count = 0usize;

    loop {
        match reader.read_event_into(&mut buffer)? {
            Event::Start(event) => {
                let name = local_name(event.local_name().as_ref()).to_vec();
                if name == b"page" {
                    page = Some(Page::default());
                    in_revision = false;
                } else if name == b"revision" && page.is_some() {
                    in_revision = true;
                    if let Some(p) = page.as_mut() {
                        p.revision_id.clear();
                        p.text.clear();
                    }
                } else if page.is_some() {
                    capture = match name.as_slice() {
                        b"title" => Field::Title,
                        b"ns" => Field::Namespace,
                        b"id" if in_revision => Field::RevisionId,
                        b"id" => Field::PageId,
                        b"text" if in_revision => Field::Text,
                        _ => Field::None,
                    };
                }
            }
            Event::Text(event) => {
                if let Some(p) = page.as_mut() {
                    let value = event.unescape()?.into_owned();
                    append_field(p, capture, &value);
                }
            }
            Event::CData(event) => {
                if let Some(p) = page.as_mut() {
                    let value = event.decode()?.into_owned();
                    append_field(p, capture, &value);
                }
            }
            Event::End(event) => {
                let name = local_name(event.local_name().as_ref()).to_vec();
                if name == b"title" || name == b"ns" || name == b"id" || name == b"text" {
                    capture = Field::None;
                } else if name == b"revision" {
                    in_revision = false;
                } else if name == b"page" {
                    if let Some(p) = page.take() {
                        if !p.text.is_empty() {
                            serde_json::to_writer(&mut output, &p)?;
                            output.write_all(b"\n")?;
                            count += 1;
                            if limit > 0 && count >= limit { break; }
                        }
                    }
                    capture = Field::None;
                }
            }
            Event::Eof => break,
            _ => {}
        }
        buffer.clear();
    }
    output.flush()?;
    Ok(())
}
