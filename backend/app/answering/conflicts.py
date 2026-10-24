import hashlib
from collections import defaultdict

from app.extraction.facts import normalized
from app.storage import sqlite as store


def list_conflicts() -> list[dict]:
    """Return explicit support/denial pairs from current, reviewed sources."""
    facts = store.rows("""SELECT f.id,f.document_id,f.subject_name,f.relation,f.object_name,
        f.polarity,f.evidence_quote,f.evidence_chunk_id,c.page,d.filename
        FROM facts f JOIN chunks c ON c.id=f.evidence_chunk_id
        JOIN documents d ON d.id=f.document_id
        WHERE f.status='approved' AND d.status='ready' AND c.version=d.version
        ORDER BY f.created_at""")
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for fact in facts:
        groups[(normalized(fact["subject_name"]), fact["relation"], normalized(fact["object_name"]))].append(fact)
    conflicts = []
    for key, claims in groups.items():
        supports = [claim for claim in claims if claim["polarity"] == "supports"]
        denies = [claim for claim in claims if claim["polarity"] == "denies"]
        if not supports or not denies:
            continue
        if not any(a["document_id"] != b["document_id"] for a in supports for b in denies):
            continue
        conflicts.append({
            "id": "conflict-" + hashlib.sha256("|".join(key).encode()).hexdigest()[:16],
            "subject": claims[0]["subject_name"], "relation": claims[0]["relation"],
            "object": claims[0]["object_name"], "claims": claims,
        })
    return conflicts
