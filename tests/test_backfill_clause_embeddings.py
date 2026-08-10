"""Tests cho scripts/backfill_clause_embeddings.py (T028 buoc 2/2).

TDD (constitution Dieu 2): file nay duoc viet TRUOC khi script ton tai.

BOI CANH: buoc 1/2 (`find_entry_points` gop vector Khoan ve article_id) da
xong va da verify khong hoi quy. Script nay them vector cap Khoan vao Chroma
de buoc gop do co gi ma gop.

CHI embed Khoan cua Dieu DAI co >=2 Khoan - khong embed het 165,393 Khoan:
  - Dieu NGAN da co similarity tot (nhom ngan nhat chi fail 15%), them vector
    Khoan cho chung la ton GPU ma khong giai quyet van de gi.
  - Dieu chi co 1 Khoan thi vector Khoan gan nhu trung voi vector ca Dieu.
Do that tu data/raw: 6,278 Dieu dai, trong do 5,494 co >=2 Khoan = 36,585
Khoan can embed (~55 phut GPU), thay vi 165,393 (~4 gio).
"""
import pytest

from scripts.backfill_clause_embeddings import (
    clause_vector_id,
    select_clauses_to_embed,
)


class _FakeClause:
    def __init__(self, so_khoan, noi_dung):
        self.so_khoan = so_khoan
        self.noi_dung = noi_dung


class _FakeArticle:
    def __init__(self, article_id, full_text, clauses):
        self.article_id = article_id
        self.full_text = full_text
        self.clauses = clauses


# --- clause_vector_id ----------------------------------------------------
# PHAI khop dinh dang ma `find_entry_points._article_id_of` tach nguoc lai,
# neu khong thi vector Khoan se khong bao gio gop duoc ve Dieu cha.


def test_clause_vector_id_format():
    assert clause_vector_id("luat-a_dieu-5", 3) == "luat-a_dieu-5#khoan-3"


def test_clause_vector_id_round_trips_with_entry_point_parser():
    # Rang buoc QUAN TRONG NHAT: hai module phai dong y ve dinh dang id.
    from app.retrieval.entry_point import _article_id_of

    vid = clause_vector_id("19-2016-tt-bxd_dieu-12", 7)
    assert _article_id_of(vid) == "19-2016-tt-bxd_dieu-12"


# --- select_clauses_to_embed --------------------------------------------


def _long(n=3000):
    return "x" * n


def test_selects_clauses_of_long_article_with_multiple_clauses():
    art = _FakeArticle("a_dieu-1", _long(), [_FakeClause(1, "noi dung 1"),
                                             _FakeClause(2, "noi dung 2")])
    rows = select_clauses_to_embed([art], already_embedded=set())
    assert [r[0] for r in rows] == ["a_dieu-1#khoan-1", "a_dieu-1#khoan-2"]
    assert [r[1] for r in rows] == ["noi dung 1", "noi dung 2"]


def test_skips_short_article_even_if_it_has_clauses():
    # Dieu ngan da co similarity tot (fail 15%) - them vector Khoan cho chung
    # chi ton GPU.
    art = _FakeArticle("a_dieu-1", "ngan", [_FakeClause(1, "x"), _FakeClause(2, "y")])
    assert select_clauses_to_embed([art], already_embedded=set()) == []


def test_skips_long_article_with_only_one_clause():
    # 1 Khoan -> vector Khoan gan nhu trung voi vector ca Dieu, khong them
    # thong tin gi.
    art = _FakeArticle("a_dieu-1", _long(), [_FakeClause(1, "chi mot khoan")])
    assert select_clauses_to_embed([art], already_embedded=set()) == []


def test_skips_long_article_with_no_clauses():
    art = _FakeArticle("a_dieu-1", _long(), [])
    assert select_clauses_to_embed([art], already_embedded=set()) == []


def test_skips_clause_with_empty_content():
    # Khong embed chuoi rong - vector vo nghia va lam nhieu ket qua.
    art = _FakeArticle("a_dieu-1", _long(), [_FakeClause(1, "   "),
                                             _FakeClause(2, "co noi dung")])
    rows = select_clauses_to_embed([art], already_embedded=set())
    assert [r[0] for r in rows] == ["a_dieu-1#khoan-2"]


def test_resumable_skips_already_embedded_clause_ids():
    # Resume: bo qua id DA co trong Chroma (giong backfill_embeddings.py bo qua
    # Article da co chroma_id) - chay lai lenh y nguyen phai tiep tuc duoc.
    art = _FakeArticle("a_dieu-1", _long(), [_FakeClause(1, "mot"),
                                             _FakeClause(2, "hai")])
    rows = select_clauses_to_embed([art], already_embedded={"a_dieu-1#khoan-1"})
    assert [r[0] for r in rows] == ["a_dieu-1#khoan-2"]


def test_empty_article_list_returns_empty():
    assert select_clauses_to_embed([], already_embedded=set()) == []


def test_long_threshold_matches_measured_p90():
    # Nguong "dai" = 2700 ky tu, lay theo p90 do that o DOT 5 (p90=2,751) va
    # dung lam moc phan nhom trong phan tich tu phan vi o DOT 16. Ghim lai de
    # khong ai doi thanh so tuy y ma khong doc lai so lieu.
    from scripts.backfill_clause_embeddings import LONG_ARTICLE_CHARS

    assert LONG_ARTICLE_CHARS == 2700


def test_duplicate_so_khoan_within_one_article_still_yields_unique_ids():
    # BUG CO SAN, do duoc (2026-08-08): parser coi moi dong "N. " o cot 0 la
    # Khoan moi, nen Dieu SUA DOI (trich lai nguyen van Dieu khac) co so_khoan
    # lap lai: [1, 1, 2, 2, 17, 18, 3, 4, ...]. Do that: 335/60,568 Article
    # (0.6%) bi trung, 4,149 Clause (2.4%) bi GOP MAT am tham trong Neo4j vi
    # `clause_id = f"{article_id}_khoan-{so_khoan}"` trung nhau va upsert dung
    # MERGE. Nang nhat: 12-2017-qh14_dieu-1 mat 341 Khoan.
    #
    # Script nay dung VI TRI (1-based) chu khong dung so_khoan -> duy nhat theo
    # cau truc. Neu dung so_khoan, Chroma raise DuplicateIDError (da xay ra
    # that o smoke test dau tien).
    art = _FakeArticle(
        "a_dieu-1", _long(),
        [_FakeClause(1, "lan mot"), _FakeClause(1, "lan hai"),
         _FakeClause(2, "khoan hai")],
    )
    rows = select_clauses_to_embed([art], already_embedded=set())
    ids = [r[0] for r in rows]
    assert len(ids) == len(set(ids)), f"id bi trung: {ids}"
    assert ids == ["a_dieu-1#khoan-1", "a_dieu-1#khoan-2", "a_dieu-1#khoan-3"]
    # Noi dung phai giu dung thu tu goc (khong mat Khoan nao).
    assert [r[1] for r in rows] == ["lan mot", "lan hai", "khoan hai"]
