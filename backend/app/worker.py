import logging
import time

from app import config
from app.extraction.facts import suggest_from_chunk
from app.ingestion.documents import process_document
from app.retrieval.vector import delete_document, index_chunks
from app.storage import graph, sqlite as store


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai03.worker")


def run_once() -> bool:
    store.migrate()
    job = store.claim_job()
    if not job:
        return False
    doc_id = job["document_id"]
    try:
        # Remove projections of the previous version before replacing its source
        # chunks. Shared entity nodes remain if other facts still use them.
        graph_reference = (store.one("SELECT id FROM facts WHERE document_id=? AND status='approved' LIMIT 1", (doc_id,)) or
                           store.one("""SELECT t.id FROM topic_members m JOIN topics t ON t.id=m.topic_id
                               WHERE m.document_id=? AND t.status='approved' LIMIT 1""", (doc_id,)))
        if graph_reference:
            graph.remove_document(doc_id)
        # An earlier failed run may have written vectors without committing chunks.
        delete_document(doc_id)
        with store.transaction() as db:
            db.execute("DELETE FROM topic_members WHERE document_id=?", (doc_id,))
        chunks = process_document(doc_id)
        if not chunks:
            raise ValueError("No extractable text was found. Check OCR availability and the source file.")
        index_chunks(chunks)
        with store.transaction() as db:
            db.execute("UPDATE documents SET status='ready',updated_at=? WHERE id=?", (store.now(), doc_id))
            db.execute("UPDATE document_versions SET status='ready' WHERE document_id=? AND version=(SELECT version FROM documents WHERE id=?)",
                       (doc_id, doc_id))
        failed_ocr = store.rows("SELECT page,ocr_status FROM pages WHERE document_id=? AND ocr_status LIKE 'failed:%'", (doc_id,))
        warnings = [f"OCR failed on page {item['page']}: {item['ocr_status']}" for item in failed_ocr]
        if config.llm_configured():
            for chunk in chunks:
                try:
                    suggest_from_chunk(chunk)
                except Exception as exc:
                    warnings.append("Some AI fact suggestions failed: " + str(exc)[:250])
                    logger.warning("Fact extraction failed for %s: %s", chunk["id"], exc)
        else:
            warnings.append("AI fact suggestions unavailable until an LLM is configured")
        warning = "; ".join(dict.fromkeys(warnings))[:500] or None
        with store.transaction() as db:
            db.execute("UPDATE documents SET error=? WHERE id=?", (warning, doc_id))
            db.execute("UPDATE jobs SET status='done',error=?,updated_at=? WHERE id=?",
                       (warning, store.now(), job["id"]))
        logger.info("Processed %s: %s chunks", doc_id, len(chunks))
    except Exception as exc:
        logger.exception("Processing failed for %s", doc_id)
        with store.transaction() as db:
            db.execute("UPDATE documents SET status='failed',error=? WHERE id=?", (str(exc)[:500], doc_id))
            db.execute("UPDATE document_versions SET status='failed' WHERE document_id=? AND version=(SELECT version FROM documents WHERE id=?)",
                       (doc_id, doc_id))
            db.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?",
                       (str(exc)[:500], store.now(), job["id"]))
    return True


if __name__ == "__main__":
    store.migrate()
    with store.transaction() as db:
        db.execute("UPDATE jobs SET status='queued',updated_at=? WHERE status='processing'", (store.now(),))
        db.execute("UPDATE documents SET status='queued' WHERE status='processing'")
    while True:
        if not run_once():
            time.sleep(2)
