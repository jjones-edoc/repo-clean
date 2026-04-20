import sqlite3

from repo_clean.db import (
    count_all_todos,
    count_by_status,
    finalize_clean,
    get_meta,
    init_db,
    insert_todo,
    print_status,
    set_meta,
)


def test_init_db_creates_tables(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    conn = sqlite3.connect(db)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"meta", "todos"}.issubset(names)


def test_init_db_is_idempotent(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    set_meta(db, "k", "v")
    init_db(db)
    assert get_meta(db, "k") == "v"


def test_insert_todo_basic(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    insert_todo(db, "do thing", "a.py", "comments", sort_order=1)
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT description, file_path, rule, status, sort_order FROM todos").fetchall()
    conn.close()
    assert rows == [("do thing", "a.py", "comments", "pending", 1)]


def test_insert_todo_dedupes_pending(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    insert_todo(db, "first", "a.py", "comments")
    insert_todo(db, "second", "a.py", "comments")
    assert count_all_todos(db) == 1


def test_insert_todo_allows_after_complete(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    insert_todo(db, "first", "a.py", "comments")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE todos SET status='complete' WHERE file_path='a.py'")
    conn.commit()
    conn.close()
    insert_todo(db, "second", "a.py", "comments")
    assert count_all_todos(db) == 2


def test_insert_todo_allows_different_rule_same_file(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    insert_todo(db, "a", "x.py", "comments")
    insert_todo(db, "b", "x.py", "dry")
    assert count_all_todos(db) == 2


def test_meta_get_set(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    assert get_meta(db, "missing") is None
    set_meta(db, "foo", "bar")
    assert get_meta(db, "foo") == "bar"
    set_meta(db, "foo", "baz")
    assert get_meta(db, "foo") == "baz"


def test_count_by_status(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    insert_todo(db, "a", "a.py", "comments")
    insert_todo(db, "b", "b.py", "comments")
    assert count_by_status(db, "pending") == 2
    assert count_by_status(db, "complete") == 0
    conn = sqlite3.connect(db)
    conn.execute("UPDATE todos SET status='complete' WHERE file_path='a.py'")
    conn.commit()
    conn.close()
    assert count_by_status(db, "pending") == 1
    assert count_by_status(db, "complete") == 1


def test_finalize_clean(tmp_path, monkeypatch, git_repo):
    db = git_repo / "test.db"
    init_db(db)
    insert_todo(db, "a", "a.py", "comments")
    set_meta(db, "other_key", "kept_raw")
    monkeypatch.chdir(git_repo)
    finalize_clean(db)
    assert count_all_todos(db) == 0
    assert get_meta(db, "last_clean_date") is not None
    commit = get_meta(db, "last_clean_commit")
    assert commit and len(commit) == 40


def test_print_status_missing_db(tmp_path, capsys):
    print_status(tmp_path / "nope.db")
    assert "No repo_clean.db found" in capsys.readouterr().out


def test_print_status_with_items(tmp_path, capsys):
    db = tmp_path / "test.db"
    init_db(db)
    insert_todo(db, "describe me", "a.py", "comments")
    set_meta(db, "last_clean_date", "2026-01-01T00:00:00+00:00")
    set_meta(db, "last_clean_commit", "abcdef1234")
    print_status(db)
    out = capsys.readouterr().out
    assert "pending: 1" in out
    assert "describe me" in out
    assert "a.py" in out
    assert "2026-01-01" in out
