#!/usr/bin/env python3
"""Convert a TinyDB KOReader sync database into a SQLite/SQLAlchemy database.

Usage:
    python migrate_tinydb_to_sqlite.py [--dry-run] [--tinydb path/to/db.json] [--sql sqlite:///path/to/sqlite.db]
"""

import argparse
import sys
from pathlib import Path

from tinydb import TinyDB

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from kosync import Base, Document, User, hash_password, DATABASE_URL


def migrate(source_path: str, dest_url: str, dry_run: bool = False):
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"TinyDB source file not found: {source}")

    if dest_url.startswith("sqlite:///") and not dest_url.startswith("sqlite:///:memory"):
        db_path = dest_url.replace("sqlite:///", "", 1)
        if db_path and not db_path.startswith("/"):
            db_path = Path.cwd() / db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        dest_url,
        connect_args={"check_same_thread": False} if dest_url.startswith("sqlite") else {},
    )
    Base.metadata.create_all(engine)

    tinydb = TinyDB(source)
    users_table = tinydb.table("users")
    documents_table = tinydb.table("documents")

    user_count = len(users_table)
    document_count = len(documents_table)

    if dry_run:
        tinydb.close()
        print(f"Dry run: would migrate {user_count} users and {document_count} documents to {dest_url}")
        return

    with Session(engine) as session:
        for user in users_table.all():
            session.merge(
                User(
                    username=user["username"],
                    password=hash_password(str(user.get("password", ""))),
                )
            )

        for doc in documents_table.all():
            session.merge(
                Document(
                    username=doc["username"],
                    document=doc["document"],
                    progress=doc["progress"],
                    percentage=float(doc["percentage"]),
                    device=doc["device"],
                    device_id=doc["device_id"],
                    timestamp=int(doc["timestamp"]),
                )
            )

        session.commit()

    tinydb.close()
    print(f"Migrated {user_count} users and {document_count} documents to {dest_url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate a TinyDB KOReader sync database to SQLite.",
    )
    parser.add_argument(
        "--tinydb",
        "-t",
        help="Path to the TinyDB JSON file",
        default="data/db.json",
    )
    parser.add_argument(
        "--sql",
        "-s",
        help="Destination database URL (e.g., sqlite:///path/to/sqlite.db)",
        default=DATABASE_URL,
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be migrated without writing data",
    )
    args = parser.parse_args()

    try:
        migrate(args.tinydb, args.sql, dry_run=args.dry_run)
    except Exception as exc:  # pragma: no cover - CLI bootstrap only
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
