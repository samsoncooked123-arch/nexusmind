"""Rebuild only the Chroma projection when the embedding model changes."""
from app.retrieval.vector import index_chunks
from app.storage import sqlite as store


def main() -> None:
    store.migrate()
    chunks = store.rows("""SELECT c.id,c.document_id,c.page,c.text,c.version,d.filename
        FROM chunks c JOIN documents d ON d.id=c.document_id
        WHERE c.version=d.version AND d.status='ready' ORDER BY c.document_id,c.page,c.ordinal""")
    index_chunks(chunks)
    print(f"Indexed {len(chunks)} current passages")


if __name__ == "__main__":
    main()
