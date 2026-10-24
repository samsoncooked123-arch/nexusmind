from functools import lru_cache
import socket
from urllib.parse import urlparse

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

from app import config
from app.storage import sqlite_graph


RELATIONS = {"USES_METHOD", "EVALUATED_ON", "CREATED_BY"}


@lru_cache(maxsize=1)
def _driver():
    return GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
                                connection_timeout=3, max_transaction_retry_time=5)


def driver():
    endpoint = urlparse(config.NEO4J_URI)
    try:
        with socket.create_connection((endpoint.hostname or "localhost", endpoint.port or 7687), timeout=0.4):
            pass
    except OSError as exc:
        raise ServiceUnavailable("Neo4j is not running") from exc
    return _driver()


def verify() -> None:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.verify()
    driver().verify_connectivity()


def initialize() -> None:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.initialize()
    queries = [
        "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE",
    ]
    for query in queries:
        driver().execute_query(query, database_=config.NEO4J_DATABASE)


def approve_fact(fact: dict) -> None:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.approve_fact(fact)
    if fact["relation"] not in RELATIONS:
        raise ValueError("Unsupported relationship")
    query = f"""
    MERGE (s:Entity {{id: $subject_id}})
    SET s.name=coalesce(s.name,$subject_name), s.type=$subject_type,
        s.aliases=CASE WHEN $subject_name IN coalesce(s.aliases,[]) THEN s.aliases
                       ELSE coalesce(s.aliases,[]) + $subject_name END
    MERGE (o:Entity {{id: $object_id}})
    SET o.name=coalesce(o.name,$object_name), o.type=$object_type,
        o.aliases=CASE WHEN $object_name IN coalesce(o.aliases,[]) THEN o.aliases
                       ELSE coalesce(o.aliases,[]) + $object_name END
    MERGE (s)-[r:{fact['relation']} {{fact_id: $fact_id}}]->(o)
    SET r.evidence_chunk_id=$evidence_chunk_id, r.document_id=$document_id,
        r.polarity=$polarity
    """
    driver().execute_query(query, subject_id=fact["subject_id"], subject_name=fact["subject_name"],
                           subject_type=fact["subject_type"], object_id=fact["object_id"],
                           object_name=fact["object_name"], object_type=fact["object_type"],
                           fact_id=fact["id"], evidence_chunk_id=fact["evidence_chunk_id"],
                           document_id=fact["document_id"], polarity=fact.get("polarity", "supports"),
                           database_=config.NEO4J_DATABASE)


def remove_document(document_id: str) -> None:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.remove_document(document_id)
    driver().execute_query("""MATCH ()-[r]->() WHERE r.document_id=$id AND
        type(r) IN ['USES_METHOD','EVALUATED_ON','CREATED_BY'] DELETE r""",
        id=document_id, database_=config.NEO4J_DATABASE)
    driver().execute_query("MATCH (d:Document {id:$id}) DETACH DELETE d", id=document_id,
                           database_=config.NEO4J_DATABASE)
    driver().execute_query("MATCH (e:Entity) WHERE NOT EXISTS { MATCH (e)--() } DELETE e",
                           database_=config.NEO4J_DATABASE)


def statistics() -> dict:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.statistics()
    records, _, _ = driver().execute_query("""MATCH (n) WITH count(n) AS nodes
        OPTIONAL MATCH ()-[r]->() RETURN nodes,count(r) AS edges""", database_=config.NEO4J_DATABASE)
    return dict(records[0]) if records else {"nodes": 0, "edges": 0}


def upsert_topic(topic: dict, document_ids: list[str]) -> None:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.upsert_topic(topic, document_ids)
    initialize()
    driver().execute_query("MERGE (t:Topic {id:$id}) SET t.label=$label",
                           id=topic["id"], label=topic["label"], database_=config.NEO4J_DATABASE)
    driver().execute_query("MATCH (t:Topic {id:$id})<-[r:ABOUT_TOPIC]-(:Document) DELETE r",
                           id=topic["id"], database_=config.NEO4J_DATABASE)
    for doc_id in document_ids:
        driver().execute_query("MERGE (d:Document {id:$doc_id}) WITH d MATCH (t:Topic {id:$topic_id}) MERGE (d)-[:ABOUT_TOPIC]->(t)",
                               doc_id=doc_id, topic_id=topic["id"], database_=config.NEO4J_DATABASE)


def delete_topic(topic_id: str) -> None:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.delete_topic(topic_id)
    driver().execute_query("MATCH (t:Topic {id:$id}) DETACH DELETE t", id=topic_id,
                           database_=config.NEO4J_DATABASE)


def entities(query: str = "", limit: int = 100) -> list[dict]:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.entities(query, limit)
    records, _, _ = driver().execute_query(
        "MATCH (e:Entity) WHERE toLower(e.name) CONTAINS toLower($query) OR any(a IN coalesce(e.aliases,[]) WHERE toLower(a) CONTAINS toLower($query)) RETURN e.id AS id,e.name AS name,e.type AS type,e.aliases AS aliases ORDER BY e.name LIMIT $limit",
        query=query, limit=limit, database_=config.NEO4J_DATABASE)
    return [dict(record) for record in records]


def neighborhood(entity_id: str, limit: int = 80) -> dict:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.neighborhood(entity_id, limit)
    records, _, _ = driver().execute_query("""
        MATCH (s:Entity {id:$entity_id})-[r]-(o:Entity)
        WHERE type(r) IN ['USES_METHOD','EVALUATED_ON','CREATED_BY']
        RETURN s.id AS sid,s.name AS sname,s.type AS stype,
               o.id AS oid,o.name AS oname,o.type AS otype,
               startNode(r).id AS source,endNode(r).id AS target,
               r.fact_id AS fact_id,type(r) AS relation,r.evidence_chunk_id AS evidence_chunk_id,
               coalesce(r.polarity,'supports') AS polarity
        LIMIT $limit
    """, entity_id=entity_id, limit=limit, database_=config.NEO4J_DATABASE)
    nodes = {}
    edges = []
    for r in records:
        nodes[r["sid"]] = {"id": r["sid"], "name": r["sname"], "type": r["stype"]}
        nodes[r["oid"]] = {"id": r["oid"], "name": r["oname"], "type": r["otype"]}
        edges.append({"id": r["fact_id"], "source": r["source"], "target": r["target"],
                      "relation": r["relation"], "evidence_chunk_id": r["evidence_chunk_id"],
                      "polarity": r["polarity"]})
    if not nodes:
        found = [e for e in entities() if e["id"] == entity_id]
        if found:
            nodes[entity_id] = found[0]
    return {"nodes": list(nodes.values()), "edges": edges}


def paths_from(entity_id: str, max_hops: int = 3, limit: int = 40) -> list[dict]:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.paths_from(entity_id, max_hops, limit)
    # Bounded, typed paths prevent arbitrary traversals through topic/document links.
    records, _, _ = driver().execute_query("""
      MATCH p=(start:Entity {id:$id})-[*1..3]-(other:Entity)
      WHERE all(r IN relationships(p) WHERE type(r) IN ['USES_METHOD','EVALUATED_ON','CREATED_BY'])
      RETURN [n IN nodes(p) | {id:n.id,name:n.name,type:n.type}] AS nodes,
             [r IN relationships(p) | {id:r.fact_id,relation:type(r),polarity:coalesce(r.polarity,'supports'),
                                      evidence_chunk_id:r.evidence_chunk_id,
                                      source:startNode(r).id,target:endNode(r).id}] AS edges
      LIMIT $limit
    """, id=entity_id, limit=limit, database_=config.NEO4J_DATABASE)
    return [{"nodes": r["nodes"], "edges": r["edges"]} for r in records if len(r["edges"]) <= max_hops]


def relations_for_documents(document_ids: list[str], limit: int = 30) -> dict:
    if config.GRAPH_BACKEND == "sqlite":
        return sqlite_graph.relations_for_documents(document_ids, limit)
    records, _, _ = driver().execute_query("""
      MATCH (s:Entity)-[r]->(o:Entity)
      WHERE type(r) IN ['USES_METHOD','EVALUATED_ON','CREATED_BY'] AND r.document_id IN $document_ids
      RETURN s.id AS sid,s.name AS sname,s.type AS stype,o.id AS oid,o.name AS oname,o.type AS otype,
             r.fact_id AS fact_id,type(r) AS relation,r.evidence_chunk_id AS evidence_chunk_id,
             coalesce(r.polarity,'supports') AS polarity
      LIMIT $limit
    """, document_ids=document_ids, limit=limit, database_=config.NEO4J_DATABASE)
    nodes = {}
    edges = []
    for r in records:
        nodes[r["sid"]] = {"id": r["sid"], "name": r["sname"], "type": r["stype"]}
        nodes[r["oid"]] = {"id": r["oid"], "name": r["oname"], "type": r["otype"]}
        edges.append({"id": r["fact_id"], "source": r["sid"], "target": r["oid"],
                      "relation": r["relation"], "evidence_chunk_id": r["evidence_chunk_id"],
                      "polarity": r["polarity"]})
    return {"nodes": list(nodes.values()), "edges": edges}
