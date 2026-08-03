"""Neo4jClient (T005): wrapper mong quanh official `neo4j` Python driver.

Trach nhiem duy nhat cua module nay: "noi chuyen voi Neo4j" (mo driver,
chay Cypher tham so hoa, dam bao constraint/index) - khong chua logic
extraction hay retrieval (constitution Dieu 5).

Connection settings (uri/user/password) doc qua `app.config`, khong doc
`.env` truc tiep o day (constitution Dieu 4).
"""
from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase

from app import config

# Bon cau lenh constraint/index co dinh, verbatim tu data-model.md
# (khong phai "magic value" - day la phan cua spec, dung IF NOT EXISTS
# de idempotent, an toan goi lai moi lan startup).
_CONSTRAINTS_AND_INDEXES: tuple[str, ...] = (
    "CREATE CONSTRAINT article_id_unique IF NOT EXISTS "
    "FOR (a:Article) REQUIRE a.article_id IS UNIQUE;",
    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS "
    "FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;",
    "CREATE INDEX article_chroma_id IF NOT EXISTS "
    "FOR (a:Article) ON (a.chroma_id);",
    "CREATE INDEX document_batch_id IF NOT EXISTS "
    "FOR (d:Document) ON (d.batch_id);",
)


class Neo4jClient:
    """Wrapper quanh `neo4j.GraphDatabase.driver` cho graph-rag-legal-qa.

    Dung nhu context manager de dam bao driver duoc dong dung cach:

        with Neo4jClient() as client:
            client.run("MATCH (n) RETURN n LIMIT $limit", limit=10)
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self.uri = uri if uri is not None else config.NEO4J_URI
        self.user = user if user is not None else config.NEO4J_USER
        self.password = password if password is not None else config.NEO4J_PASSWORD

        # Driver co built-in connection pooling - khong tu implement
        # pooling rieng (constitution Dieu 1).
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def run(self, query: str, **params: Any) -> list[dict]:
        """Chay mot cau Cypher tham so hoa va tra ve list of dict.

        `params` luon duoc truyen qua driver nhu tham so Cypher (`$name`),
        khong bao gio string-format truc tiep vao chuoi query - tranh
        injection.
        """
        with self._driver.session() as session:
            result = session.run(query, **params)
            return [record.data() for record in result]

    def ensure_constraints_and_indexes(self) -> None:
        """Dam bao 2 constraint + 2 index bat buoc ton tai (idempotent)."""
        with self._driver.session() as session:
            for statement in _CONSTRAINTS_AND_INDEXES:
                session.run(statement)

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
