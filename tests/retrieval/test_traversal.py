"""Tests cho app/retrieval/traversal.py (T011 + T015).

Khong co Neo4j that chay trong moi truong nay - cung quy uoc "honest
mocking" nhu tests/graph_store/test_upsert.py: mock `Neo4jClient.run` va
kiem tra CA Cypher/tham so gui di LAN du lieu mock tra ve, khong phai
"Neo4j thuc thi dung hay khong".

Cac case theo task-3d-brief.md:
  1. Mot entry point, chuoi 2-hop khong vong lap (A->B->C).
  2. Vong lap trich dan (A->B->A) voi max_hop=2 - khong lap vo han, khong
     duplicate B trong visited, canh B->A VAN co trong edges, nhung
     client.run() chi duoc goi dung max_hop lan (khong phai "bao nhieu
     lan vong lap ngu y").
  3. max_hop=1 tren mot chuoi du dai 2+ hop - chi hang xom 1-hop duoc tham,
     hop thu hai khong bao gio xuat hien.
  4. Nhieu entry point cung luc - frontier ban dau la HOP cua tat ca entry
     point, khong chi entry point dau tien.
  5. External placeholder (is_external=True) gap giua traversal - vao
     external_article_ids, khong crash, tu nhien dong gop 0 canh o hop sau.
  6. entry_article_ids rong - tra ve TraversalResult rong, KHONG goi Neo4j.
  7. Moi hop la MOT loi goi client.run() DUY NHAT bao phu toan bo frontier
     qua UNWIND (khong phai mot loi goi cho moi frontier node).
"""
from unittest.mock import MagicMock

from app.retrieval.traversal import TraversalEdge, TraversalResult, traverse


def _make_mock_client():
    return MagicMock()


def _row(from_id: str, to_id: str, rel_type: str = "REFERENCES", is_external: bool = False) -> dict:
    """Mo phong 1 dong tra ve tu `_TRAVERSAL_QUERY`. `to_id` duoc dat vao
    `to_article_id` (REFERENCES, b la :Article) hoac `to_term_id` (DEFINES,
    b la :Term) tuong ung - dung y nghia cot Cypher that su tra ve, khong
    phai mot cot `to_id` chung chung nhu truoc khi fix bug (b:Article) ep
    ca hai loai canh vao cung mot label."""
    row = {
        "from_id": from_id,
        "rel_type": rel_type,
        "to_article_id": None,
        "to_term_id": None,
        "is_external": is_external,
    }
    if rel_type == "DEFINES":
        row["to_term_id"] = to_id
    else:
        row["to_article_id"] = to_id
    return row


# --- Case 1: chuoi 2-hop, khong vong lap -----------------------------------


def test_single_entry_point_two_hop_chain_no_cycle():
    client = _make_mock_client()
    client.run.side_effect = [
        [_row("A", "B")],
        [_row("B", "C")],
    ]

    result = traverse(client, ["A"], max_hop=2)

    assert result.visited_article_ids == {"A", "B", "C"}
    assert TraversalEdge("A", "B", "REFERENCES") in result.edges
    assert TraversalEdge("B", "C", "REFERENCES") in result.edges
    assert len(result.edges) == 2
    assert client.run.call_count == 2


# --- Case 2: vong lap trich dan A->B->A ------------------------------------


def test_citation_cycle_does_not_loop_and_bounds_query_count():
    client = _make_mock_client()
    client.run.side_effect = [
        [_row("A", "B")],
        [_row("B", "A")],
    ]

    result = traverse(client, ["A"], max_hop=2)

    assert result.visited_article_ids == {"A", "B"}
    assert TraversalEdge("A", "B", "REFERENCES") in result.edges
    assert TraversalEdge("B", "A", "REFERENCES") in result.edges
    assert len(result.edges) == 2
    # Dung dung max_hop lan goi, khong phai "vong lap se lam bao nhieu lan"
    assert client.run.call_count == 2


# --- Case 3: max_hop=1 gioi han dung hop thu hai khong xuat hien ----------


def test_max_hop_one_stops_before_second_hop():
    client = _make_mock_client()
    client.run.side_effect = [
        [_row("A", "B")],
    ]

    result = traverse(client, ["A"], max_hop=1)

    assert result.visited_article_ids == {"A", "B"}
    assert "C" not in result.visited_article_ids
    assert len(result.edges) == 1
    assert client.run.call_count == 1


# --- Case 4: nhieu entry point cung luc ------------------------------------


def test_multiple_entry_points_union_as_initial_frontier():
    client = _make_mock_client()
    client.run.side_effect = [
        [_row("A", "C"), _row("X", "Y")],
    ]

    result = traverse(client, ["A", "X"], max_hop=1)

    first_call_kwargs = client.run.call_args_list[0].kwargs
    assert set(first_call_kwargs["frontier_ids"]) == {"A", "X"}

    assert result.visited_article_ids == {"A", "X", "C", "Y"}
    assert TraversalEdge("A", "C", "REFERENCES") in result.edges
    assert TraversalEdge("X", "Y", "REFERENCES") in result.edges


# --- Case 5: external placeholder giua traversal ---------------------------


def test_external_placeholder_surfaced_and_does_not_crash_traversal():
    client = _make_mock_client()
    client.run.side_effect = [
        [_row("A", "B", is_external=True)],
        [],  # B la external placeholder - khong co canh outgoing that
    ]

    result = traverse(client, ["A"], max_hop=2)

    assert result.visited_article_ids == {"A", "B"}
    assert result.external_article_ids == {"B"}
    assert len(result.edges) == 1
    assert client.run.call_count == 2


# --- Case 6: entry_article_ids rong -----------------------------------------


def test_empty_entry_article_ids_returns_empty_result_without_querying():
    client = _make_mock_client()

    result = traverse(client, [], max_hop=2)

    assert result == TraversalResult()
    assert result.visited_article_ids == set()
    assert result.edges == []
    assert result.external_article_ids == set()
    client.run.assert_not_called()


# --- Case 7: moi hop la MOT loi goi batched, khong phai 1 loi goi/node ------


def test_query_is_batched_once_per_hop_not_once_per_frontier_node():
    client = _make_mock_client()
    client.run.side_effect = [
        [_row("A", "P"), _row("B", "Q"), _row("C", "R")],
    ]

    result = traverse(client, ["A", "B", "C"], max_hop=1)

    # Dung 1 loi goi cho ca hop nay, du frontier co 3 node - khong phai 3
    # loi goi (moi node mot loi goi).
    assert client.run.call_count == 1
    call = client.run.call_args_list[0]
    query = call.args[0]
    assert "UNWIND" in query
    assert set(call.kwargs["frontier_ids"]) == {"A", "B", "C"}
    assert result.visited_article_ids == {"A", "B", "C", "P", "Q", "R"}
    assert len(result.edges) == 3


# --- Case 8: canh DEFINES (Article -> Term) khong bi ep ve :Article --------


def test_defines_edge_goes_to_visited_term_ids_not_frontier():
    """Article A --DEFINES--> Term T1, dong thoi A --REFERENCES--> B.

    T1 phai vao `visited_term_ids` (khong phai `visited_article_ids`), canh
    duoc ghi lai trong `edges`, va T1 KHONG duoc dua vao frontier hop ke
    tiep - chi B (tu canh REFERENCES) duoc UNWIND o hop 2. Day la regression
    test cho bug: query cu ep target vao (b:Article) nen DEFINES khong bao
    gio tra ve duoc, ke ca sau khi T012 populate DEFINES that su.
    """
    client = _make_mock_client()
    client.run.side_effect = [
        [_row("A", "T1", rel_type="DEFINES"), _row("A", "B")],
        [],  # hop 2: chi B duoc tham, T1 khong xuat hien trong frontier
    ]

    result = traverse(client, ["A"], max_hop=2)

    assert result.visited_term_ids == {"T1"}
    assert "T1" not in result.visited_article_ids
    assert TraversalEdge("A", "T1", "DEFINES") in result.edges
    assert TraversalEdge("A", "B", "REFERENCES") in result.edges
    assert len(result.edges) == 2

    assert client.run.call_count == 2
    second_call_kwargs = client.run.call_args_list[1].kwargs
    assert set(second_call_kwargs["frontier_ids"]) == {"B"}
    assert "T1" not in second_call_kwargs["frontier_ids"]


# --- Default max_hop reads from config.MAX_HOP ------------------------------


def test_default_max_hop_reads_from_config(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MAX_HOP", 1)

    client = _make_mock_client()
    client.run.side_effect = [
        [_row("A", "B")],
    ]

    result = traverse(client, ["A"])

    assert client.run.call_count == 1
    assert result.visited_article_ids == {"A", "B"}
