"""Tests cho app/graph_store/neo4j_client.py (T005).

Khong co Neo4j that chay trong moi truong nay - moi test o day mock
`GraphDatabase.driver` va `driver.session()` de kiem tra:
  (1) constructor doc dung connection settings tu app.config,
  (2) `run()` truyen query + params dung cach vao session.run() va
      chuyen ket qua thanh list[dict],
  (3) `ensure_constraints_and_indexes()` gui dung 4 cau Cypher, verbatim,
      qua session.run(),
  (4) `close()` / context manager goi driver.close().

Day la kiem tra "co gui dung Cypher/tham so hay khong", khong phai
"Neo4j co thuc thi dung hay khong" - hop ly de unit test bang mock,
khong phai mock rong tue.
"""
from unittest.mock import MagicMock, patch

import pytest

from app import config
from app.graph_store.neo4j_client import Neo4jClient

EXPECTED_STATEMENTS = (
    "CREATE CONSTRAINT article_id_unique IF NOT EXISTS "
    "FOR (a:Article) REQUIRE a.article_id IS UNIQUE",
    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS "
    "FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
    "CREATE INDEX article_chroma_id IF NOT EXISTS "
    "FOR (a:Article) ON (a.chroma_id)",
    "CREATE INDEX document_batch_id IF NOT EXISTS "
    "FOR (d:Document) ON (d.batch_id)",
)


def _make_mock_driver():
    """Tao mock driver voi mock session ho tro context manager."""
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_driver.session.return_value.__exit__.return_value = False
    return mock_driver, mock_session


@patch("app.graph_store.neo4j_client.GraphDatabase")
def test_constructor_reads_connection_settings_from_config(mock_graphdb):
    mock_driver, _ = _make_mock_driver()
    mock_graphdb.driver.return_value = mock_driver

    client = Neo4jClient()

    assert client.uri == config.NEO4J_URI
    assert client.user == config.NEO4J_USER
    assert client.password == config.NEO4J_PASSWORD
    mock_graphdb.driver.assert_called_once_with(
        config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
    )


@patch("app.graph_store.neo4j_client.GraphDatabase")
def test_constructor_accepts_explicit_overrides(mock_graphdb):
    mock_driver, _ = _make_mock_driver()
    mock_graphdb.driver.return_value = mock_driver

    Neo4jClient(uri="bolt://other:7687", user="u", password="p")

    mock_graphdb.driver.assert_called_once_with("bolt://other:7687", auth=("u", "p"))


@patch("app.graph_store.neo4j_client.GraphDatabase")
def test_run_passes_query_and_params_and_returns_list_of_dict(mock_graphdb):
    mock_driver, mock_session = _make_mock_driver()
    mock_graphdb.driver.return_value = mock_driver

    record1 = MagicMock()
    record1.data.return_value = {"a": 1}
    record2 = MagicMock()
    record2.data.return_value = {"a": 2}
    mock_session.run.return_value = [record1, record2]

    client = Neo4jClient()
    result = client.run("MATCH (n) RETURN n.a AS a LIMIT $limit", limit=2)

    mock_session.run.assert_called_once_with(
        "MATCH (n) RETURN n.a AS a LIMIT $limit", limit=2
    )
    assert result == [{"a": 1}, {"a": 2}]


@patch("app.graph_store.neo4j_client.GraphDatabase")
def test_ensure_constraints_and_indexes_sends_exact_statements(mock_graphdb):
    mock_driver, mock_session = _make_mock_driver()
    mock_graphdb.driver.return_value = mock_driver

    client = Neo4jClient()
    client.ensure_constraints_and_indexes()

    actual_calls = [call.args[0] for call in mock_session.run.call_args_list]
    assert actual_calls == list(EXPECTED_STATEMENTS)


@patch("app.graph_store.neo4j_client.GraphDatabase")
def test_close_closes_driver(mock_graphdb):
    mock_driver, _ = _make_mock_driver()
    mock_graphdb.driver.return_value = mock_driver

    client = Neo4jClient()
    client.close()

    mock_driver.close.assert_called_once()


@patch("app.graph_store.neo4j_client.GraphDatabase")
def test_context_manager_closes_driver_on_exit(mock_graphdb):
    mock_driver, _ = _make_mock_driver()
    mock_graphdb.driver.return_value = mock_driver

    with Neo4jClient() as client:
        assert isinstance(client, Neo4jClient)

    mock_driver.close.assert_called_once()


@patch("app.graph_store.neo4j_client.GraphDatabase")
def test_context_manager_closes_driver_even_on_exception(mock_graphdb):
    mock_driver, _ = _make_mock_driver()
    mock_graphdb.driver.return_value = mock_driver

    with pytest.raises(ValueError):
        with Neo4jClient():
            raise ValueError("boom")

    mock_driver.close.assert_called_once()
