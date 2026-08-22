"""Tests cho scripts/eval_bhxh_retrieval.py (P2-T3) - logic cham diem + schema
bo eval. KHONG chay retrieval that (khong Neo4j/Chroma)."""
import json
from pathlib import Path

from scripts.eval_bhxh_retrieval import _score

EVAL_PATH = Path("data/eval/bhxh_eval_set.json")


def test_score_gold_at_rank_1_is_hit5_hit10_rr1():
    hit5, hit10, rr = _score(["g", "x", "y"], ["g"])
    assert hit5 is True and hit10 is True and rr == 1.0


def test_score_gold_at_rank_7_is_hit10_not_hit5():
    ranked = [f"x{i}" for i in range(6)] + ["g"]  # gold o vi tri 7
    hit5, hit10, rr = _score(ranked, ["g"])
    assert hit5 is False and hit10 is True
    assert rr == 1.0 / 7


def test_score_no_gold_in_top10_is_miss():
    hit5, hit10, rr = _score(["a", "b", "c"], ["g"])
    assert hit5 is False and hit10 is False and rr == 0.0


def test_score_any_of_multiple_gold_counts():
    # 2 gold, cai thu hai xuat hien o rank 2 -> hit.
    hit5, hit10, rr = _score(["x", "g2"], ["g1", "g2"])
    assert hit5 is True and rr == 0.5


def test_eval_set_schema_valid_and_nonempty():
    data = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    qs = data["questions"]
    assert len(qs) >= 10
    for q in qs:
        assert q["question"].strip()
        assert isinstance(q["gold_article_ids"], list) and q["gold_article_ids"]
        assert all("_dieu-" in g for g in q["gold_article_ids"])
