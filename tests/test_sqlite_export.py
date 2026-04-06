import json
from pathlib import Path

import pytest


def test_export_all_data_writes_json_csv_and_manifest(tmp_path, monkeypatch):
    import database.sqlite_export as ex
    import database.connection as conn_mod

    db_path = tmp_path / "src.db"
    conn = __import__("sqlite3").connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL DEFAULT 'default',
            username TEXT NOT NULL
        );
        INSERT INTO users (tenant_id, username) VALUES ('default', 'admin');
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL
        );
        INSERT INTO customers (tenant_id, name) VALUES ('default', 'Alice');
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(conn_mod, "DB_PATH", db_path)
    monkeypatch.setattr(ex, "get_db_provider", lambda: "sqlite")

    def _conn():
        c = __import__("sqlite3").connect(str(db_path))
        c.row_factory = __import__("sqlite3").Row
        return c

    # ``sqlite_export`` importa ``get_db_conn`` por nome; patch no módulo de export.
    monkeypatch.setattr(ex, "get_db_conn", lambda: _conn())

    out_root = tmp_path / "export"
    run_dir = ex.export_all_data(out_root, subdir_with_timestamp=False)

    assert run_dir == out_root
    assert (out_root / "manifest.json").is_file()
    assert (out_root / "users.json").is_file()
    assert (out_root / "users.csv").is_file()

    manifest = json.loads((out_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["engine"] == "sqlite"
    assert any(t["table"] == "users" for t in manifest["tables"])

    users_payload = json.loads((out_root / "users.json").read_text(encoding="utf-8"))
    assert users_payload["table"] == "users"
    assert "tenant_id" in users_payload["columns"]
    assert len(users_payload["rows"]) == 1
    assert users_payload["rows"][0]["username"] == "admin"


def test_export_all_data_requires_sqlite_provider(monkeypatch):
    import database.sqlite_export as ex

    monkeypatch.setattr(ex, "get_db_provider", lambda: "postgres")
    with pytest.raises(RuntimeError, match="sqlite"):
        ex.export_all_data()
