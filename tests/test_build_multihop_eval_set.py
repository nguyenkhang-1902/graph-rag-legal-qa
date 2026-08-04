"""Tests cho scripts/build_multihop_eval_set.py (T016).

Khong co Neo4j/Chroma that trong sandbox test - mock o ranh gioi (cung quy
uoc "honest mocking" nhu tests/graph_store/test_upsert.py/
tests/test_backfill_embeddings.py): mock `Neo4jClient.run` (phan biet 2-hop
vs 1-hop qua chuoi con dac trung trong query text - "c_id" chi xuat hien o
cau 2-hop) VA `app.retrieval.embedder.get_texts` (khong tai model/Chroma
that).

Cac case theo task-3f-brief.md:
1. Chuoi 2-hop that, ca 3 article deu that + du dai -> xuat hien trong
   output voi dung article_id + relationship_path.
2. Mot article duoi --min-content-length -> chuoi bi loai.
3. Chuoi cham vao article is_external=true -> bi loai boi WHERE cua Cypher
   (mock khong bao gio tra ve dong do - test kiem tra bang cach KHONG dua
   dong nay vao ket qua mock, xac nhan code khong "tu suy" ra chuoi thieu).
4. Cap 1-hop cung duoc thu thap (tap phu), khong chi chuoi 2-hop.
5. Uu tien noi dung: co full text tu embedder.get_texts -> dung, danh dau
   is_preview=False; khong co -> fallback noi_dung_preview tu Neo4j, danh
   dau is_preview=True.
6. Sap xep xac dinh - goi 2 lan tren cung input -> cung thu tu output.
"""
from unittest.mock import MagicMock

from scripts.build_multihop_eval_set import (
    DEFAULT_MIN_CONTENT_LENGTH,
    build_multihop_eval_set,
)

_LONG_A = "Noi dung Dieu A that day du, du dai de vuot qua nguong loc." * 2
_LONG_B = "Noi dung Dieu B that day du, du dai de vuot qua nguong loc." * 2
_LONG_C = "Noi dung Dieu C that day du, du dai de vuot qua nguong loc." * 2
_SHORT = "Qua ngan."


def _make_mock_client(two_hop_rows=None, one_hop_rows=None):
    """Neo4jClient mock - `run()` phan biet 2 cau truy van co dinh cua module
    qua dau hieu "c_id" chi co trong RETURN cua cau 2-hop (xem
    `_TWO_HOP_QUERY`/`_ONE_HOP_QUERY`)."""
    two_hop_rows = two_hop_rows or []
    one_hop_rows = one_hop_rows or []

    def _run(query: str, **params):
        if "c_id" in query:
            return two_hop_rows
        return one_hop_rows

    client = MagicMock()
    client.run.side_effect = _run
    return client


def _two_hop_row(a_id, b_id, c_id, a_preview=_LONG_A, b_preview=_LONG_B, c_preview=_LONG_C):
    return {
        "a_id": a_id,
        "b_id": b_id,
        "c_id": c_id,
        "a_preview": a_preview,
        "b_preview": b_preview,
        "c_preview": c_preview,
    }


def _one_hop_row(a_id, b_id, a_preview=_LONG_A, b_preview=_LONG_B):
    return {"a_id": a_id, "b_id": b_id, "a_preview": a_preview, "b_preview": b_preview}


# --- Case 1: chuoi 2-hop that, day du -> xuat hien dung ---------------------


def test_two_hop_chain_with_real_sufficient_content_appears_with_correct_path():
    client = _make_mock_client(
        two_hop_rows=[_two_hop_row("luat-a_dieu-1", "luat-b_dieu-2", "luat-c_dieu-3")]
    )

    result = build_multihop_eval_set(client, min_content_length=DEFAULT_MIN_CONTENT_LENGTH)

    assert len(result["two_hop_candidates"]) == 1
    candidate = result["two_hop_candidates"][0]
    assert candidate["chain_type"] == "2-hop"
    assert candidate["article_ids"] == ["luat-a_dieu-1", "luat-b_dieu-2", "luat-c_dieu-3"]
    assert candidate["relationship_path"] == [
        {"from": "luat-a_dieu-1", "to": "luat-b_dieu-2", "type": "REFERENCES"},
        {"from": "luat-b_dieu-2", "to": "luat-c_dieu-3", "type": "REFERENCES"},
    ]
    article_ids_in_entries = [a["article_id"] for a in candidate["articles"]]
    assert article_ids_in_entries == ["luat-a_dieu-1", "luat-b_dieu-2", "luat-c_dieu-3"]


# --- Case 2: article duoi nguong do dai -> chuoi bi loai --------------------


def test_chain_with_article_below_min_content_length_is_excluded():
    client = _make_mock_client(
        two_hop_rows=[
            _two_hop_row(
                "luat-a_dieu-1", "luat-b_dieu-2", "luat-c_dieu-3", b_preview=_SHORT
            )
        ]
    )

    result = build_multihop_eval_set(client, min_content_length=DEFAULT_MIN_CONTENT_LENGTH)

    assert result["two_hop_candidates"] == []


# --- Case 3: chuoi cham is_external=true -> khong xuat hien -----------------


def test_chain_touching_external_article_is_excluded():
    # WHERE a/b/c.is_external = false trong Cypher (that) dam bao Neo4j
    # KHONG BAO GIO tra ve dong co article is_external=true - mo phong bang
    # cach mock tra ve DANH SACH RONG (dai dien cho "khong co dong nao khop
    # WHERE do"), xac nhan code phia Python khong tu bo sung/gia dinh chuoi
    # thieu nao ca.
    client = _make_mock_client(two_hop_rows=[])

    result = build_multihop_eval_set(client, min_content_length=DEFAULT_MIN_CONTENT_LENGTH)

    assert result["two_hop_candidates"] == []


# --- Case 4: cap 1-hop cung duoc thu thap (tap phu) -------------------------


def test_one_hop_pair_also_captured_as_secondary_pool():
    client = _make_mock_client(
        two_hop_rows=[],
        one_hop_rows=[_one_hop_row("luat-x_dieu-1", "luat-y_dieu-2")],
    )

    result = build_multihop_eval_set(client, min_content_length=DEFAULT_MIN_CONTENT_LENGTH)

    assert result["two_hop_candidates"] == []
    assert len(result["one_hop_candidates"]) == 1
    candidate = result["one_hop_candidates"][0]
    assert candidate["chain_type"] == "1-hop"
    assert candidate["article_ids"] == ["luat-x_dieu-1", "luat-y_dieu-2"]
    assert candidate["relationship_path"] == [
        {"from": "luat-x_dieu-1", "to": "luat-y_dieu-2", "type": "REFERENCES"}
    ]


# --- Case 5: uu tien full text tu embedder, fallback preview ---------------


def test_content_prefers_full_text_from_embedder_falls_back_to_preview(monkeypatch):
    client = _make_mock_client(
        two_hop_rows=[
            _two_hop_row("luat-a_dieu-1", "luat-b_dieu-2", "luat-c_dieu-3")
        ]
    )

    full_text_for_a = "FULL TEXT THAT tu Chroma cho Dieu A - dai hon nhieu preview." * 2
    monkeypatch.setattr(
        "scripts.build_multihop_eval_set.embedder.get_texts",
        lambda ids: {"luat-a_dieu-1": full_text_for_a},
    )

    result = build_multihop_eval_set(client, min_content_length=DEFAULT_MIN_CONTENT_LENGTH)

    candidate = result["two_hop_candidates"][0]
    by_id = {a["article_id"]: a for a in candidate["articles"]}

    # A: co full text -> dung full text, is_preview=False.
    assert by_id["luat-a_dieu-1"]["content"] == full_text_for_a
    assert by_id["luat-a_dieu-1"]["is_preview"] is False

    # B, C: khong co trong ket qua embedder.get_texts -> fallback preview.
    assert by_id["luat-b_dieu-2"]["content"] == _LONG_B
    assert by_id["luat-b_dieu-2"]["is_preview"] is True
    assert by_id["luat-c_dieu-3"]["content"] == _LONG_C
    assert by_id["luat-c_dieu-3"]["is_preview"] is True


def test_get_texts_called_once_batched_with_all_article_ids(monkeypatch):
    client = _make_mock_client(
        two_hop_rows=[_two_hop_row("luat-a_dieu-1", "luat-b_dieu-2", "luat-c_dieu-3")],
        one_hop_rows=[_one_hop_row("luat-x_dieu-1", "luat-y_dieu-2")],
    )

    mock_get_texts = MagicMock(return_value={})
    monkeypatch.setattr(
        "scripts.build_multihop_eval_set.embedder.get_texts", mock_get_texts
    )

    build_multihop_eval_set(client, min_content_length=DEFAULT_MIN_CONTENT_LENGTH)

    mock_get_texts.assert_called_once()
    (called_ids,), _ = mock_get_texts.call_args
    assert called_ids == sorted(
        [
            "luat-a_dieu-1",
            "luat-b_dieu-2",
            "luat-c_dieu-3",
            "luat-x_dieu-1",
            "luat-y_dieu-2",
        ]
    )


# --- Case 6: sap xep xac dinh - goi 2 lan cung ket qua -----------------------


def test_deterministic_ordering_across_two_calls():
    two_hop_rows = [
        _two_hop_row("luat-z_dieu-9", "luat-b_dieu-2", "luat-c_dieu-3"),
        _two_hop_row("luat-a_dieu-1", "luat-b_dieu-2", "luat-c_dieu-3"),
        _two_hop_row("luat-m_dieu-5", "luat-b_dieu-2", "luat-c_dieu-3"),
    ]
    one_hop_rows = [
        _one_hop_row("luat-z_dieu-9", "luat-y_dieu-2"),
        _one_hop_row("luat-a_dieu-1", "luat-y_dieu-2"),
    ]

    client1 = _make_mock_client(two_hop_rows=list(two_hop_rows), one_hop_rows=list(one_hop_rows))
    result1 = build_multihop_eval_set(client1, min_content_length=DEFAULT_MIN_CONTENT_LENGTH)

    client2 = _make_mock_client(two_hop_rows=list(two_hop_rows), one_hop_rows=list(one_hop_rows))
    result2 = build_multihop_eval_set(client2, min_content_length=DEFAULT_MIN_CONTENT_LENGTH)

    assert result1 == result2

    # Sap xep theo tuple(article_ids) - "luat-a" truoc "luat-m" truoc "luat-z".
    two_hop_first_ids = [c["article_ids"][0] for c in result1["two_hop_candidates"]]
    assert two_hop_first_ids == sorted(two_hop_first_ids)
    one_hop_first_ids = [c["article_ids"][0] for c in result1["one_hop_candidates"]]
    assert one_hop_first_ids == sorted(one_hop_first_ids)


# --- Extra: A == C (vong lap trich dan) KHONG bi loc bo ---------------------


def test_reference_cycle_a_to_b_to_a_is_not_filtered_out():
    client = _make_mock_client(
        two_hop_rows=[_two_hop_row("luat-a_dieu-1", "luat-b_dieu-2", "luat-a_dieu-1")]
    )

    result = build_multihop_eval_set(client, min_content_length=DEFAULT_MIN_CONTENT_LENGTH)

    assert len(result["two_hop_candidates"]) == 1
    candidate = result["two_hop_candidates"][0]
    assert candidate["article_ids"] == ["luat-a_dieu-1", "luat-b_dieu-2", "luat-a_dieu-1"]
    assert len(candidate["articles"]) == 3


# --- Extra: --limit cat rieng biet cho MOI tap ------------------------------


def test_limit_applies_independently_per_pool():
    two_hop_rows = [
        _two_hop_row(f"luat-{i:02d}_dieu-1", "luat-b_dieu-2", "luat-c_dieu-3")
        for i in range(5)
    ]
    client = _make_mock_client(two_hop_rows=two_hop_rows)

    result = build_multihop_eval_set(client, min_content_length=DEFAULT_MIN_CONTENT_LENGTH, limit=3)

    assert len(result["two_hop_candidates"]) == 3
    assert result["limit_per_pool"] == 3
