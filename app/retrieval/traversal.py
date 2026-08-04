"""traversal.py (T011 + T015): N-hop graph traversal tu mot hoac nhieu
Article entry point (do `entry_point.py`, T010, tim ra), theo canh
`REFERENCES` va `DEFINES`, tra ve moi Article den duoc cung path (danh
cho hien thi citation sau nay, FR-006), xu ly dung vong lap trich dan va
external reference placeholder (data-model.md).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): graph
traversal thuan tuy qua `Neo4jClient`. Khong vector search (do la
`entry_point.py`), khong LLM/sinh cau tra loi, khong API serving, khong
sinh text hien thi "khong co trong corpus" cho external article (do la
`serving/api.py`, T014 - module nay chi SURFACE qua `external_article_ids`).

=== Vi sao BFS thu cong tu Python, khong dung mot cau Cypher
variable-length duy nhat ===
Cypher pattern `[:REFERENCES*1..N]` chi cam lap lai CUNG MOT RELATIONSHIP
trong mot path, khong cam lap lai CUNG MOT NODE - nen mot vong lap trich
dan (Dieu A -> Dieu B -> Dieu A) van co the xuat hien nhu mot path "hop
le" theo luat cua Cypher. spec.md edge case yeu cau chong lap vo han that
su (khong chi gioi han so hop), nen traversal nay dung BFS tung hop tu
Python voi mot `visited` set o muc ung dung (khong bao gio traverse tiep
tu - hay tra ve nhu "moi thay" - mot node da visited trong lan traversal
nay). Don gian hon va de kiem tra dung hon la nhoi dedup logic vao trong
Cypher (Dieu 1 - don gian hon la khon kheo).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app import config
from app.graph_store.neo4j_client import Neo4jClient

_TRAVERSAL_QUERY = (
    "UNWIND $frontier_ids AS from_id\n"
    "MATCH (a:Article {article_id: from_id})-[r:REFERENCES|DEFINES]->(b:Article)\n"
    "RETURN from_id AS from_id, type(r) AS rel_type, b.article_id AS to_id, "
    "b.is_external AS is_external"
)


@dataclass
class TraversalEdge:
    from_article_id: str
    to_article_id: str
    relationship_type: str  # "REFERENCES" hoac "DEFINES"


@dataclass
class TraversalResult:
    visited_article_ids: set[str] = field(default_factory=set)
    edges: list[TraversalEdge] = field(default_factory=list)
    external_article_ids: set[str] = field(default_factory=set)


def traverse(
    client: Neo4jClient,
    entry_article_ids: list[str],
    max_hop: int | None = None,
) -> TraversalResult:
    """BFS toi da `max_hop` hop (mac dinh `config.MAX_HOP`) tu
    `entry_article_ids` qua canh REFERENCES/DEFINES.

    - `visited_article_ids` bao gom CA entry point ban dau.
    - `edges` chua MOI canh thuc su duoc tra ve tu Neo4j, KE CA canh tro
      nguoc lai node da visited (vi du canh B->A trong vong lap A->B->A) -
      day chinh la cach vong lap trich dan duoc GIU LAI trong ket qua ma
      khong gay lap vo han: canh duoc ghi nhan, nhung node khong duoc
      expand lan thu hai.
    - `external_article_ids` la tap con cua `visited_article_ids` co
      `Article.is_external == True` - khong tu expand tiep tu node nay o
      hop sau (no khong co canh outgoing that, se tu nhien tra ve 0 dong,
      khong can special-case).
    - `entry_article_ids` rong -> tra ve TraversalResult rong, khong goi
      Neo4j (khong query voi UNWIND rong).
    """
    if not entry_article_ids:
        return TraversalResult()

    if max_hop is None:
        max_hop = config.MAX_HOP

    visited: set[str] = set(entry_article_ids)
    frontier: set[str] = set(entry_article_ids)
    edges: list[TraversalEdge] = []
    external_article_ids: set[str] = set()

    for _hop in range(max_hop):
        if not frontier:
            break

        rows = client.run(_TRAVERSAL_QUERY, frontier_ids=sorted(frontier))

        next_frontier: set[str] = set()
        for row in rows:
            from_id = row["from_id"]
            to_id = row["to_id"]
            rel_type = row["rel_type"]

            edges.append(
                TraversalEdge(
                    from_article_id=from_id,
                    to_article_id=to_id,
                    relationship_type=rel_type,
                )
            )

            if to_id not in visited:
                visited.add(to_id)
                next_frontier.add(to_id)
                if row.get("is_external"):
                    external_article_ids.add(to_id)

        frontier = next_frontier

    return TraversalResult(
        visited_article_ids=visited,
        edges=edges,
        external_article_ids=external_article_ids,
    )
