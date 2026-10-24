import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app import config


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.DATABASE_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=30000")
    return db


@contextmanager
def transaction():
    db = connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def migrate() -> None:
    with transaction() as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            db.executescript("""
            CREATE TABLE documents (
              id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE,
              filename TEXT NOT NULL, extension TEXT NOT NULL, byte_size INTEGER NOT NULL,
              status TEXT NOT NULL, error TEXT, page_count INTEGER DEFAULT 0,
              created_at TEXT NOT NULL
            );
            CREATE TABLE pages (
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              page INTEGER NOT NULL, text TEXT NOT NULL, ocr_status TEXT NOT NULL,
              PRIMARY KEY(document_id,page)
            );
            CREATE TABLE chunks (
              id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              page INTEGER NOT NULL, ordinal INTEGER NOT NULL, section TEXT,
              text TEXT NOT NULL, text_hash TEXT NOT NULL,
              UNIQUE(document_id,page,ordinal)
            );
            CREATE INDEX chunks_by_document ON chunks(document_id,page);
            CREATE TABLE jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE facts (
              id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              subject_id TEXT NOT NULL, subject_name TEXT NOT NULL, subject_type TEXT NOT NULL,
              relation TEXT NOT NULL,
              object_id TEXT NOT NULL, object_name TEXT NOT NULL, object_type TEXT NOT NULL,
              evidence_chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
              evidence_quote TEXT NOT NULL, status TEXT NOT NULL,
              origin TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX facts_by_status ON facts(status);
            CREATE INDEX facts_by_chunk ON facts(evidence_chunk_id);
            CREATE TABLE topics (
              id TEXT PRIMARY KEY, label TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE topic_members (
              topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              PRIMARY KEY(topic_id, document_id)
            );
            PRAGMA user_version=1;
            """)
        if version < 2:
            db.executescript("""
            ALTER TABLE documents ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE documents ADD COLUMN updated_at TEXT;
            ALTER TABLE chunks ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE facts ADD COLUMN polarity TEXT NOT NULL DEFAULT 'supports';
            CREATE TABLE document_versions (
              document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              version INTEGER NOT NULL, sha256 TEXT NOT NULL, filename TEXT NOT NULL,
              extension TEXT NOT NULL, byte_size INTEGER NOT NULL,
              status TEXT NOT NULL, created_at TEXT NOT NULL, retired_at TEXT,
              PRIMARY KEY(document_id,version)
            );
            INSERT INTO document_versions(document_id,version,sha256,filename,extension,byte_size,status,created_at)
              SELECT id,1,sha256,filename,extension,byte_size,status,created_at FROM documents;
            UPDATE documents SET updated_at=created_at WHERE updated_at IS NULL;
            CREATE INDEX chunks_by_version ON chunks(document_id,version);
            PRAGMA user_version=2;
            """)
        if version < 3:
            db.executescript("""
            CREATE TABLE translations (
              chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
              target_language TEXT NOT NULL,
              translated_text TEXT NOT NULL,
              engine TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY(chunk_id,target_language)
            );
            PRAGMA user_version=3;
            """)


def rows(query: str, params: tuple = ()) -> list[dict]:
    with connect() as db:
        return [dict(row) for row in db.execute(query, params).fetchall()]


def one(query: str, params: tuple = ()) -> dict | None:
    with connect() as db:
        row = db.execute(query, params).fetchone()
        return dict(row) if row else None


def claim_job() -> dict | None:
    with transaction() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
        if not row:
            return None
        db.execute("UPDATE jobs SET status='processing', updated_at=? WHERE id=?", (now(), row["id"]))
        db.execute("UPDATE documents SET status='processing', error=NULL WHERE id=?", (row["document_id"],))
        return dict(row)
