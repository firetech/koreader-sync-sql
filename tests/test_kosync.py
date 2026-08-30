# -*- coding: utf-8 -*-
# pyright: strict
import importlib
import os
import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_app(db_path: Path):
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    import kosync

    return importlib.reload(kosync).app

@pytest.fixture
def db_path(tmp_path: Path):
    return tmp_path / "kosync.sqlite"

@pytest.fixture
def client(db_path: Path):
    app = load_app(db_path)
    with TestClient(app) as client:
        yield client


def test_import_does_not_create_db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "nested" / "kosync.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    sys.modules.pop("kosync", None)

    import kosync

    assert not db_path.exists()
    importlib.reload(kosync)
    assert not db_path.exists()


def test_api(db_path: Path, client: TestClient):
    response = client.post("/users/create", json={"username": "alice", "password": "secret"})
    assert response.status_code == 201
    assert response.json() == {"username": "alice"}

    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('users', 'documents')"
            ).fetchall()
        }
        assert {"users", "documents"}.issubset(tables)
        user_row = conn.execute(
            "SELECT username, password FROM users WHERE username = ?",
            ("alice",),
        ).fetchone()
        assert user_row[0] == "alice"
        assert user_row[1] != "secret" # The password should be hashed.

    response = client.get(
        "/users/auth",
        headers={"x-auth-user": "alice", "x-auth-key": "secret"},
    )
    assert response.status_code == 200
    assert response.json() == {"authorized": "OK"}

    response = client.put(
        "/syncs/progress",
        headers={"x-auth-user": "alice", "x-auth-key": "secret"},
        json={
            "document": "book-1",
            "progress": "1234",
            "percentage": 25.5,
            "device": "kindle",
            "device_id": "device-123",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"document": "book-1", "timestamp": response.json()["timestamp"]}

    with sqlite3.connect(db_path) as conn:
        doc_row = conn.execute(
            "SELECT username, document, progress, percentage, device, device_id FROM documents WHERE username = ? AND document = ?",
            ("alice", "book-1"),
        ).fetchone()
        assert doc_row is not None
        assert doc_row[0] == "alice"
        assert doc_row[1] == "book-1"
        assert doc_row[2] == "1234"
        assert doc_row[3] == 25.5
        assert doc_row[4] == "kindle"
        assert doc_row[5] == "device-123"
