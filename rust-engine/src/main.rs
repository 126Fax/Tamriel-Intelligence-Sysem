use bzip2::read::MultiBzDecoder;
use serde::Deserialize;
use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Write};
use tamriel_processing::{count_wikitext_structures, extract_candidate_facts, for_each_page, CandidateFact, PageText};

#[derive(Deserialize)]
struct InputPage {
    page_id: i64,
    title: String,
    text: String,
}

fn usage() -> ! {
    eprintln!("Usage:");
    eprintln!("  tamriel-processing xml <dump.xml.bz2> [page-limit]");
    eprintln!("  tamriel-processing facts <pages.jsonl>");
    eprintln!("  tamriel-processing wiki <pages.jsonl>");
    eprintln!("  tamriel-processing db <facts.jsonl> <output.sqlite> [batch-size]");
    std::process::exit(2);
}


fn insert_fact_batch(
    connection: &mut rusqlite::Connection,
    facts: &[CandidateFact],
) -> Result<usize, rusqlite::Error> {
    let transaction = connection.transaction()?;
    let mut inserted = 0usize;
    {
        let mut statement = transaction.prepare(
            "INSERT OR IGNORE INTO candidate_facts
             (source_page_id, source_page, subject, relationship, object,
              evidence, extraction_method, confidence)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )?;
        for fact in facts {
            inserted += statement.execute(rusqlite::params![
                fact.source_page_id, fact.source_page, fact.subject,
                fact.relationship, fact.object, fact.evidence,
                fact.extraction_method, fact.confidence
            ])?;
        }
    }
    transaction.commit()?;
    Ok(inserted)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 { usage(); }

    match args[1].as_str() {
        "xml" => {
            let limit = args.get(3).map(|value| value.parse::<usize>()).transpose()?;
            let file = File::open(&args[2])?;
            let decoder = MultiBzDecoder::new(file);
            let stdout = io::stdout();
            let mut output = io::BufWriter::new(stdout.lock());
            for_each_page(BufReader::new(decoder), limit, |page| {
                serde_json::to_writer(&mut output, &page).map_err(|error| error.to_string())?;
                output.write_all(b"\n").map_err(|error| error.to_string())?;
                Ok(())
            }).map_err(io::Error::other)?;
            output.flush()?;
        }
        "db" => {
            if args.len() < 4 { usage(); }
            let batch_size = args.get(4).map(|value| value.parse::<usize>()).transpose()?.unwrap_or(1000);
            if batch_size == 0 { return Err("batch size must be at least 1".into()); }
            let file = File::open(&args[2])?;
            let input = BufReader::new(file);
            let mut connection = rusqlite::Connection::open(&args[3])?;
            connection.execute_batch(
                "CREATE TABLE IF NOT EXISTS candidate_facts (
                    fact_id INTEGER PRIMARY KEY,
                    source_page_id INTEGER NOT NULL,
                    source_page TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    object TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    extraction_method TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    UNIQUE(source_page_id, subject, relationship, object, evidence)
                );"
            )?;
            let mut batch: Vec<CandidateFact> = Vec::with_capacity(batch_size);
            let mut inserted = 0usize;
            for line in input.lines() {
                let line = line?;
                if line.trim().is_empty() { continue; }
                batch.push(serde_json::from_str(&line)?);
                if batch.len() >= batch_size {
                    inserted += insert_fact_batch(&mut connection, &batch)?;
                    batch.clear();
                }
            }
            if !batch.is_empty() { inserted += insert_fact_batch(&mut connection, &batch)?; }
            let count: i64 = connection.query_row("SELECT COUNT(*) FROM candidate_facts", [], |row| row.get(0))?;
            println!("{}", serde_json::json!({"records_seen": inserted, "rows_in_database": count}));
        }
        "wiki" => {
            let file = File::open(&args[2])?;
            let input = BufReader::new(file);
            let stdout = io::stdout();
            let mut output = io::BufWriter::new(stdout.lock());
            for line in input.lines() {
                let line = line?;
                if line.trim().is_empty() { continue; }
                let page: InputPage = serde_json::from_str(&line)?;
                let page = PageText { page_id: page.page_id, title: page.title, text: page.text };
                let stats = count_wikitext_structures(&page);
                serde_json::to_writer(&mut output, &stats)?;
                output.write_all(b"\n")?;
            }
            output.flush()?;
        }
        "facts" => {
            let file = File::open(&args[2])?;
            let input = BufReader::new(file);
            let stdout = io::stdout();
            let mut output = io::BufWriter::new(stdout.lock());
            for line in input.lines() {
                let line = line?;
                if line.trim().is_empty() { continue; }
                let page: InputPage = serde_json::from_str(&line)?;
                let page = PageText { page_id: page.page_id, title: page.title, text: page.text };
                for fact in extract_candidate_facts(&page) {
                    serde_json::to_writer(&mut output, &fact)?;
                    output.write_all(b"\n")?;
                }
            }
            output.flush()?;
        }
        _ => usage(),
    }
    Ok(())
}
