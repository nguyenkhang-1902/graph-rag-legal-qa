"""bench_bm25_backends.py: so sanh HAI backend BM25 tren corpus that, de
quyet dinh dung cai nao cho baseline Hybrid+Reranker o quy mo 67k (T018).

=== VI SAO CAN SCRIPT NAY ===
Project truoc (`rag-chatbot-document-QA`) dung `rank_bm25.BM25Okapi` va TU
GHI NHAN han che trong README: "BM25 dung `rank_bm25` (linear scan, khong co
inverted index) - chi phi lookup tang nhanh hon tuyen tinh theo quy mo corpus
(do duoc: corpus tang 4.86x, lookup tang 8.6x). Can doi backend neu scale
vuot 10k van ban." Corpus o day la 61k = ~6x cua 10k.

`bm25s` la backend thay the: tinh san diem so luc index vao MA TRAN THUA
(scipy CSR) - thuc chat mot inverted index - nen chi phi truy van ti le voi
SO TAI LIEU CHUA TU KHOA, khong phai voi kich thuoc corpus.

=== BA CAU HOI SCRIPT NAY TRA LOI (trong MOT lan chay) ===
  1. `rank_bm25` cham co mot o 61k? (thoi gian index + thoi gian/truy van)
  2. `bm25s` nhanh hon bao nhieu lan?
  3. QUAN TRONG NHAT: hai backend co xep hang GIONG NHAU khong?

Cau 3 la ly do KHONG duoc mac dinh "cung la BM25 nen giong nhau": BM25 co
nhieu bien the IDF (robertson / lucene / atire / bm25l / bm25+) khac nhau o
cach xu ly tu qua pho bien. `rank_bm25.BM25Okapi` dung bien the Robertson
kem `epsilon` chan IDF am; `bm25s` mac dinh dung bien the khac. Doi backend
CO THE lam lech thu hang du cung mang ten "BM25" - phai DO, khong duoc doan
(Quy tac rieng #3 constitution: "khong nhan xet dinh tinh ma khong co con
so").

=== VI SAO CHAY TUAN TU, KHONG CHAY SONG SONG ===
Ca hai backend deu CPU-bound. Chay dong thoi thi chung tranh loi CPU va CA
HAI deu cham di, khong deu nhau -> so do vo nghia (dung bai hoc DOT 5: benchmark
32 vs 64 "khong hoan toan cong bang vi cua so lay mau khac nhau"). Script nay
chay tung backend MOT, tren CUNG corpus va CUNG bo cau hoi.

=== TOKENIZE PHAI GIONG HET PROJECT TRUOC ===
`tokenize()` duoi day sao chep nguyen tu `D:/RAG Chatbot/app/hybrid_retriever.py`
(constitution cho phep "chi tham chieu doc, vd copy script benchmark"). Bo dau
tieng Viet CA HAI PHIA (corpus luc index + query luc tim) chinh la fix da dua
Recall@4 tu 61.1% -> 100% o project truoc. Tokenize lech thi moi so lieu so
sanh voi baseline cu deu vo nghia.

CACH DUNG:
    python -m scripts.bench_bm25_backends data/raw
    python -m scripts.bench_bm25_backends data/raw --limit-docs 5000 --limit-queries 50
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

GOLD_SET_PATH = Path(__file__).parent / "quality_fixtures" / "gold_set_zalo.json"

# k = 4 de khop truc tiep voi bang "Recall@4" trong README project truoc.
DEFAULT_K = 4


def _strip_diacritics(text: str) -> str:
    """Bo dau tieng Viet. "d"/"D" xu ly rieng vi NFD KHONG tach duoc no
    (la ky tu goc rieng U+0111, khong phai "d" + dau ket hop).

    Sao chep nguyen tu project truoc - xem module docstring."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def tokenize(text: str) -> list[str]:
    """Bo dau + lowercase + tach theo tu (\\w+, Unicode-aware)."""
    return _TOKEN_RE.findall(_strip_diacritics(text.lower()))


def topk_agreement(
    ranked_a: list[list[str]], ranked_b: list[list[str]], k: int
) -> float:
    """Ty le TRUNG KHOP TAP top-k giua hai backend, trung binh tren cac cau
    hoi. 1.0 = hai backend luon tra ve cung mot tap k tai lieu.

    Do "cung TAP hay khong", KHONG phat khac thu tu ben trong top-k - vi
    Recall@k cung khong quan tam thu tu (MRR moi quan tam). Dung mot metric
    cho ca hai muc dich se lam mo ket luan.

    Tra ve 0.0 khi khong co cau hoi nao (khong chia cho 0)."""
    if not ranked_a or not ranked_b:
        return 0.0
    scores = []
    for a, b in zip(ranked_a, ranked_b):
        set_a, set_b = set(a[:k]), set(b[:k])
        denom = max(len(set_a), len(set_b))
        scores.append(len(set_a & set_b) / denom if denom else 0.0)
    return sum(scores) / len(scores)


def recall_and_mrr(
    retrieved: list[list[str]], expected: list[str], k: int
) -> tuple[float, float]:
    """Recall@k va MRR theo CUNG dinh nghia voi `eval_zalo_recall.py` cua
    project truoc: moi cau hoi co DUNG MOT dap an.

    Khac han `scripts/eval_graph_recall.py` (T017) - bo 32 cau multi-hop co
    NHIEU `expected_article_ids`/cau nen phai dung strict/lenient recall
    rieng. O day dung dinh nghia don gian de so sanh duoc voi so lieu cu.

    `retrieved[i]` la danh sach id xep hang cho cau hoi i; `expected[i]` la
    id dap an duy nhat. Lech do dai = loi lap trinh (ghep sai cau hoi voi
    dap an) -> raise, khong am tham tinh sai."""
    if len(retrieved) != len(expected):
        raise ValueError(
            f"so cau hoi khong khop: retrieved={len(retrieved)} nhung "
            f"expected={len(expected)}"
        )
    if not retrieved:
        return 0.0, 0.0

    hits = 0
    rr_total = 0.0
    for ranked, want in zip(retrieved, expected):
        topk = ranked[:k]
        if want in topk:
            hits += 1
            rr_total += 1.0 / (topk.index(want) + 1)
    n = len(retrieved)
    return hits / n, rr_total / n


def load_corpus(data_dir: str | Path, limit: int | None = None):
    """(article_ids, texts) tu `data/raw`. Tai dung `discover_documents` +
    `parse_file` cua `app/ingest.py` (Dieu 1) de corpus BM25 KHOP CHINH XAC
    voi corpus dense da nam trong Chroma - neu hai ben lech nhau thi Hybrid
    (RRF gop hai nhanh) khong con y nghia."""
    from app.ingest import discover_documents, parse_file

    ids: list[str] = []
    texts: list[str] = []
    for path in discover_documents(data_dir, limit=limit):
        try:
            _raw, parsed = parse_file(path)
        except Exception:
            logger.warning("bo qua file khong parse duoc: %s", path)
            continue
        article = parsed.articles[0]
        ids.append(article.article_id)
        texts.append(article.full_text)
    return ids, texts


def filter_gold_to_indexed_corpus(
    questions: list[str], expected: list[str], indexed_ids: set[str]
) -> tuple[list[str], list[str]]:
    """Giu lai cac cau hoi co dap an NAM TRONG corpus da index.

    Bat buoc khi chay voi `--limit-docs`: subset lay N file DAU theo thu tu
    ten, nen hau het dap an cua gold set khong nam trong do -> Recall@k do
    duoc se la 0% va KHONG noi len dieu gi ve chat luong backend (smoke test
    dau tien da dinh dung bay nay). Loc truoc thi con so do duoc lai co
    nghia tren dung phan corpus dang xet.

    Khi chay full (khong `--limit-docs`) thi ham nay khong loai cau nao -
    da kiem that: 793/793 dap an deu co trong corpus 61k."""
    kept_q: list[str] = []
    kept_e: list[str] = []
    for q, e in zip(questions, expected):
        if e in indexed_ids:
            kept_q.append(q)
            kept_e.append(e)
    return kept_q, kept_e


def load_gold(limit: int | None = None):
    """(questions, expected_article_ids) tu gold set Zalo - CUNG bo cau hoi
    project truoc da dung, nen so sanh duoc truc tiep.

    `expected_source_file` ("100_2019_nđ-cp_6.md") duoc doi sang article_id
    ("100-2019-nd-cp_dieu-6") bang DUNG logic cua `app/ingest.py` - da kiem
    that: 793/793 cau (100%) map duoc sang article_id co that trong corpus
    61k."""
    from app.extraction.slugify import slugify_doc_name

    gold = json.loads(GOLD_SET_PATH.read_text(encoding="utf-8"))["gold_set"]
    if limit is not None:
        gold = gold[:limit]

    stem_re = re.compile(r"^(.+)_(\d+)$")
    questions: list[str] = []
    expected: list[str] = []
    for item in gold:
        match = stem_re.match(Path(item["expected_source_file"]).stem)
        if not match:
            logger.warning("bo qua gold item ten file la: %s", item["expected_source_file"])
            continue
        questions.append(item["question"])
        expected.append(
            f"{slugify_doc_name(match.group(1))}_dieu-{int(match.group(2))}"
        )
    return questions, expected


def run_rank_bm25(corpus_tokens, ids, queries, k):
    """Backend cua project truoc: `rank_bm25.BM25Okapi`, tham so MAC DINH
    (giong het `app/hybrid_retriever.py` dong 112 - khong chinh k1/b/epsilon,
    de trung thanh voi so lieu cu)."""
    import numpy as np
    from rank_bm25 import BM25Okapi

    t0 = time.monotonic()
    bm25 = BM25Okapi(corpus_tokens)
    index_s = time.monotonic() - t0

    t0 = time.monotonic()
    ranked: list[list[str]] = []
    for q in queries:
        scores = bm25.get_scores(tokenize(q))
        top = np.argsort(scores)[::-1][:k]
        ranked.append([ids[i] for i in top])
    query_s = time.monotonic() - t0
    return ranked, index_s, query_s


def run_bm25s(corpus_tokens, ids, queries, k, method: str):
    """Backend thay the: `bm25s`, inverted index (ma tran thua CSR).

    `method` PHAI truyen tuong minh - mac dinh cua thu vien KHAC bien the ma
    `rank_bm25.BM25Okapi` dung, va do chinh la thu script nay di do."""
    import bm25s

    # show_progress=False: bm25s in progress bar cho MOI lan index/retrieve,
    # voi hang tram truy van thi log ngap hoan toan (da thay o smoke test).
    t0 = time.monotonic()
    retriever = bm25s.BM25(method=method)
    retriever.index(corpus_tokens, show_progress=False)
    index_s = time.monotonic() - t0

    t0 = time.monotonic()
    ranked: list[list[str]] = []
    for q in queries:
        idx, _scores = retriever.retrieve([tokenize(q)], k=k, show_progress=False)
        ranked.append([ids[i] for i in idx[0]])
    query_s = time.monotonic() - t0
    return ranked, index_s, query_s


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "So sanh rank_bm25 vs bm25s tren corpus that: toc do VA muc do "
            "trung khop thu hang. Chay TUAN TU (khong song song) de so do "
            "khong bi nhieu do tranh CPU."
        )
    )
    parser.add_argument("data_dir", type=str, help="Thu muc .md (vd data/raw).")
    parser.add_argument("--limit-docs", type=int, default=None,
                        help="Chi index N file dau - smoke test truoc khi chay full 61k.")
    parser.add_argument("--limit-queries", type=int, default=50,
                        help="So cau hoi gold set dung de do (mac dinh 50).")
    parser.add_argument("-k", type=int, default=DEFAULT_K,
                        help=f"top-k (mac dinh {DEFAULT_K}, khop bang Recall@4 cua project truoc).")
    parser.add_argument(
        "--bm25s-methods",
        type=str,
        default="robertson,lucene",
        help=(
            "Danh sach bien the IDF cua bm25s, cach nhau bang dau phay. Thu "
            "NHIEU bien the trong MOT lan chay vi doc corpus 61k mat ~6 phut - "
            "chay lai cho tung bien the la tra gia gap doi cho phan khong doi. "
            "'robertson' duoc ky vong gan nhat rank_bm25.BM25Okapi; 'lucene' la "
            "mac dinh cua bm25s. Cac lua chon khac: atire, bm25l, bm25+."
        ),
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_arg_parser().parse_args()

    logger.info("doc corpus...")
    t0 = time.monotonic()
    ids, texts = load_corpus(args.data_dir, limit=args.limit_docs)
    logger.info("  %d tai lieu trong %.1fs", len(ids), time.monotonic() - t0)

    logger.info("tokenize corpus...")
    t0 = time.monotonic()
    corpus_tokens = [tokenize(t) for t in texts]
    tok_s = time.monotonic() - t0
    ntok = sum(len(t) for t in corpus_tokens)
    logger.info("  %d token trong %.1fs (dung CHUNG cho ca 2 backend)", ntok, tok_s)

    # Lay du roi loc theo corpus da index, moi cat xuong --limit-queries:
    # neu cat truoc khi loc thi voi --limit-docs se con rat it (hoac 0) cau.
    all_q, all_e = load_gold()
    questions, expected = filter_gold_to_indexed_corpus(all_q, all_e, set(ids))
    if len(questions) < len(all_q):
        logger.warning(
            "chi %d/%d cau gold co dap an nam trong corpus da index (do "
            "--limit-docs) - da loc bo phan con lai, neu khong Recall@k do "
            "duoc se la 0%% va vo nghia",
            len(questions),
            len(all_q),
        )
    if args.limit_queries is not None:
        questions = questions[: args.limit_queries]
        expected = expected[: args.limit_queries]
    if not questions:
        raise SystemExit(
            "Khong con cau hoi nao sau khi loc - subset corpus qua nho hoac "
            "khong chua dap an nao. Tang --limit-docs hoac chay full."
        )
    logger.info("%d cau hoi gold set Zalo (sau khi loc)", len(questions))

    nq = len(questions)
    methods = [m.strip() for m in args.bm25s_methods.split(",") if m.strip()]

    logger.info("--- backend: rank_bm25 (giong project truoc) ---")
    ranked_rank, idx_rank, qry_rank = run_rank_bm25(corpus_tokens, ids, questions, args.k)
    r_rank, m_rank = recall_and_mrr(ranked_rank, expected, args.k)

    # (nhan, thoi gian index, thoi gian truy van, recall, mrr, trung khop)
    rows = [("rank_bm25", idx_rank, qry_rank, r_rank, m_rank, 1.0)]
    for i, method in enumerate(methods, 1):
        logger.info("--- backend: bm25s method=%s (%d/%d) ---", method, i, len(methods))
        ranked_s, idx_s, qry_s = run_bm25s(
            corpus_tokens, ids, questions, args.k, method
        )
        r_s, m_s = recall_and_mrr(ranked_s, expected, args.k)
        rows.append((
            f"bm25s:{method}", idx_s, qry_s, r_s, m_s,
            topk_agreement(ranked_rank, ranked_s, args.k),
        ))

    # Chi bao ty le tang toc khi CA HAI phep do du lon de dang tin. Duoi
    # nguong nay, do phan giai dong ho lam ty le vo nghia (smoke test dau
    # tien in ra "nhanh hon 157,000,000 lan" vi chia cho ~0).
    _MIN_MEASURABLE_S = 0.5

    print()
    print(f"corpus: {len(ids):,} tai lieu | {nq} cau hoi gold | k={args.k}")
    print()
    head = (f"{'backend':<18}{'index(s)':>10}{'truyvan(s)':>12}{'ms/truyvan':>12}"
            f"{'Recall@'+str(args.k):>12}{'MRR':>8}{'khop rank_bm25':>17}"
            f"{'tang toc':>20}")
    print(head)
    print("-" * len(head))
    for label, idx_s, qry_s, rec, mrr, agree in rows:
        if label == "rank_bm25":
            speed = "1.0x (goc)"
        elif qry_rank >= _MIN_MEASURABLE_S and qry_s >= _MIN_MEASURABLE_S:
            speed = f"{qry_rank / qry_s:.0f}x"
        else:
            speed = "(qua nhanh de do)"
        khop = "-" if label == "rank_bm25" else f"{agree:.1%}"
        print(f"{label:<18}{idx_s:>10.1f}{qry_s:>12.1f}{qry_s/max(nq,1)*1000:>12.1f}"
              f"{rec:>11.1%}{mrr:>8.3f}{khop:>17}{speed:>20}")

    print()
    best = max(
        (r for r in rows if r[0] != "rank_bm25"), key=lambda r: r[5], default=None
    )
    if best is not None:
        if best[5] >= 0.999:
            print(
                f"KET LUAN: {best[0]} xep hang GIONG HET rank_bm25 ({best[5]:.1%}) "
                "-> dung duoc thay the, so lieu VAN so sanh truc tiep duoc voi "
                "Recall@4 cu cua project truoc."
            )
        else:
            print(
                f"KET LUAN: bien the bam sat nhat la {best[0]} nhung chi khop "
                f"{best[5]:.1%} thu hang voi rank_bm25 -> KHONG phai thay the "
                "trong suot. Neu dung bm25s cho baseline thi PHAI ghi ro trong "
                "bang ket qua rang so lieu khong so truc tiep duoc voi Recall@4 "
                "cu (khac ca backend LAN quy mo corpus)."
            )
    print(
        f"\nLuu y: day chi la tang BM25. Baseline Hybrid+Reranker con them dense "
        f"(da co san 60,568 embedding) + cross-encoder rerank (phan dat nhat, "
        f"chi phi GIONG NHAU du chon backend nao)."
    )


if __name__ == "__main__":
    main()
