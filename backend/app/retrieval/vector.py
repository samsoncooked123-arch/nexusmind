from functools import lru_cache
import hashlib

import chromadb
from fastembed import TextEmbedding

from app import config


@lru_cache(maxsize=1)
def embedder():
    return TextEmbedding(model_name=config.EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def collection():
    client = chromadb.HttpClient(host=config.CHROMA_HOST, port=config.CHROMA_PORT)
    name = config.CHROMA_COLLECTION or "passages_" + hashlib.sha256(config.EMBEDDING_MODEL.encode()).hexdigest()[:12]
    return client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})


def embeddings(texts: list[str]) -> list[list[float]]:
    return [vector.tolist() for vector in embedder().embed(texts)]


def index_chunks(chunks: list[dict]) -> None:
    if not chunks:
        return
    index = collection()
    for offset in range(0, len(chunks), 32):
        batch = chunks[offset:offset + 32]
        index.upsert(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            embeddings=embeddings([c["text"] for c in batch]),
            metadatas=[{"document_id": c["document_id"], "filename": c["filename"],
                        "page": c["page"], "version": c["version"]} for c in batch],
        )


def delete_document(document_id: str) -> None:
    index = collection()
    while True:
        found = index.get(where={"document_id": document_id}, limit=1000, include=[])
        ids = found["ids"]
        if not ids:
            return
        index.delete(ids=ids)


def search(query: str, limit: int = 5) -> list[dict]:
    if not query.strip():
        return []
    index = collection()
    if index.count() == 0:
        return []
    result = index.query(query_embeddings=embeddings([query]), n_results=min(max(limit * 4, 20), index.count()),
                         include=["documents", "metadatas", "distances"])
    from app.storage import sqlite as store
    live = []
    for chunk_id, text, distance, metadata in zip(result["ids"][0], result["documents"][0],
                                                   result["distances"][0], result["metadatas"][0]):
        current = store.one("""SELECT c.id FROM chunks c JOIN documents d ON d.id=c.document_id
            WHERE c.id=? AND c.version=d.version AND d.status='ready'""", (chunk_id,))
        if current:
            live.append({"chunk_id": chunk_id, "text": text, "score": round(1 - distance, 4), **metadata})
        if len(live) >= limit:
            break
    return live

