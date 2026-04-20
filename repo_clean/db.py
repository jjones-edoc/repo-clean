import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def init_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            description TEXT NOT NULL,
            file_path TEXT,
            rule TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


@contextmanager
def _connect(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn.cursor()
        conn.commit()
    finally:
        conn.close()


def insert_todo(db_path: Path, description: str, file_path: str, rule: str, sort_order: int = 0) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as c:
        c.execute(
            "SELECT 1 FROM todos WHERE file_path = ? AND rule = ? AND status != 'complete' AND status != 'skipped'",
            (file_path, rule),
        )
        if c.fetchone() is None:
            c.execute(
                "INSERT INTO todos (sort_order, description, file_path, rule, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (sort_order, description, file_path, rule, now, now),
            )


def get_meta(db_path: Path, key: str) -> str | None:
    with _connect(db_path) as c:
        c.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = c.fetchone()
    return row[0] if row else None


def set_meta(db_path: Path, key: str, value: str) -> None:
    with _connect(db_path) as c:
        c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def count_by_status(db_path: Path, status: str) -> int:
    with _connect(db_path) as c:
        c.execute("SELECT COUNT(*) FROM todos WHERE status = ?", (status,))
        return c.fetchone()[0]


def count_all_todos(db_path: Path) -> int:
    with _connect(db_path) as c:
        c.execute("SELECT COUNT(*) FROM todos")
        return c.fetchone()[0]


def finalize_clean(db_path: Path) -> None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True
    )
    commit_hash = result.stdout.strip() if result.returncode == 0 else "unknown"
    now = datetime.now(timezone.utc).isoformat()

    with _connect(db_path) as c:
        c.execute("DELETE FROM todos")
        c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_clean_date', ?)", (now,))
        c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_clean_commit', ?)", (commit_hash,))

    # VACUUM cannot run inside a transaction, so it needs a separate connection.
    vacuum_conn = sqlite3.connect(db_path)
    vacuum_conn.execute("VACUUM")
    vacuum_conn.close()

    print(f"\n✓ Repository marked clean at commit {commit_hash[:8]} ({now})")


def print_status(db_path: Path) -> None:
    if not db_path.exists():
        print("No repo_clean.db found. Run 'repo-clean' to initialize.")
        return

    with _connect(db_path) as c:
        c.execute("SELECT key, value FROM meta")
        meta = {row["key"]: row["value"] for row in c.fetchall()}
        print("\n=== Repo Clean Status ===")
        print(f"Last clean : {meta.get('last_clean_date', 'never')}")
        print(f"Last commit: {meta.get('last_clean_commit', 'n/a')}")

        c.execute("SELECT status, COUNT(*) as cnt FROM todos GROUP BY status")
        counts = {row["status"]: row["cnt"] for row in c.fetchall()}

        if not counts:
            print("\nNo todo items.")
            return

        print("\nTodo counts:")
        for status in ("pending", "in_progress", "complete", "failed", "skipped"):
            n = counts.get(status, 0)
            if n:
                print(f"  {status}: {n}")

        c.execute("""
            SELECT id, status, rule, file_path, description, notes
            FROM todos
            WHERE status NOT IN ('complete', 'skipped')
            ORDER BY sort_order
        """)
        rows = c.fetchall()
        if rows:
            print("\nOpen items:")
            for row in rows:
                label = f"[{row['id']}] {row['status'].upper()} | {row['rule'] or ''}"
                if row["file_path"]:
                    label += f" | {row['file_path']}"
                print(f"\n  {label}")
                print(f"       {row['description']}")
                if row["notes"]:
                    print(f"       Notes: {row['notes']}")
