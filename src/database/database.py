import sqlite3
from pathlib import Path

# Locate the project directories.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = PROJECT_ROOT / "data" / "database" / "tamriel_intelligence.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialise_database():
    connection = get_connection()

    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
            schema = schema_file.read()

        connection.executescript(schema)

    finally:
        connection.close()


def register_source_dump(source_name, dump_date=None):
    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT INTO source_dumps (source_name, dump_date)
            VALUES (?, ?)
            """,
            (source_name, dump_date),
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def insert_page(dump_id, page_data, namespace_name):
    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO pages (
                dump_id,
                page_id,
                title,
                namespace_id,
                namespace_name,
                revision_id,
                text_length,
                page_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dump_id,
                int(page_data["page_id"]),
                page_data["title"],
                int(page_data["namespace"]),
                namespace_name,
                int(page_data["revision_id"]),
                len(page_data["text"]),
                page_data["text"],
            ),
        )

        connection.commit()

    finally:
        connection.close()


def insert_pages_batch(
    dump_id,
    pages,
    namespace_map,
    batch_size=1000,
    progress_callback=None,
):
    if batch_size < 1:
        raise ValueError("Batch size must be at least 1.")

    connection = get_connection()

    inserted_count = 0
    processed_count = 0
    batch = []

    try:
        for page_data in pages:
            namespace_id = int(page_data["namespace"])

            batch.append(
                (
                    dump_id,
                    int(page_data["page_id"]),
                    page_data["title"],
                    namespace_id,
                    namespace_map.get(namespace_id, "Unknown"),
                    int(page_data["revision_id"])
                    if page_data["revision_id"] is not None
                    else None,
                    len(page_data["text"]),
                    page_data["text"],
                )
            )

            processed_count += 1

            if len(batch) >= batch_size:
                before = connection.total_changes

                connection.executemany(
                    """
                    INSERT OR IGNORE INTO pages (
                        dump_id,
                        page_id,
                        title,
                        namespace_id,
                        namespace_name,
                        revision_id,
                        text_length,
                        page_text
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )

                inserted_count += connection.total_changes - before
                connection.commit()
                batch.clear()

                if progress_callback is not None:
                    progress_callback(processed_count, inserted_count)

        if batch:
            before = connection.total_changes

            connection.executemany(
                """
                INSERT OR IGNORE INTO pages (
                    dump_id,
                    page_id,
                    title,
                    namespace_id,
                    namespace_name,
                    revision_id,
                    text_length,
                    page_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )

            inserted_count += connection.total_changes - before
            connection.commit()

            if progress_callback is not None:
                progress_callback(processed_count, inserted_count)

        return inserted_count

    finally:
        connection.close()


def migrate_database():
    connection = get_connection()

    try:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(source_dumps)")
        }

        if "import_status" not in columns:
            connection.execute(
                """
                ALTER TABLE source_dumps
                ADD COLUMN import_status TEXT NOT NULL
                DEFAULT 'pending'
                CHECK (
                    import_status IN (
                        'pending',
                        'importing',
                        'completed',
                        'failed'
                    )
                )
                """
            )

        if "completed_at" not in columns:
            connection.execute(
                """
                ALTER TABLE source_dumps
                ADD COLUMN completed_at TEXT
                """
            )

        page_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(pages)")
        }

        if "page_text" not in page_columns:
            connection.execute(
                """
                ALTER TABLE pages
                ADD COLUMN page_text TEXT NOT NULL DEFAULT ''
                """
            )

        connection.commit()

    finally:
        connection.close()


def update_import_status(dump_id, status):
    allowed_statuses = {
        "pending",
        "importing",
        "completed",
        "failed",
    }

    if status not in allowed_statuses:
        raise ValueError(f"Invalid import status: {status}")

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            UPDATE source_dumps
            SET
                import_status = ?,
                completed_at = CASE
                    WHEN ? = 'completed' THEN CURRENT_TIMESTAMP
                    ELSE NULL
                END
            WHERE dump_id = ?
            """,
            (status, status, dump_id),
        )

        if cursor.rowcount == 0:
            raise ValueError(f"Dump ID {dump_id} does not exist.")

        connection.commit()

    finally:
        connection.close()



def search_pages(search_term, limit=10):
    """Search page titles and stored wiki text for a simple keyword or phrase."""
    search_term = search_term.strip()

    if not search_term:
        raise ValueError("Search term cannot be empty.")

    if limit < 1:
        raise ValueError("Search limit must be at least 1.")

    connection = get_connection()

    try:
        return connection.execute(
            """
            SELECT
                page_id,
                title,
                namespace_name,
                revision_id,
                text_length,
                page_text
            FROM pages
            WHERE title LIKE ? OR page_text LIKE ?
            ORDER BY
                CASE WHEN title LIKE ? THEN 0 ELSE 1 END,
                text_length DESC
            LIMIT ?
            """,
            (
                f"%{search_term}%",
                f"%{search_term}%",
                f"%{search_term}%",
                limit,
            ),
        ).fetchall()
    finally:
        connection.close()


def get_page_by_title(title):
    """Return the most recently imported page matching an exact title."""
    connection = get_connection()

    try:
        return connection.execute(
            """
            SELECT
                page_id,
                title,
                namespace_name,
                revision_id,
                text_length,
                page_text
            FROM pages
            WHERE title = ?
            ORDER BY dump_id DESC
            LIMIT 1
            """,
            (title,),
        ).fetchone()
    finally:
        connection.close()



def get_pages_for_analysis(namespace_id=0, min_text_length=1):
    """Return stored pages suitable for text analysis."""
    if min_text_length < 0:
        raise ValueError("Minimum text length cannot be negative.")

    connection = get_connection()

    try:
        return connection.execute(
            """
            SELECT
                page_id,
                title,
                namespace_id,
                namespace_name,
                revision_id,
                page_text
            FROM pages
            WHERE namespace_id = ?
              AND LENGTH(TRIM(page_text)) >= ?
            ORDER BY title
            """,
            (namespace_id, min_text_length),
        ).fetchall()
    finally:
        connection.close()
