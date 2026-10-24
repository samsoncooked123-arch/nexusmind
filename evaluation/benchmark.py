"""Reproducible real-embedding/Chroma ingestion benchmark; requires a running Chroma service."""
import argparse
import json
import logging
import platform
import time
from pathlib import Path

from app import config
from app.ingestion.documents import delete_document, ingest_upload, replace_upload
from app.retrieval import vector
from app.storage import graph, sqlite as store
from app.worker import run_once


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--report", type=Path, default=Path(__file__).with_name("benchmark_results.json"))
    args = parser.parse_args()
    if args.count < 500:
        parser.error("Use at least 500 documents for the required scale benchmark")
    scratch = Path(__file__).resolve().parents[3] / "work" / "ai03-benchmark"
    scratch.mkdir(parents=True, exist_ok=True)
    config.DATABASE_PATH = scratch / "benchmark.db"
    config.UPLOAD_DIR = scratch / "uploads"
    config.CHROMA_COLLECTION = "benchmark_nexusmind_500"
    config.LLM_BASE_URL = ""
    vector.collection.cache_clear()
    logging.getLogger("ai03.worker").setLevel(logging.WARNING)
    store.migrate()
    existing = store.one("SELECT COUNT(*) AS n FROM documents")["n"]
    if existing:
        parser.error(f"Benchmark storage already has {existing} documents; use a clean work/ai03-benchmark directory")

    start = time.monotonic()
    ids = []
    for number in range(args.count):
        text = (f"Research report {number:04d}. Project-{number:04d} uses Method-{number % 31:02d} "
                f"for road analysis and was evaluated on Dataset-{number % 19:02d}. "
                f"This report contains source-specific observation {number:04d} about the method and dataset.")
        doc, _ = ingest_upload(f"report-{number:04d}.txt", text.encode())
        ids.append(doc["id"])
    upload_seconds = time.monotonic() - start
    for number in range(args.count):
        assert run_once(), f"Worker ran out of queued jobs at {number}"
        if (number + 1) % 50 == 0:
            print(f"Processed {number + 1}/{args.count} in {time.monotonic() - start:.1f}s", flush=True)
    ingest_seconds = time.monotonic() - start
    statuses = {row["status"]: row["n"] for row in store.rows("SELECT status,COUNT(*) AS n FROM documents GROUP BY status")}
    chunks = store.one("SELECT COUNT(*) AS n FROM chunks")["n"]
    chroma_chunks = vector.collection().count()
    try:
        graph_stats = graph.statistics()
        graph_error = None
    except Exception as exc:
        graph_stats, graph_error = None, str(exc)

    first = ids[0]
    original = store.one("SELECT id FROM chunks WHERE document_id=?", (first,))["id"]
    change_start = time.monotonic()
    replace_upload(first, "report-0000-revised.txt", b"Project-0000 now uses Method-99 for road analysis.")
    assert run_once()
    update_seconds = time.monotonic() - change_start
    stale_chunk_gone = store.one("SELECT id FROM chunks WHERE id=?", (original,)) is None
    delete_start = time.monotonic()
    delete_document(first)
    delete_seconds = time.monotonic() - delete_start
    report = {
        "documents_requested": args.count, "statuses_after_ingestion": statuses,
        "upload_seconds": round(upload_seconds, 3), "ingestion_seconds": round(ingest_seconds, 3),
        "documents_per_minute": round(args.count * 60 / ingest_seconds, 2),
        "sqlite_chunks": chunks, "chroma_chunks": chroma_chunks,
        "neo4j_graph_size": graph_stats, "neo4j_error": graph_error,
        "single_document_update_seconds": round(update_seconds, 3),
        "single_document_delete_seconds": round(delete_seconds, 3),
        "old_chunk_removed_on_update": stale_chunk_gone,
        "embedding_model": config.EMBEDDING_MODEL, "python": platform.python_version(),
        "platform": platform.platform(),
        "note": "Facts require human approval. This no-LLM benchmark measures document/chunk indexing; Neo4j size is unavailable without a running Neo4j service.",
    }
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
