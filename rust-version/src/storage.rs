use anyhow::{Context, Result};
use rusqlite::{Connection, OpenFlags};
use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
struct StorageFile {
    path: PathBuf,
    bytes: u64,
    category: &'static str,
}

#[derive(Debug)]
struct DatabaseObjectStats {
    name: String,
    object_type: String,
    table_name: String,
    pages: u64,
    allocated_bytes: u64,
    payload_bytes: u64,
    unused_bytes: u64,
}

#[derive(Debug, Default)]
struct TableStorageStats {
    rows: u64,
    table_bytes: u64,
    index_bytes: u64,
    other_bytes: u64,
    table_payload_bytes: u64,
    index_payload_bytes: u64,
    unused_bytes: u64,
}

#[derive(Debug)]
struct DatabaseStats {
    page_size: u64,
    page_count: u64,
    free_pages: u64,
    table_rows: Vec<(String, u64)>,
    objects: Option<Vec<DatabaseObjectStats>>,
    dbstat_error: Option<String>,
}

fn human_size(bytes: u64) -> String {
    const UNITS: [&str; 5] = ["B", "KiB", "MiB", "GiB", "TiB"];
    let mut value = bytes as f64;
    let mut unit = 0;
    while value >= 1024.0 && unit < UNITS.len() - 1 {
        value /= 1024.0;
        unit += 1;
    }
    if unit == 0 {
        format!("{bytes} B")
    } else {
        format!("{value:.2} {}", UNITS[unit])
    }
}

fn classify(path: &Path, root: &Path) -> &'static str {
    let relative = path.strip_prefix(root).unwrap_or(path);
    let text = relative.to_string_lossy().replace('\\', "/");
    let name = path.file_name().and_then(|value| value.to_str()).unwrap_or("");

    if text.starts_with("data/raw/") || name.ends_with(".xml.bz2") {
        "Original source dump"
    } else if name.ends_with(".db") || name.ends_with(".db-wal") || name.ends_with(".db-shm") {
        "SQLite database and sidecars"
    } else if text.starts_with("rust-version/data/") || name == "knowledge_base.json" {
        "Generated exports and reports"
    } else {
        "Other tracked data"
    }
}

fn collect_files(directory: &Path, root: &Path, files: &mut Vec<StorageFile>) -> Result<()> {
    if !directory.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(directory).with_context(|| format!("reading {}", directory.display()))? {
        let entry = entry?;
        let path = entry.path();
        let file_type = entry.file_type()?;
        if file_type.is_dir() {
            collect_files(&path, root, files)?;
        } else if file_type.is_file() {
            let bytes = entry.metadata()?.len();
            files.push(StorageFile {
                category: classify(&path, root),
                path,
                bytes,
            });
        }
    }
    Ok(())
}

fn add_database_sidecars(path: &Path, root: &Path, files: &mut Vec<StorageFile>) -> Result<()> {
    for candidate in [
        path.to_path_buf(),
        PathBuf::from(format!("{}-wal", path.display())),
        PathBuf::from(format!("{}-shm", path.display())),
    ] {
        if candidate.is_file() && !files.iter().any(|file| file.path == candidate) {
            files.push(StorageFile {
                category: classify(&candidate, root),
                bytes: fs::metadata(&candidate)?.len(),
                path: candidate,
            });
        }
    }
    Ok(())
}

fn database_object_stats(connection: &Connection) -> Result<Vec<DatabaseObjectStats>> {
    let mut statement = connection.prepare(
        "SELECT
            d.name,
            COALESCE(m.type, 'internal'),
            COALESCE(m.tbl_name, d.name),
            COUNT(*),
            COALESCE(SUM(d.pgsize), 0),
            COALESCE(SUM(d.payload), 0),
            COALESCE(SUM(d.unused), 0)
         FROM dbstat AS d
         LEFT JOIN sqlite_master AS m ON m.name = d.name
         GROUP BY d.name, m.type, m.tbl_name
         ORDER BY SUM(d.pgsize) DESC, d.name ASC",
    )?;

    let rows = statement.query_map([], |row| {
        Ok(DatabaseObjectStats {
            name: row.get(0)?,
            object_type: row.get(1)?,
            table_name: row.get(2)?,
            pages: row.get::<_, i64>(3)?.max(0) as u64,
            allocated_bytes: row.get::<_, i64>(4)?.max(0) as u64,
            payload_bytes: row.get::<_, i64>(5)?.max(0) as u64,
            unused_bytes: row.get::<_, i64>(6)?.max(0) as u64,
        })
    })?;

    rows.collect::<rusqlite::Result<Vec<_>>>()
        .context("reading SQLite dbstat page statistics")
}

fn database_stats(path: &Path) -> Result<Option<DatabaseStats>> {
    if !path.is_file() {
        return Ok(None);
    }
    let connection = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .with_context(|| format!("opening database read-only: {}", path.display()))?;
    let page_size: i64 = connection.query_row("PRAGMA page_size", [], |row| row.get(0))?;
    let page_count: i64 = connection.query_row("PRAGMA page_count", [], |row| row.get(0))?;
    let free_pages: i64 = connection.query_row("PRAGMA freelist_count", [], |row| row.get(0))?;

    let mut table_rows = Vec::new();
    let mut table_statement = connection.prepare(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    )?;
    let table_names = table_statement
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<rusqlite::Result<Vec<_>>>()?;

    for table in table_names {
        let sql = format!("SELECT COUNT(*) FROM \"{}\"", table.replace('"', "\"\""));
        let count: i64 = connection.query_row(&sql, [], |row| row.get(0))?;
        table_rows.push((table, count.max(0) as u64));
    }

    let (objects, dbstat_error) = match database_object_stats(&connection) {
        Ok(objects) => (Some(objects), None),
        Err(error) => (None, Some(error.to_string())),
    };

    Ok(Some(DatabaseStats {
        page_size: page_size.max(0) as u64,
        page_count: page_count.max(0) as u64,
        free_pages: free_pages.max(0) as u64,
        table_rows,
        objects,
        dbstat_error,
    }))
}

fn print_database_breakdown(stats: &DatabaseStats) {
    if let Some(objects) = &stats.objects {
        let row_counts: HashMap<&str, u64> = stats
            .table_rows
            .iter()
            .map(|(name, rows)| (name.as_str(), *rows))
            .collect();
        let mut tables = BTreeMap::<String, TableStorageStats>::new();

        for object in objects {
            let table = tables.entry(object.table_name.clone()).or_default();
            if object.object_type == "table" {
                table.table_bytes += object.allocated_bytes;
                table.table_payload_bytes += object.payload_bytes;
            } else if object.object_type == "index" {
                table.index_bytes += object.allocated_bytes;
                table.index_payload_bytes += object.payload_bytes;
            } else {
                table.other_bytes += object.allocated_bytes;
            }
            table.unused_bytes += object.unused_bytes;
        }

        for (name, table) in &mut tables {
            table.rows = row_counts.get(name.as_str()).copied().unwrap_or(0);
        }

        println!("  Per-table storage (including each table's indexes):");
        println!(
            "    {:<32} {:>10} {:>11} {:>11} {:>11} {:>12}",
            "Table", "Rows", "Table data", "Indexes", "Total", "Avg/row"
        );
        for (name, table) in &tables {
            let total = table.table_bytes + table.index_bytes + table.other_bytes;
            let average = if table.rows > 0 {
                human_size(total / table.rows)
            } else {
                "n/a".to_string()
            };
            println!(
                "    {:<32} {:>10} {:>11} {:>11} {:>11} {:>12}",
                name,
                table.rows,
                human_size(table.table_bytes),
                human_size(table.index_bytes),
                human_size(total),
                average
            );
        }

        println!();
        println!("  Per-object page breakdown (tables and indexes):");
        println!(
            "    {:<32} {:<7} {:<28} {:>7} {:>11} {:>11} {:>11}",
            "Object", "Type", "Belongs to", "Pages", "Allocated", "Payload", "Unused"
        );
        for object in objects {
            println!(
                "    {:<32} {:<7} {:<28} {:>7} {:>11} {:>11} {:>11}",
                object.name,
                object.object_type,
                object.table_name,
                object.pages,
                human_size(object.allocated_bytes),
                human_size(object.payload_bytes),
                human_size(object.unused_bytes)
            );
        }

        let total_payload: u64 = objects.iter().map(|item| item.payload_bytes).sum();
        let total_unused: u64 = objects.iter().map(|item| item.unused_bytes).sum();
        println!();
        println!("  dbstat totals:");
        println!("    B-tree allocated pages: {}", human_size(objects.iter().map(|item| item.allocated_bytes).sum()));
        println!("    Payload bytes:           {}", human_size(total_payload));
        println!("    Unused bytes in pages:   {}", human_size(total_unused));
        println!("    Free-list pages:         reported separately above");
        println!(
            "    Note: payload is SQLite B-tree payload, not a compressed-size estimate of logical text."
        );
    } else if let Some(error) = &stats.dbstat_error {
        println!("  Per-table storage breakdown unavailable: {error}");
        println!("  This SQLite build may not include the dbstat virtual table.");
    }
}

/// Print a read-only inventory of the source dump, SQLite files and generated data.
pub fn print_report(project_root: &Path, database_path: &Path) -> Result<()> {
    let database_path = if database_path.is_absolute() {
        database_path.to_path_buf()
    } else {
        project_root.join(database_path)
    };
    let mut files = Vec::new();
    for relative in ["data/raw", "data/database", "rust-version/data"] {
        collect_files(&project_root.join(relative), project_root, &mut files)?;
    }
    let python_export = project_root.join("knowledge_base.json");
    if python_export.is_file() {
        files.push(StorageFile {
            category: classify(&python_export, project_root),
            bytes: fs::metadata(&python_export)?.len(),
            path: python_export,
        });
    }
    add_database_sidecars(&database_path, project_root, &mut files)?;
    files.sort_by(|left, right| left.path.cmp(&right.path));

    let mut totals = BTreeMap::<&str, u64>::new();
    for file in &files {
        *totals.entry(file.category).or_default() += file.bytes;
    }
    let total_bytes: u64 = files.iter().map(|file| file.bytes).sum();
    let source_bytes = totals.get("Original source dump").copied().unwrap_or(0);
    let generated_bytes = totals.get("Generated exports and reports").copied().unwrap_or(0);
    let database_bytes = totals.get("SQLite database and sidecars").copied().unwrap_or(0);

    println!("Tamriel Intelligence storage report");
    println!("===================================");
    println!("All sizes use binary units (1 MiB = 1,024 KiB).");
    println!();
    println!("Storage totals:");
    println!("  Original compressed source dump: {}", human_size(source_bytes));
    println!("  SQLite databases and sidecars:   {}", human_size(database_bytes));
    println!("  Generated exports and reports:   {}", human_size(generated_bytes));
    println!("  All inventoried data:             {}", human_size(total_bytes));
    println!();

    println!("Files:");
    if files.is_empty() {
        println!("  No data files found in the scanned locations.");
    } else {
        for file in &files {
            let display_path = file.path.strip_prefix(project_root).unwrap_or(&file.path);
            println!("  {:>12}  {}", human_size(file.bytes), display_path.display());
        }
    }
    println!();

    println!("Rust SQLite database details:");
    println!("  Path: {}", database_path.display());
    match database_stats(&database_path)? {
        Some(stats) => {
            let allocated = stats.page_size.saturating_mul(stats.page_count);
            let free = stats.page_size.saturating_mul(stats.free_pages);
            println!("  Allocated SQLite pages: {}", human_size(allocated));
            println!("  Free pages inside database: {} ({})", stats.free_pages, human_size(free));
            println!("  Page size: {} bytes", stats.page_size);
            println!("  Table row counts:");
            for (table, rows) in &stats.table_rows {
                println!("    {table}: {rows}");
            }
            println!();
            print_database_breakdown(&stats);
        }
        None => println!("  Database file not found; import or initialise it first."),
    }
    println!();
    println!("Note: SQLite page statistics describe the main database file. WAL/SHM sidecars");
    println!("are listed separately and included in the SQLite file total. No files were changed.");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{database_object_stats, human_size};
    use rusqlite::Connection;

    #[test]
    fn formats_sizes_in_understandable_units() {
        assert_eq!(human_size(512), "512 B");
        assert_eq!(human_size(1024), "1.00 KiB");
        assert_eq!(human_size(1024 * 1024), "1.00 MiB");
        assert_eq!(human_size(1024_u64 * 1024 * 1024), "1.00 GiB");
    }

    #[test]
    fn reports_table_and_index_pages_from_dbstat() {
        let connection = Connection::open_in_memory().expect("open in-memory database");
        connection
            .execute_batch(
                "CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT);
                 CREATE INDEX sample_value_idx ON sample(value);
                 INSERT INTO sample(value) VALUES ('alpha'), ('beta'), ('gamma');",
            )
            .expect("create sample table and index");

        let objects = database_object_stats(&connection).expect("read dbstat");
        assert!(objects.iter().any(|object| {
            object.name == "sample" && object.object_type == "table"
        }));
        assert!(objects.iter().any(|object| {
            object.name == "sample_value_idx" && object.object_type == "index"
        }));
        assert!(objects.iter().all(|object| {
            object.allocated_bytes >= object.payload_bytes
                && object.allocated_bytes >= object.unused_bytes
        }));
    }
}
