use bzip2::read::BzDecoder;
use serde::Deserialize;
use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Write};
use tamriel_processing::{extract_candidate_facts, read_pages, PageText};

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
    std::process::exit(2);
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 { usage(); }

    match args[1].as_str() {
        "xml" => {
            let limit = args.get(3).map(|value| value.parse::<usize>()).transpose()?;
            let file = File::open(&args[2])?;
            let decoder = BzDecoder::new(file);
            let pages = read_pages(BufReader::new(decoder), limit)
                .map_err(io::Error::other)?;
            let stdout = io::stdout();
            let mut output = io::BufWriter::new(stdout.lock());
            for page in pages {
                serde_json::to_writer(&mut output, &page)?;
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
