use anyhow::Result;
use clap::{Parser, Subcommand};
use std::path::PathBuf;
use std::time::Instant;
use tamriel_intelligence::{analysis, cleaner, config, database, ingestion, knowledge, top_down};

#[derive(Parser)]
#[command(name="tamriel-intelligence",version,about="Independent Rust implementation of Tamriel Intelligence System")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Create the Rust database schema.
    InitDb { #[arg(long)] db: Option<PathBuf> },
    /// Import a compressed UESP MediaWiki XML dump into the Rust SQLite database.
    Import {
        #[arg(long)] dump: Option<PathBuf>,
        #[arg(long)] db: Option<PathBuf>,
        #[arg(long,default_value_t=2500)] batch_size: usize,
        #[arg(long)] limit: Option<usize>,
    },
    /// Rebuild Bottom-Up analysis tables for an imported dump.
    Analyse {
        #[arg(long)] dump_id: i64,
        #[arg(long)] db: Option<PathBuf>,
        #[arg(long,default_value_t=32000)] batch_size: usize,
    },
    /// Export evidence-backed candidate facts to JSON.
    BuildKb {
        #[arg(long)] dump_id: i64,
        #[arg(long)] db: Option<PathBuf>,
        #[arg(long)] output: Option<PathBuf>,
    },
    /// Run the complete Rust import -> analysis -> knowledge export pipeline.
    Run {
        #[arg(long)] dump: Option<PathBuf>,
        #[arg(long)] db: Option<PathBuf>,
        #[arg(long)] output: Option<PathBuf>,
        #[arg(long,default_value_t=2500)] import_batch_size: usize,
        #[arg(long,default_value_t=32000)] analysis_batch_size: usize,
        #[arg(long)] limit: Option<usize>,
        #[arg(long)] skip_import: bool,
    },
    /// Ask the Rust Top-Down prototype a question.
    Ask {
        question: String,
        #[arg(long)] db: Option<PathBuf>,
    },
    /// Print row counts from the Rust database.
    Stats { #[arg(long)] db: Option<PathBuf> },
    /// Import user/mod observations from a JSON array, keeping their provenance separate.
    ImportObservations { #[arg(long)] input: PathBuf, #[arg(long)] db: Option<PathBuf> },
    /// Review an exported candidate-fact JSON file without changing it.
    Clean {
        #[arg(long)] input: Option<PathBuf>,
        #[arg(long)] output: Option<PathBuf>,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::InitDb { db } => {
            let path = db.unwrap_or_else(config::default_database);
            let _connection = database::connect(&path)?;
            println!("Rust database initialised: {}",path.display());
        }
        Command::Import { dump,db,batch_size,limit } => {
            let dump_path = config::find_dump(dump)?;
            let db_path = db.unwrap_or_else(config::default_database);
            let started = Instant::now();
            let (dump_id,inserted) = ingestion::import_dump(&dump_path,&db_path,batch_size,limit)?;
            println!("Dump ID: {dump_id}\nNew pages inserted: {inserted}\nElapsed: {:.2}s",started.elapsed().as_secs_f64());
        }
        Command::Analyse { dump_id,db,batch_size } => {
            let db_path = db.unwrap_or_else(config::default_database);
            let started = Instant::now();
            let summary = analysis::analyse_dump_with_progress(&db_path,dump_id,batch_size, |stats, done, total, elapsed| {
                let rate = if elapsed > 0.0 { done as f64 / elapsed } else { 0.0 };
                println!("  Analysing: {done}/{total} pages ({:.1}%) | {:.0} pages/s | links: {} | parameters: {} | facts: {} | typed candidates: {}",
                    if total > 0 { done as f64 * 100.0 / total as f64 } else { 100.0 },
                    rate, stats.wiki_links_extracted, stats.template_parameters_extracted,
                    stats.candidate_facts_extracted, stats.entity_candidates_extracted);
            })?;
            println!("Pages analysed: {}\nWiki links: {}\nTemplate parameters: {}\nCandidate facts: {}\nRace/occupation/book candidates: {}\nElapsed: {:.2}s",
                summary.pages_analysed,summary.wiki_links_extracted,summary.template_parameters_extracted,
                summary.candidate_facts_extracted,summary.entity_candidates_extracted,started.elapsed().as_secs_f64());
        }
        Command::BuildKb { dump_id,db,output } => {
            let db_path = db.unwrap_or_else(config::default_database);
            let output_path = output.unwrap_or_else(config::default_knowledge_base);
            let count = knowledge::export_knowledge_base(&db_path,dump_id,&output_path)?;
            println!("Exported {count} knowledge records to {}",output_path.display());
        }
        Command::Run { dump,db,output,import_batch_size,analysis_batch_size,limit,skip_import } => {
            if import_batch_size == 0 || analysis_batch_size == 0 {
                anyhow::bail!("batch sizes must be at least 1");
            }
            if skip_import && limit.is_some() { anyhow::bail!("--limit applies only when importing; it cannot be used with --skip-import."); }
            let dump_path = config::find_dump(dump)?;
            let db_path = db.unwrap_or_else(config::default_database);
            let output_path = output.unwrap_or_else(config::default_knowledge_base);
            let total_started = Instant::now();
            let dump_id;
            if skip_import {
                let connection = database::connect(&db_path)?;
                dump_id = database::latest_dump_id(&connection,
                    dump_path.file_name().and_then(|name| name.to_str()).unwrap_or(""))?
                    .ok_or_else(|| anyhow::anyhow!("This dump is not imported into the Rust database. Run without --skip-import first."))?;
                println!("Import stage skipped; using Rust dump ID {dump_id}.");
            } else {
                println!("1/3 Importing UESP XML...");
                let started = Instant::now();
                let (id,inserted) = ingestion::import_dump_with_progress(&dump_path,&db_path,import_batch_size,limit, |read, elapsed| {
                    let rate = if elapsed > 0.0 { read as f64 / elapsed } else { 0.0 };
                    let target = limit.map(|value| value.to_string()).unwrap_or_else(|| "unknown".to_string());
                    println!("  XML pages read: {read}/{target} | {:.0} pages/s | elapsed: {:.1}s", rate, elapsed);
                })?;
                dump_id = id;
                println!("  Dump ID {dump_id}; {inserted} new pages; {:.2}s",started.elapsed().as_secs_f64());
            }
            println!("2/3 Running Bottom-Up analysis...");
            let started = Instant::now();
            let summary = analysis::analyse_dump_with_progress(&db_path,dump_id,analysis_batch_size, |stats, done, total, elapsed| {
                let rate = if elapsed > 0.0 { done as f64 / elapsed } else { 0.0 };
                println!("  Analysing: {done}/{total} pages ({:.1}%) | {:.0} pages/s | links: {} | parameters: {} | facts: {} | typed candidates: {}",
                    if total > 0 { done as f64 * 100.0 / total as f64 } else { 100.0 },
                    rate, stats.wiki_links_extracted, stats.template_parameters_extracted,
                    stats.candidate_facts_extracted, stats.entity_candidates_extracted);
            })?;
            println!("  {} pages | {} links | {} template parameters | {} facts | {} typed candidates | {:.2}s",
                summary.pages_analysed,summary.wiki_links_extracted,summary.template_parameters_extracted,
                summary.candidate_facts_extracted,summary.entity_candidates_extracted,started.elapsed().as_secs_f64());
            println!("3/3 Exporting knowledge base...");
            let count = knowledge::export_knowledge_base(&db_path,dump_id,&output_path)?;
            println!("  {count} records -> {}",output_path.display());
            println!("Rust pipeline complete in {:.2}s.",total_started.elapsed().as_secs_f64());
        }
        Command::Ask { question,db } => {
            let db_path = db.unwrap_or_else(config::default_database);
            println!("{}",top_down::answer_question(&db_path,&question)?);
        }
        Command::Stats { db } => {
            let db_path = db.unwrap_or_else(config::default_database);
            let connection = database::connect(&db_path)?;
            for table in ["source_dumps","pages","page_analysis","page_template_parameters","page_links","candidate_facts","entity_candidates","external_observations"] {
                let count: i64 = connection.query_row(&format!("SELECT COUNT(*) FROM {table}"),[],|row| row.get(0))?;
                println!("{table}: {count}");
            }
            println!("Database: {}",db_path.display());
        }
        Command::ImportObservations { input,db } => {
            let db_path = db.unwrap_or_else(config::default_database);
            let count = tamriel_intelligence::external::import_observations(&input,&db_path)?;
            println!("Imported {count} user/mod observations into {}.",db_path.display());
        }
        Command::Clean { input,output } => {
            let input_path = input.unwrap_or_else(config::default_knowledge_base);
            let output_path = output.unwrap_or_else(|| config::project_root().join("rust-version/data/cleaner/review.json"));
            let summary = cleaner::review_file(&input_path,&output_path)?;
            println!("Reviewed: {} | approved: {} | rejected: {} | needs review: {}\nReport: {}",
                summary.total,summary.approved,summary.rejected,summary.needs_review,output_path.display());
        }
    }
    Ok(())
}
