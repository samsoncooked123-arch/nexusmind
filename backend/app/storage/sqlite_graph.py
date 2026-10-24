"""Evidence graph derived from approved, current SQLite facts.

This local backend keeps the review gate and source citations without needing
a separate Neo4j process. The facts and topic memberships remain authoritative.
"""
from collections import defaultdict

from app.storage import sqlite as store


RELATIONS = {"USES_METHOD", "EVALUATED_ON", "CREATED_BY"}


def verify() -> None:
    store.one("SELECT 1 AS ok")


def initialize() -> None:
    pass


def approve_fact(fact: dict) -> None:
    if fact["relation"] not in RELATIONS:
        raise ValueError("Unsupported relationship")


def remove_document(document_id: str) -> None:
    # Queries exclude non-ready documents and stale versions. Deleting or
    # replacing their SQLite rows removes graph edges by foreign-key cascade.
    pass


def upsert_topic(topic: dict, document_ids: list[str]) -> None:
    # save_topic writes both records and memberships in the same transaction.
    pass


def delete_topic(topic_id: str) -> None:
    pass


def _data() -> tuple[dict[str, dict], list[dict]]:
    facts = store.rows("""SELECT f.* FROM facts f
        JOIN chunks c ON c.id=f.evidence_chunk_id
        JOIN documents d ON d.id=f.document_id
        WHERE f.status='approved' AND d.status='ready'
          AND c.document_id=d.id AND c.version=d.version
        ORDER BY f.created_at,f.id""")
    topic_rows = store.rows("""SELECT m.document_id,t.label FROM topic_members m
        JOIN topics t ON t.id=m.topic_id WHERE t.status='approved'""")
    topics_by_document: dict[str, set[str]] = defaultdict(set)
    for item in topic_rows:
        topics_by_document[item["document_id"]].add(item["label"])
    nodes: dict[str, dict] = {}
    edges = []
    for fact in facts:
        for side in ("subject", "object"):
            entity_id = fact[f"{side}_id"]
            name = fact[f"{side}_name"]
            if entity_id not in nodes:
                nodes[entity_id] = {"id": entity_id, "name": name,
                                    "type": fact[f"{side}_type"], "aliases": [name], "topics": []}
            elif name not in nodes[entity_id]["aliases"]:
                nodes[entity_id]["aliases"].append(name)
            for topic in sorted(topics_by_document[fact["document_id"]]):
                if topic not in nodes[entity_id]["topics"]:
                    nodes[entity_id]["topics"].append(topic)
        edges.append({"id": fact["id"], "source": fact["subject_id"],
                      "target": fact["object_id"], "relation": fact["relation"],
                      "evidence_chunk_id": fact["evidence_chunk_id"],
                      "document_id": fact["document_id"], "polarity": fact["polarity"]})
    return nodes, edges


def _public(edge: dict) -> dict:
    return {key: value for key, value in edge.items() if key != "document_id"}


def statistics() -> dict:
    nodes, edges = _data()
    memberships = store.rows("""SELECT m.document_id,m.topic_id FROM topic_members m
        JOIN topics t ON t.id=m.topic_id JOIN documents d ON d.id=m.document_id
        WHERE t.status='approved' AND d.status='ready'""")
    topic_ids = {item["topic_id"] for item in memberships}
    document_ids = {item["document_id"] for item in memberships}
    return {"nodes": len(nodes) + len(topic_ids) + len(document_ids),
            "edges": len(edges) + len(memberships)}


def entities(query: str = "", limit: int = 100) -> list[dict]:
    nodes, _ = _data()
    needle = query.casefold()
    matching = [node for node in nodes.values()
                if any(needle in name.casefold() for name in node["aliases"])]
    return sorted(matching, key=lambda node: (node["name"].casefold(), node["id"]))[:limit]


def neighborhood(entity_id: str, limit: int = 80) -> dict:
    nodes, edges = _data()
    selected = [edge for edge in edges
                if entity_id in (edge["source"], edge["target"])][:limit]
    active = {entity_id} | {node_id for edge in selected for node_id in (edge["source"], edge["target"])}
    return {"nodes": [nodes[key] for key in active if key in nodes],
            "edges": [_public(edge) for edge in selected]}


def paths_from(entity_id: str, max_hops: int = 3, limit: int = 40) -> list[dict]:
    nodes, edges = _data()
    if entity_id not in nodes:
        return []
    adjacent: dict[str, list[dict]] = defaultdict(list)
    for edge in edges:
        adjacent[edge["source"]].append(edge)
        adjacent[edge["target"]].append(edge)
    paths: list[dict] = []

    def walk(current: str, visited: set[str], node_path: list[str], edge_path: list[dict]) -> None:
        if len(edge_path) >= max_hops or len(paths) >= limit:
            return
        for edge in adjacent[current]:
            next_id = edge["target"] if edge["source"] == current else edge["source"]
            if next_id in visited:
                continue
            next_nodes = node_path + [next_id]
            next_edges = edge_path + [_public(edge)]
            paths.append({"nodes": [nodes[key] for key in next_nodes], "edges": next_edges})
            if len(paths) >= limit:
                return
            walk(next_id, visited | {next_id}, next_nodes, next_edges)

    walk(entity_id, {entity_id}, [entity_id], [])
    return paths


def relations_for_documents(document_ids: list[str], limit: int = 30) -> dict:
    nodes, edges = _data()
    allowed = set(document_ids)
    selected = [edge for edge in edges if edge["document_id"] in allowed][:limit]
    active = {node_id for edge in selected for node_id in (edge["source"], edge["target"])}
    return {"nodes": [nodes[key] for key in active], "edges": [_public(edge) for edge in selected]}
