import hashlib
import re
import sqlite3
import uuid
from pathlib import Path

from app import config
from app.storage import sqlite as store


def _checked_upload(filename: str, data: bytes) -> tuple[str, str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".txt"}:
        raise ValueError("Only PDF and TXT files are supported")
    if not data or len(data) > config.MAX_UPLOAD_BYTES:
        raise ValueError("File is empty or exceeds the upload limit")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("This is not a valid PDF file")
    digest = hashlib.sha256(data).hexdigest()
    safe_name = re.sub(r"[^a-zA-Z0-9._ -]", "_", Path(filename).name)[:160]
    return suffix, digest, safe_name


def document_path(doc: dict) -> Path:
    version = doc.get("version", 1)
    suffix = f"-v{version}" if version > 1 else ""
    return config.UPLOAD_DIR / f"{doc['id']}{suffix}{doc['extension']}"


def ingest_upload(filename: str, data: bytes) -> tuple[dict, bool]:
    suffix, digest, safe_name = _checked_upload(filename, data)
    existing = store.one("SELECT * FROM documents WHERE sha256=?", (digest,))
    if existing:
        return existing, True
    doc_id = "doc-" + digest[:20]
    if store.one("SELECT id FROM documents WHERE id=?", (doc_id,)):
        doc_id = "doc-" + uuid.uuid4().hex[:20]
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = config.UPLOAD_DIR / f"{doc_id}{suffix}"
    target.write_bytes(data)
    try:
        with store.transaction() as db:
            db.execute("INSERT INTO documents(id,sha256,filename,extension,byte_size,status,created_at) VALUES(?,?,?,?,?,?,?)",
                       (doc_id, digest, safe_name, suffix, len(data), "queued", store.now()))
            db.execute("""INSERT INTO document_versions(document_id,version,sha256,filename,extension,byte_size,status,created_at)
                VALUES(?,?,?,?,?,?,?,?)""", (doc_id, 1, digest, safe_name, suffix, len(data), "queued", store.now()))
            db.execute("INSERT INTO jobs(document_id,status,created_at,updated_at) VALUES(?,?,?,?)",
                       (doc_id, "queued", store.now(), store.now()))
    except sqlite3.IntegrityError:
        # Another upload of the same bytes won the race.
        return store.one("SELECT * FROM documents WHERE sha256=?", (digest,)), True
    return store.one("SELECT * FROM documents WHERE id=?", (doc_id,)), False


def replace_upload(document_id: str, filename: str, data: bytes) -> tuple[dict, bool]:
    current = store.one("SELECT * FROM documents WHERE id=?", (document_id,))
    if not current:
        raise ValueError("Document not found")
    suffix, digest, safe_name = _checked_upload(filename, data)
    if digest == current["sha256"]:
        return current, True
    if store.one("SELECT id FROM documents WHERE sha256=?", (digest,)):
        raise ValueError("This file is already stored as another document")
    if store.one("SELECT id FROM jobs WHERE document_id=? AND status IN ('queued','processing')", (document_id,)):
        raise ValueError("Wait for the current document job to finish")
    version = current["version"] + 1
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = config.UPLOAD_DIR / f"{document_id}-v{version}{suffix}"
    path.write_bytes(data)
    try:
        with store.transaction() as db:
            db.execute("""UPDATE documents SET sha256=?,filename=?,extension=?,byte_size=?,version=?,status='queued',
                error=NULL,page_count=0,updated_at=? WHERE id=?""",
                (digest, safe_name, suffix, len(data), version, store.now(), document_id))
            db.execute("UPDATE document_versions SET status='retired',retired_at=? WHERE document_id=? AND version=?",
                       (store.now(), document_id, current["version"]))
            db.execute("""INSERT INTO document_versions(document_id,version,sha256,filename,extension,byte_size,status,created_at)
                VALUES(?,?,?,?,?,?,?,?)""", (document_id, version, digest, safe_name, suffix, len(data), "queued", store.now()))
            db.execute("INSERT INTO jobs(document_id,status,created_at,updated_at) VALUES(?,?,?,?)",
                       (document_id, "queued", store.now(), store.now()))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return store.one("SELECT * FROM documents WHERE id=?", (document_id,)), False


def delete_document(document_id: str) -> None:
    doc = store.one("SELECT * FROM documents WHERE id=?", (document_id,))
    if not doc:
        raise ValueError("Document not found")
    if store.one("SELECT id FROM jobs WHERE document_id=? AND status='processing'", (document_id,)):
        raise ValueError("Wait for document processing to finish")
    from app.retrieval import vector
    from app.storage import graph
    graph_reference = (store.one("SELECT id FROM facts WHERE document_id=? AND status='approved' LIMIT 1", (document_id,)) or
                       store.one("""SELECT t.id FROM topic_members m JOIN topics t ON t.id=m.topic_id
                           WHERE m.document_id=? AND t.status='approved' LIMIT 1""", (document_id,)))
    if graph_reference:
        graph.remove_document(document_id)
    vector.delete_document(document_id)
    with store.transaction() as db:
        db.execute("DELETE FROM documents WHERE id=?", (document_id,))
    for path in config.UPLOAD_DIR.glob(f"{document_id}*"):
        if path.is_file():
            path.unlink()


def split_passages(text: str, limit: int = 1200) -> list[str]:
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    paragraphs = [p for p in paragraphs if p]
    result: list[str] = []
    current = ""
    for paragraph in paragraphs:
        parts = re.split(r"(?<=[.!?])\s+", paragraph) if len(paragraph) > limit else [paragraph]
        for part in parts:
            if len(part) > limit:
                parts2 = [part[i:i + limit] for i in range(0, len(part), limit)]
            else:
                parts2 = [part]
            for item in parts2:
                if current and len(current) + len(item) + 1 > limit:
                    result.append(current)
                    current = ""
                current = f"{current} {item}".strip()
    if current:
        result.append(current)
    return result


def extract_pages(path: Path) -> list[tuple[int, str, str]]:
    if path.suffix == ".txt":
        return [(1, path.read_text(encoding="utf-8-sig", errors="replace"), "not_needed")]
    import pymupdf
    result = []
    with pymupdf.open(path) as pdf:
        for number, page in enumerate(pdf, start=1):
            text = page.get_text(sort=True).strip()
            ocr_status = "not_needed"
            if len(text) < 40:
                try:
                    text_page = page.get_textpage_ocr(language="eng", dpi=200, full=True)
                    text = page.get_text(textpage=text_page).strip()
                    ocr_status = "done" if text else "empty"
                except Exception as exc:
                    ocr_status = "failed: " + str(exc)[:150]
            result.append((number, text, ocr_status))
    return result


def process_document(document_id: str) -> list[dict]:
    doc = store.one("SELECT * FROM documents WHERE id=?", (document_id,))
    if not doc:
        raise ValueError("Document not found")
    path = document_path(doc)
    pages = extract_pages(path)
    chunks: list[dict] = []
    with store.transaction() as db:
        db.execute("DELETE FROM pages WHERE document_id=?", (document_id,))
        db.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
        for number, text, ocr_status in pages:
            db.execute("INSERT INTO pages(document_id,page,text,ocr_status) VALUES(?,?,?,?)",
                       (document_id, number, text, ocr_status))
            for ordinal, passage in enumerate(split_passages(text), start=1):
                chunk_id = f"{document_id}-v{doc['version']}-p{number:04d}-c{ordinal:03d}"
                text_hash = hashlib.sha256(passage.encode()).hexdigest()
                section = passage[:100] if len(passage) < 100 and not passage.endswith(".") else None
                db.execute("INSERT INTO chunks(id,document_id,page,ordinal,section,text,text_hash,version) VALUES(?,?,?,?,?,?,?,?)",
                           (chunk_id, document_id, number, ordinal, section, passage, text_hash, doc["version"]))
                chunks.append({"id": chunk_id, "document_id": document_id, "page": number,
                               "filename": doc["filename"], "text": passage, "version": doc["version"]})
        db.execute("UPDATE documents SET page_count=?, status='extracted' WHERE id=?", (len(pages), document_id))
    return chunks
