import math
import re
import uuid
from collections import Counter

from app.models.schemas import TopicInput
from app.retrieval.vector import embeddings
from app.storage import graph, sqlite as store


STOP = {"the", "and", "for", "with", "using", "based", "project", "report", "system", "study", "analysis"}


def _theme_hint(filename: str) -> str | None:
    # A repeated leading filename term is often the collection name. Treat it as
    # a boundary, while leaving unrelated filenames to semantic clustering.
    words = re.findall(r"[A-Za-z]{3,}", filename.rsplit(".", 1)[0])
    return next((word.lower() for word in words if word.lower() not in STOP), None)


def list_topics() -> list[dict]:
    topics = store.rows("SELECT * FROM topics ORDER BY label")
    for topic in topics:
        topic["documents"] = store.rows("""SELECT d.id,d.filename,d.status FROM topic_members m
            JOIN documents d ON d.id=m.document_id WHERE m.topic_id=? ORDER BY d.filename""", (topic["id"],))
    return topics


def save_topic(topic_id: str | None, data: TopicInput) -> dict:
    for document_id in data.document_ids:
        if not store.one("SELECT id FROM documents WHERE id=? AND status='ready'", (document_id,)):
            raise ValueError(f"Document is missing or not ready: {document_id}")
    topic_id = topic_id or "topic-" + uuid.uuid4().hex[:16]
    with store.transaction() as db:
        db.execute("""INSERT INTO topics(id,label,status,created_at,updated_at) VALUES(?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET label=excluded.label,status=excluded.status,updated_at=excluded.updated_at""",
                   (topic_id, data.label, data.status, store.now(), store.now()))
        db.execute("DELETE FROM topic_members WHERE topic_id=?", (topic_id,))
        db.executemany("INSERT INTO topic_members(topic_id,document_id) VALUES(?,?)",
                       [(topic_id, document_id) for document_id in data.document_ids])
        if data.status == "approved":
            # Keep the review record unapproved if its graph projection fails.
            graph.upsert_topic({"id": topic_id, "label": data.label}, data.document_ids)
    return next(t for t in list_topics() if t["id"] == topic_id)


def _label(documents: list[dict]) -> str:
    hints = {_theme_hint(doc["filename"]) for doc in documents}
    if len(hints) == 1 and None not in hints:
        return next(iter(hints)).title()
    words = Counter()
    for doc in documents:
        words.update(w.lower() for w in re.findall(r"[A-Za-z]{4,}", doc["filename"]) if w.lower() not in STOP)
    common = [word.title() for word, _ in words.most_common(2)]
    return " ".join(common) if common else "Untitled group"


def suggest_topics() -> list[dict]:
    docs = store.rows("SELECT id,filename FROM documents WHERE status='ready' ORDER BY filename")
    if not docs:
        return []
    texts = []
    for doc in docs:
        chunks = store.rows("SELECT text FROM chunks WHERE document_id=? ORDER BY page,ordinal LIMIT 3", (doc["id"],))
        texts.append(" ".join(c["text"] for c in chunks)[:3000] or doc["filename"])
    vectors = embeddings(texts)
    hints = [_theme_hint(doc["filename"]) for doc in docs]
    repeated_hints = {hint for hint, count in Counter(hints).items() if hint and count >= 2}
    parent = list(range(len(docs)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def similarity(a: list[float], b: list[float]) -> float:
        numerator = sum(x * y for x, y in zip(a, b))
        denominator = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
        return numerator / denominator if denominator else 0

    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            if hints[i] in repeated_hints and hints[j] in repeated_hints and hints[i] != hints[j]:
                continue
            if similarity(vectors[i], vectors[j]) >= 0.72:
                parent[root(j)] = root(i)
    groups: dict[int, list[dict]] = {}
    for i, doc in enumerate(docs):
        groups.setdefault(root(i), []).append(doc)
    with store.transaction() as db:
        db.execute("DELETE FROM topics WHERE status='suggested'")
    result = []
    for members in groups.values():
        result.append(save_topic(None, TopicInput(label=_label(members),
                         document_ids=[d["id"] for d in members], status="suggested")))
    return result


def merge_topics(primary_id: str, secondary_id: str) -> dict:
    if primary_id == secondary_id:
        raise ValueError("Choose two different topics")
    current = {topic["id"]: topic for topic in list_topics()}
    if primary_id not in current or secondary_id not in current:
        raise ValueError("Topic not found")
    primary, secondary = current[primary_id], current[secondary_id]
    member_ids = sorted({d["id"] for d in primary["documents"] + secondary["documents"]})
    updated = save_topic(primary_id, TopicInput(label=primary["label"], document_ids=member_ids, status="approved"))
    with store.transaction() as db:
        db.execute("DELETE FROM topics WHERE id=?", (secondary_id,))
    if secondary["status"] == "approved":
        graph.delete_topic(secondary_id)
    return updated


def split_topic(source_id: str, label: str, document_ids: list[str]) -> dict:
    source = next((topic for topic in list_topics() if topic["id"] == source_id), None)
    if not source:
        raise ValueError("Topic not found")
    original = {d["id"] for d in source["documents"]}
    moving = set(document_ids)
    if not moving or not moving < original:
        raise ValueError("Select a nonempty subset of this topic's documents")
    new_topic = save_topic(None, TopicInput(label=label, document_ids=sorted(moving), status="approved"))
    save_topic(source_id, TopicInput(label=source["label"], document_ids=sorted(original - moving), status="approved"))
    return new_topic
