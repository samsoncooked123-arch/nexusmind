from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from neo4j.exceptions import ServiceUnavailable, SessionExpired

from app import config
from app.answering.service import ask
from app.answering.conflicts import list_conflicts
from app.extraction.facts import create_fact, validate_fact
from app.ingestion.documents import delete_document, document_path, ingest_upload, replace_upload
from app.models.schemas import AskInput, FactInput, SearchInput, TopicInput, TopicMergeInput, TopicSplitInput, TranslateTextInput
from app.retrieval import vector
from app.storage import graph, sqlite as store
from app.topics.service import list_topics, merge_topics, save_topic, split_topic, suggest_topics
from app.translation import ENGINE as TRANSLATION_ENGINE, translate_text


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.migrate()
    try:
        graph.verify()
        graph.initialize()
    except Exception:
        # Health reports graph connectivity; document APIs can still start.
        pass
    yield


app = FastAPI(title="NexusMind — AI-03 Knowledge Base", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[config.FRONTEND_ORIGIN], allow_methods=["*"], allow_headers=["*"])


def missing(message: str = "Not found") -> HTTPException:
    return HTTPException(status_code=404, detail=message)


@app.get("/health")
def health():
    status = {"sqlite": False, "neo4j": False, "chroma": False,
              "graph_available": False, "graph_backend": config.GRAPH_BACKEND,
              "llm_configured": config.llm_configured(),
              "llm_model": config.LLM_MODEL if config.llm_configured() else None}
    try:
        store.one("SELECT 1 AS ok")
        status["sqlite"] = True
    except Exception:
        pass
    try:
        graph.verify()
        status["graph_available"] = True
        status["neo4j"] = config.GRAPH_BACKEND == "neo4j"
    except Exception:
        pass
    try:
        vector.collection().count()
        status["chroma"] = True
    except Exception:
        pass
    return {"status": "ok" if all(status[k] for k in ("sqlite", "graph_available", "chroma")) else "degraded", **status}


@app.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    try:
        document, duplicate = ingest_upload(file.filename or "upload", data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"document": document, "duplicate": duplicate}


@app.get("/documents")
def documents():
    return store.rows("SELECT * FROM documents ORDER BY created_at DESC")


@app.get("/documents/{document_id}")
def document(document_id: str):
    result = store.one("SELECT * FROM documents WHERE id=?", (document_id,))
    if not result:
        raise missing("Document not found")
    return result


@app.put("/documents/{document_id}")
async def replace_document(document_id: str, file: UploadFile = File(...)):
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    try:
        updated, duplicate = replace_upload(document_id, file.filename or "replacement", data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"document": updated, "duplicate": duplicate}


@app.delete("/documents/{document_id}")
def remove_document(document_id: str):
    try:
        delete_document(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Document removal unavailable: {exc}") from exc
    return {"deleted": document_id}


@app.post("/documents/{document_id}/retry")
def retry_document(document_id: str):
    doc = document(document_id)
    if doc["status"] != "failed":
        raise HTTPException(status_code=409, detail="Only failed documents can be retried")
    with store.transaction() as db:
        db.execute("UPDATE documents SET status='queued',error=NULL,updated_at=? WHERE id=?", (store.now(), document_id))
        db.execute("INSERT INTO jobs(document_id,status,created_at,updated_at) VALUES(?,?,?,?)",
                   (document_id, "queued", store.now(), store.now()))
    return document(document_id)


@app.get("/documents/{document_id}/versions")
def document_versions(document_id: str):
    document(document_id)
    return store.rows("SELECT * FROM document_versions WHERE document_id=? ORDER BY version DESC", (document_id,))


@app.get("/documents/{document_id}/file")
def document_file(document_id: str):
    doc = document(document_id)
    path = document_path(doc)
    if not path.is_file():
        raise missing("Original file not found")
    return FileResponse(path, filename=doc["filename"], content_disposition_type="inline",
                        media_type="application/pdf" if doc["extension"] == ".pdf" else "text/plain")


@app.get("/documents/{document_id}/pages/{page}")
def document_page(document_id: str, page: int):
    result = store.one("""SELECT p.* FROM pages p JOIN documents d ON d.id=p.document_id
        WHERE p.document_id=? AND p.page=? AND d.status='ready'""", (document_id, page))
    if not result:
        raise missing("Page not found")
    return result


@app.get("/documents/{document_id}/chunks")
def document_chunks(document_id: str):
    document(document_id)
    return store.rows("""SELECT c.* FROM chunks c JOIN documents d ON d.id=c.document_id
        WHERE c.document_id=? AND c.version=d.version AND d.status='ready' ORDER BY c.page,c.ordinal""", (document_id,))


@app.get("/chunks/{chunk_id}")
def chunk(chunk_id: str):
    result = store.one("""SELECT c.*,d.filename FROM chunks c JOIN documents d ON d.id=c.document_id
        WHERE c.id=? AND c.version=d.version AND d.status='ready'""", (chunk_id,))
    if not result:
        raise missing("Passage not found")
    return result


@app.get("/chunks/{chunk_id}/translation")
def chunk_translation(chunk_id: str):
    source = chunk(chunk_id)
    cached = store.one("SELECT translated_text,engine FROM translations WHERE chunk_id=? AND target_language='hi'", (chunk_id,))
    if cached:
        return {"chunk_id": chunk_id, "source_text": source["text"], "translated_text": cached["translated_text"],
                "source_language": "en", "target_language": "hi", "engine": cached["engine"], "cached": True}
    try:
        translated = translate_text(source["text"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Local Hindi translation unavailable: {exc}") from exc
    # A replacement can retire a passage while the model is translating it.
    chunk(chunk_id)
    with store.transaction() as db:
        db.execute("""INSERT OR IGNORE INTO translations(chunk_id,target_language,translated_text,engine,created_at)
            VALUES(?,'hi',?,?,?)""", (chunk_id, translated, TRANSLATION_ENGINE, store.now()))
    return {"chunk_id": chunk_id, "source_text": source["text"], "translated_text": translated,
            "source_language": "en", "target_language": "hi", "engine": TRANSLATION_ENGINE, "cached": False}


@app.post("/translate/text")
def translate_plain_text(input: TranslateTextInput):
    try:
        translated = translate_text(input.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Local Hindi translation unavailable: {exc}") from exc
    return {"source_text": input.text, "translated_text": translated,
            "source_language": "en", "target_language": "hi", "engine": TRANSLATION_ENGINE}


@app.post("/search")
def search(input: SearchInput):
    try:
        return {"results": vector.search(input.query, input.limit)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Search unavailable: {exc}") from exc


@app.get("/facts/pending")
def pending_facts():
    return store.rows("""SELECT f.*,c.text AS evidence_text,c.page,d.filename FROM facts f
        JOIN chunks c ON c.id=f.evidence_chunk_id JOIN documents d ON d.id=f.document_id
        WHERE f.status='pending' AND c.version=d.version AND d.status='ready'
        ORDER BY f.created_at DESC""")


@app.get("/conflicts")
def conflicts():
    return list_conflicts()


@app.post("/facts")
def add_fact(input: FactInput):
    try:
        return create_fact(input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/facts/{fact_id}")
def edit_fact(fact_id: str, input: FactInput):
    previous = store.one("SELECT * FROM facts WHERE id=?", (fact_id,))
    if not previous:
        raise missing("Fact not found")
    if previous["status"] != "pending":
        raise HTTPException(status_code=409, detail="Only pending facts can be edited")
    try:
        item = validate_fact(input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with store.transaction() as db:
        db.execute("""UPDATE facts SET document_id=?,subject_id=?,subject_name=?,subject_type=?,relation=?,
            object_id=?,object_name=?,object_type=?,evidence_chunk_id=?,evidence_quote=?,polarity=?,updated_at=? WHERE id=?""",
            (item["document_id"], item["subject_id"], input.subject.name, input.subject.type, input.relation,
             item["object_id"], input.object.name, input.object.type, input.evidence_chunk_id,
             input.evidence_quote, input.polarity, store.now(), fact_id))
    return store.one("SELECT * FROM facts WHERE id=?", (fact_id,))


@app.post("/facts/{fact_id}/approve")
def approve_fact(fact_id: str):
    preliminary = store.one("SELECT status FROM facts WHERE id=?", (fact_id,))
    if not preliminary:
        raise missing("Fact not found")
    if preliminary["status"] != "pending":
        raise HTTPException(status_code=409, detail="Fact is not pending")
    try:
        graph.initialize()
        with store.transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM facts WHERE id=?", (fact_id,)).fetchone()
            if not row:
                raise missing("Fact not found")
            if row["status"] != "pending":
                raise HTTPException(status_code=409, detail="Fact is not pending")
            current = db.execute("""SELECT c.id FROM chunks c JOIN documents d ON d.id=c.document_id
                WHERE c.id=? AND c.version=d.version AND d.status='ready'""", (row["evidence_chunk_id"],)).fetchone()
            if not current:
                raise HTTPException(status_code=409, detail="Fact evidence is no longer current")
            graph.approve_fact(dict(row))
            db.execute("UPDATE facts SET status='approved',updated_at=? WHERE id=?", (store.now(), fact_id))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph unavailable: {exc}") from exc
    return store.one("SELECT * FROM facts WHERE id=?", (fact_id,))


@app.post("/facts/{fact_id}/reject")
def reject_fact(fact_id: str):
    fact = store.one("SELECT * FROM facts WHERE id=?", (fact_id,))
    if not fact:
        raise missing("Fact not found")
    if fact["status"] != "pending":
        raise HTTPException(status_code=409, detail="Fact is not pending")
    with store.transaction() as db:
        db.execute("UPDATE facts SET status='rejected',updated_at=? WHERE id=?", (store.now(), fact_id))
    return store.one("SELECT * FROM facts WHERE id=?", (fact_id,))


@app.get("/topics")
def topics():
    return list_topics()


@app.post("/topics")
def add_topic(input: TopicInput):
    try:
        return save_topic(None, input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/topics/{topic_id}")
def edit_topic(topic_id: str, input: TopicInput):
    if not store.one("SELECT id FROM topics WHERE id=?", (topic_id,)):
        raise missing("Topic not found")
    try:
        return save_topic(topic_id, input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/topics/discover")
def discover_topics():
    try:
        return suggest_topics()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Topic discovery unavailable: {exc}") from exc


@app.post("/topics/{topic_id}/merge")
def merge_topic(topic_id: str, input: TopicMergeInput):
    try:
        return merge_topics(topic_id, input.secondary_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/topics/{topic_id}/split")
def split_topic_route(topic_id: str, input: TopicSplitInput):
    try:
        return split_topic(topic_id, input.label, input.document_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/graph/entities")
def graph_entities(query: str = "", limit: int = Query(default=100, ge=1, le=500)):
    try:
        return graph.entities(query, limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph unavailable: {exc}") from exc


@app.get("/graph/stats")
def graph_stats():
    try:
        return graph.statistics()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph unavailable: {exc}") from exc


def _current_graph_edges(result: dict) -> dict:
    # A graph projection can outlive a replaced source in Neo4j. Never show
    # an edge unless its exact passage still belongs to the ready version.
    current_edges = []
    for edge in result["edges"]:
        evidence = store.one("""SELECT c.id AS chunk_id,c.document_id,c.page,c.text,d.filename
            FROM chunks c JOIN documents d ON d.id=c.document_id
            WHERE c.id=? AND c.version=d.version AND d.status='ready'""",
            (edge["evidence_chunk_id"],))
        if evidence:
            edge["evidence"] = evidence
            current_edges.append(edge)
    result["edges"] = current_edges
    active = {item for edge in result["edges"] for item in (edge["source"], edge["target"])}
    result["nodes"] = [node for node in result["nodes"] if node["id"] in active]
    return result


@app.get("/graph/overview")
def graph_overview(limit: int = Query(default=24, ge=1, le=80)):
    document_ids = [row["id"] for row in store.rows("SELECT id FROM documents WHERE status='ready'")]
    if not document_ids:
        return {"nodes": [], "edges": []}
    try:
        return _current_graph_edges(graph.relations_for_documents(document_ids, limit=limit))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph unavailable: {exc}") from exc


@app.get("/graph/topic/{topic_id}")
def graph_topic(topic_id: str):
    topic = next((item for item in list_topics() if item["id"] == topic_id), None)
    if not topic:
        raise missing("Topic not found")
    try:
        result = graph.relations_for_documents([item["id"] for item in topic["documents"]], limit=80)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph unavailable: {exc}") from exc
    return _current_graph_edges(result)


@app.get("/graph/neighborhood/{entity_id}")
def graph_neighborhood(entity_id: str):
    try:
        result = graph.neighborhood(entity_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph unavailable: {exc}") from exc
    for edge in result["edges"]:
        edge["evidence"] = store.one("""SELECT c.id AS chunk_id,c.document_id,c.page,c.text,d.filename
            FROM chunks c JOIN documents d ON d.id=c.document_id
            WHERE c.id=? AND c.version=d.version AND d.status='ready'""", (edge["evidence_chunk_id"],))
    result["edges"] = [edge for edge in result["edges"] if edge["evidence"]]
    active = {entity_id} | {item for edge in result["edges"] for item in (edge["source"], edge["target"])}
    result["nodes"] = [node for node in result["nodes"] if node["id"] in active]
    return result


@app.post("/ask")
def answer(input: AskInput):
    try:
        return ask(input.question)
    except (ServiceUnavailable, SessionExpired):
        # Preserve cited passage search while clearly withholding graph claims.
        return ask(input.question, vector_only=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Answer service unavailable: {exc}") from exc
