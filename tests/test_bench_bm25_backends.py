"""Tests cho scripts/bench_bm25_backends.py (chuan bi T018).

TDD (constitution Dieu 2): file nay duoc viet TRUOC khi script ton tai.

MUC DICH CUA SCRIPT: tra loi BA cau hoi trong MOT lan chay, de quyet dinh
dung backend BM25 nao cho baseline Hybrid+Reranker o quy mo 67k:
  1. `rank_bm25` (giong het project truoc) cham co mot?
  2. `bm25s` (inverted index) nhanh hon bao nhieu lan?
  3. QUAN TRONG NHAT - hai backend co xep hang GIONG NHAU khong?

Cau 3 la ly do khong duoc mac dinh "cung la BM25 nen giong nhau": BM25 co
nhieu bien the IDF (robertson/lucene/atire/bm25l/bm25+), `rank_bm25.
BM25Okapi` dung bien the Robertson (kem epsilon chan IDF am) con `bm25s`
mac dinh dung bien the khac. Doi backend co the lam lech thu hang du cung
mang ten "BM25" - phai DO, khong duoc doan (Quy tac rieng #3).

Cac test o day chi kiem phan LOGIC THUAN (tokenize, metric) - khong dung
toi corpus 61k that (ton RAM/CPU, thuoc ve lan chay that).
"""
import pytest

from scripts.bench_bm25_backends import (
    recall_and_mrr,
    tokenize,
    topk_agreement,
)


# --- tokenize: PHAI giong het project truoc ------------------------------
# Sao chep nguyen tu `D:/RAG Chatbot/app/hybrid_retriever.py` (constitution
# cho phep "chi tham chieu doc, vd copy script benchmark"). Neu tokenize
# lech, moi so lieu so sanh voi baseline cu deu vo nghia.


def test_tokenize_strips_vietnamese_diacritics():
    # Chinh fix da dua Recall@4 tu 61.1% -> 100% o project truoc: cau hoi
    # nguoi dung thuong go KHONG dau trong khi van ban goc co dau day du.
    assert tokenize("Thời gian làm thêm giờ") == ["thoi", "gian", "lam", "them", "gio"]


def test_tokenize_handles_dj_separately_from_nfd():
    # "đ" (U+0111) la chu cai goc rieng, NFD KHONG tach duoc thanh "d" + dau
    # - phai .replace() truoc khi NFD strip cac dau con lai.
    assert tokenize("Nghị định") == ["nghi", "dinh"]
    assert tokenize("ĐIỀU") == ["dieu"]


def test_tokenize_lowercases_and_splits_on_non_word():
    assert tokenize("Điều 5, khoản 2.") == ["dieu", "5", "khoan", "2"]


def test_tokenize_empty_text_returns_empty_list():
    assert tokenize("") == []


# --- topk_agreement: hai backend co xep hang giong nhau khong? -----------


def test_topk_agreement_identical_rankings_is_one():
    a = [["x", "y", "z"], ["p", "q", "r"]]
    assert topk_agreement(a, a, k=3) == 1.0


def test_topk_agreement_counts_overlap_not_order():
    # Do la "cung TAP top-k hay khong", khong phat khac thu tu trong top-k:
    # Recall@k cung khong quan tam thu tu (MRR moi quan tam) - dung mot
    # metric cho moi muc dich se lam mo ket luan.
    a = [["x", "y", "z"]]
    b = [["z", "y", "x"]]
    assert topk_agreement(a, b, k=3) == 1.0


def test_topk_agreement_partial_overlap():
    a = [["x", "y", "z", "w"]]
    b = [["x", "y", "q", "r"]]
    assert topk_agreement(a, b, k=4) == 0.5  # 2/4 trung


def test_topk_agreement_averages_across_queries():
    a = [["x", "y"], ["p", "q"]]
    b = [["x", "y"], ["p", "zz"]]
    assert topk_agreement(a, b, k=2) == 0.75  # (1.0 + 0.5) / 2


def test_topk_agreement_empty_input_is_zero_not_crash():
    assert topk_agreement([], [], k=4) == 0.0


# --- recall_and_mrr: CUNG dinh nghia voi eval_zalo_recall.py cua du an cu -
# Moi cau hoi Zalo gold set co DUNG MOT dap an (`expected_source_file`) -
# khac han bo 32 cau multi-hop (nhieu `expected_article_ids`, phai dung
# strict/lenient recall rieng - xem scripts/eval_graph_recall.py). O day
# dung dinh nghia don gian cua project truoc de so sanh duoc.


def test_recall_counts_hit_when_expected_in_topk():
    retrieved = [["a", "b", "c", "d"]]
    expected = ["c"]
    recall, mrr = recall_and_mrr(retrieved, expected, k=4)
    assert recall == 1.0
    assert mrr == pytest.approx(1 / 3)  # vi tri thu 3


def test_recall_misses_when_expected_outside_topk():
    retrieved = [["a", "b", "c", "d", "e"]]
    expected = ["e"]
    recall, mrr = recall_and_mrr(retrieved, expected, k=4)  # cat con 4
    assert recall == 0.0
    assert mrr == 0.0


def test_mrr_is_one_when_expected_is_first():
    recall, mrr = recall_and_mrr([["x", "y"]], ["x"], k=2)
    assert recall == 1.0
    assert mrr == 1.0


def test_recall_and_mrr_average_across_queries():
    retrieved = [["x", "y"], ["p", "q"]]
    expected = ["x", "zz"]
    recall, mrr = recall_and_mrr(retrieved, expected, k=2)
    assert recall == 0.5
    assert mrr == 0.5


def test_recall_and_mrr_empty_input_is_zero_not_crash():
    assert recall_and_mrr([], [], k=4) == (0.0, 0.0)


def test_recall_and_mrr_rejects_mismatched_lengths():
    # Lech do dai = loi lap trinh (ghep sai cau hoi voi dap an) -> phai
    # crash lon tieng chu khong am tham tinh sai.
    with pytest.raises(ValueError, match="khong khop"):
        recall_and_mrr([["x"], ["y"]], ["x"], k=1)


# --- filter_gold_to_indexed_corpus ---------------------------------------
# Bay THAT dinh phai o smoke test dau tien: chay voi --limit-docs 2000 (2000
# file DAU theo thu tu ten) nhung gold set hoi ve Dieu nam rai khap 61k ->
# Recall@4 do duoc la 0.0% cho CA HAI backend, khong noi len dieu gi ve chat
# luong backend. Phai loc cau hoi ve dung phan corpus dang xet.


def test_filter_keeps_only_questions_whose_answer_is_indexed():
    from scripts.bench_bm25_backends import filter_gold_to_indexed_corpus

    q, e = filter_gold_to_indexed_corpus(
        ["cau A", "cau B", "cau C"],
        ["co-that_dieu-1", "ngoai-subset_dieu-9", "co-that_dieu-2"],
        {"co-that_dieu-1", "co-that_dieu-2"},
    )
    assert q == ["cau A", "cau C"]
    assert e == ["co-that_dieu-1", "co-that_dieu-2"]


def test_filter_keeps_everything_when_full_corpus_indexed():
    from scripts.bench_bm25_backends import filter_gold_to_indexed_corpus

    q, e = filter_gold_to_indexed_corpus(
        ["a", "b"], ["x_dieu-1", "y_dieu-2"], {"x_dieu-1", "y_dieu-2", "z_dieu-3"}
    )
    assert (q, e) == (["a", "b"], ["x_dieu-1", "y_dieu-2"])


def test_filter_returns_empty_when_nothing_indexed():
    from scripts.bench_bm25_backends import filter_gold_to_indexed_corpus

    assert filter_gold_to_indexed_corpus(["a"], ["x_dieu-1"], set()) == ([], [])
