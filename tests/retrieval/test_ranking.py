"""Tests cho app/retrieval/ranking.py (T028 buoc 3/3).

TDD (constitution Dieu 2): file nay duoc viet TRUOC khi module ton tai.

=== VI SAO CAN MODULE NAY ===
Sau khi them vector cap Khoan (T028 buoc 2), so ung vien trung binh tang tu
6.0 -> 17.1 Article/cau hoi. Do that tren 793 cau Zalo gold, recall BAO HOA o
muc cat = 10:
    k       4      6      8     10     12     15     20
    Recall 71.1%  74.0%  75.2%  75.4%  75.4%  75.4%  75.4%
Nen cat o 10 KHONG MAT GI ma giam 41% luong ngu canh dua cho LLM.

Nhung muon cat co nghia thi phai co THU TU. Hai van de da co san:
  1. `TraversalResult.visited_article_ids` la mot SET - khong co thu tu nao.
  2. `api._build_prompt` sap ngu canh bang `sorted(contexts)` - tuc thu tu
     CHU CAI cua article_id, khong lien quan gi den do lien quan. Neu cat 10
     tu do se giu 10 Dieu TUY Y.

Logic xep hang dung DA TON TAI nhung nam trong `scripts/eval_graph_recall.py`
(private `_ranked_retrieved_article_ids`). App KHONG duoc phu thuoc scripts,
nen dua ve day de ca `serving/api.py` LAN script eval dung CUNG mot nguon
(Dieu 1 - khong hai ban sao lech nhau).

THU TU: entry point truoc (theo similarity giam dan - `find_entry_points` da
sap san), roi Article tim them qua traversal REFERENCES theo thu tu LAN DAU
xuat hien trong `edges`. Canh DEFINES bi bo qua - no tro toi `Term`, khong
phai Article.
"""
from app.retrieval.ranking import rank_article_ids


class _Edge:
    def __init__(self, from_article_id, to_id, relationship_type):
        self.from_article_id = from_article_id
        self.to_id = to_id
        self.relationship_type = relationship_type


class _Result:
    def __init__(self, edges):
        self.edges = edges


def test_entry_points_come_first_in_given_order():
    # `find_entry_points` da sap theo similarity giam dan - PHAI giu nguyen
    # thu tu do, khong sap lai.
    out = rank_article_ids(["a", "b", "c"], _Result([]))
    assert out == ["a", "b", "c"]


def test_traversal_articles_appended_after_entry_points():
    edges = [_Edge("a", "x", "REFERENCES"), _Edge("x", "y", "REFERENCES")]
    out = rank_article_ids(["a"], _Result(edges))
    assert out == ["a", "x", "y"]


def test_defines_edges_are_ignored_because_they_point_to_terms():
    # DEFINES tro toi `Term`, khong phai Article - dua term_id vao danh sach
    # Article se lam cac buoc sau (get_texts / citation path) tim khong thay.
    edges = [_Edge("a", "thuat-ngu-nao-do", "DEFINES")]
    out = rank_article_ids(["a"], _Result(edges))
    assert out == ["a"]


def test_duplicates_are_removed_keeping_first_position():
    edges = [_Edge("a", "b", "REFERENCES"), _Edge("b", "a", "REFERENCES")]
    out = rank_article_ids(["a"], _Result(edges))
    assert out == ["a", "b"]  # "a" khong xuat hien lai o cuoi


def test_traversal_order_follows_first_appearance_in_edges():
    edges = [
        _Edge("a", "z", "REFERENCES"),
        _Edge("a", "m", "REFERENCES"),
        _Edge("z", "m", "REFERENCES"),  # "m" da thay -> khong day xuong cuoi
    ]
    out = rank_article_ids(["a"], _Result(edges))
    assert out == ["a", "z", "m"]


def test_limit_truncates_to_first_n():
    edges = [_Edge("a", f"t{i}", "REFERENCES") for i in range(10)]
    out = rank_article_ids(["a"], _Result(edges), limit=4)
    assert out == ["a", "t0", "t1", "t2"]


def test_limit_none_returns_everything():
    edges = [_Edge("a", f"t{i}", "REFERENCES") for i in range(3)]
    out = rank_article_ids(["a"], _Result(edges), limit=None)
    assert len(out) == 4


def test_limit_larger_than_available_is_harmless():
    out = rank_article_ids(["a"], _Result([]), limit=99)
    assert out == ["a"]


def test_limit_never_drops_entry_points_below_it():
    # Uu tien: entry point (dense, co diem similarity that) QUAN TRONG HON
    # Article tim qua traversal. Cat phai giu entry point truoc.
    edges = [_Edge("a", "t1", "REFERENCES")]
    out = rank_article_ids(["a", "b", "c"], _Result(edges), limit=2)
    assert out == ["a", "b"]


def test_empty_input_returns_empty():
    assert rank_article_ids([], _Result([])) == []
