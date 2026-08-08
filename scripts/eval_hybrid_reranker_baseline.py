"""eval_hybrid_reranker_baseline.py (T018): tu do BASELINE Hybrid+Reranker
MOI o quy mo 67k, cho du an nay (huong G1-b da chot trong
CHECKLIST-GRAPHRAG-DUYET.md: "khong ep baseline cu chay o 67k, tu do
baseline moi trong du an nay va trinh bay la phat trien them").

Trach nhiem duy nhat cua module nay (constitution Dieu 5): dieu phoi eval
3 chien luoc (Dense-only / Hybrid RRF / Hybrid+Reranker) - tai su dung
`app.retrieval.embedder` (model + Chroma collection DA CO SAN cua du an
nay, KHONG tao lai), `scripts.bench_bm25_backends` (tokenize/load_corpus/
load_gold/recall_and_mrr - Dieu 1, khong duplicate logic da viet cho
T018-prep), va `bm25s` (backend da chot qua so sanh thuc te voi
rank_bm25 - xem TIEN_DO.md).

=== VI SAO CAN SCRIPT NAY (khac voi bench_bm25_backends.py) ===
bench_bm25_backends.py CHI do BM25 DUNG MOT MINH (khong dense, khong RRF,
khong reranker) - ton tai DE CHON THU VIEN BM25, khong dai dien cho
baseline cuoi cung. Recall@4 do duoc o do (55-58%) THAP HON NHIEU so voi
con so 97.7% cua project truoc VI project truoc do CA PIPELINE (BM25 +
dense qua RRF + cross-encoder rerank), khong phai BM25 rieng le - xem
TIEN_DO.md muc giai thich. Script nay dung lai DUNG tham so cua project
truoc (RRF_K=60, fetch_k=20, k=4, model reranker BAAI/bge-reranker-v2-m3)
de tao mot con so THAT SU so sanh duoc.

=== Article_id la ID CHUNG giua 2 nhanh (khac project truoc) ===
D:\\RAG Chatbot\\app\\hybrid_retriever.py can "content_hash" de noi ket
qua BM25 (tu dong tokenize rieng) voi ket qua Chroma (id noi bo rieng) vi
2 he thong do KHONG chia se dinh dang id. O day CA HAI nhanh deu dung
CHINH `article_id` (bm25 corpus xay tu `discover_documents`/`parse_file`
cua `app.ingest` - article_id lay tu ten file; Chroma cung dung
article_id lam id luc `scripts/backfill_embeddings.py` ghi vao) - khong
can lop id trung gian nao, RRF fusion o day chi lam viec truc tiep tren
article_id.

=== Reranker: sentence_transformers.CrossEncoder, khong qua langchain ===
Giong nguyen tac `app/serving/api.py` (goi HTTP Ollama truc tiep, khong
qua langchain) - constitution Dieu 1. Model BAAI/bge-reranker-v2-m3 DA
CACHE san tren may nay (dung chung HF cache voi D:\\RAG Chatbot, xac nhan
qua `huggingface_hub.scan_cache_dir()` truoc khi viet module nay) nen
`HF_HUB_OFFLINE=1` (dat trong app.retrieval.embedder luc import) khong
chan viec tai model.

CACH DUNG:
    python -m scripts.eval_hybrid_reranker_baseline data/raw
    python -m scripts.eval_hybrid_reranker_baseline data/raw --limit-docs 5000 --limit-queries 50
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# RRF_K/DEFAULT_FETCH_K/DEFAULT_K: dung Y HET gia tri
# D:\RAG Chatbot\app\hybrid_retriever.py + app/config.py (retriever_top_k=4,
# hybrid_fetch_k=20, RRF_K=60) - de so sanh duoc, khong tu chon lai.
RRF_K = 60
DEFAULT_FETCH_K = 20
DEFAULT_K = 4
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

# Model ho tro toi 8192 token nhung KHONG chan (max_length=None) - corpus
# co outlier that toi 252,967 ky tu va chi phi self-attention cua
# cross-encoder la O(n^2) theo do dai chuoi. Do that TRUC TIEP tren GPU
# nay (RTX 3050) bang 8 cap cung do dai: max_length=128 -> 0.53s,
# 512 -> 1.09s, 2048 -> 13.69s, KHONG gioi han (~8192 that su dung) ->
# 167.12s - xac nhan max_length CO duoc ton trong (khong phai tham so vo
# hieu), chi phi tang gan dung ty le binh phuong theo do dai (O(n^2)).
# Smoke test THAT voi 2048 (15 cau, 3000 file) van mat 997.6s (~66s/cau) -
# qua cham cho full 793 cau (~14.7h). Ha xuong 1024: theo ty le do duoc,
# chi phi con khoang 1/4 cua 2048 (uoc ~3.4s/8 cap o do dai toi da). Do
# that phan phoi token bang tokenizer CHINH model nay tren mau 200 file
# that: p50=245, p90=665, p99=2347 - 1024 van phu QUA p90 that (665), chi
# cat bot noi dung o duoi ~10% dai nhat (p90-p99). Danh doi co chu dich:
# uu tien chay het duoc full 793 cau/61k trong thoi gian hop ly hon la giu
# nguyen do dai toi da cho <10% candidate - ghi ro trong ket qua T018,
# KHONG kiem chung Recall thay doi bao nhieu khi cat o muc nay (chi 15 cau
# smoke test, chua du de ket luan).
_RERANKER_MAX_LENGTH = 1024

RESULT_PATH = Path(__file__).parent / "quality_fixtures" / "hybrid_reranker_baseline_result.json"

# Checkpoint/resume (them SAU khi lan chay full dau tien bi ngat giua
# chung boi tien trinh nen bi dung - xem TIEN_DO.md - mat toan bo tien do
# cua buoc Reranker, buoc TON THOI GIAN NHAT, ~3h o quy mo 793 cau). Sao
# chep dung pattern D:\RAG Chatbot\scripts\eval_zalo_recall.py (da tung
# giai quyet CHINH XAC van de nay - Dieu 1, khong tu nghi lai): ghi
# checkpoint sau moi CHECKPOINT_EVERY cau HOI VA khi xong moi chien luoc,
# chay lai CUNG lenh se tu resume tu cho dang do (bo qua chien luoc da
# xong, tiep tuc chien luoc dang do tu cau hoi ke tiep).
CHECKPOINT_PATH = Path(__file__).parent / "quality_fixtures" / "_hybrid_reranker_checkpoint.json"
CHECKPOINT_EVERY = 20


class QuestionCountMismatchError(RuntimeError):
    """Raise khi resume voi SO CAU HOI khac voi luc checkpoint duoc ghi.

    BUG THAT da xay ra (2026-08-08): checkpoint khong ghi so cau hoi. Lan
    chay dau do Dense-only + Hybrid tren 793 cau; lan resume sau chay voi
    `--limit-queries` mac dinh (luc do la 50) -> script BO QUA 2 chien luoc
    da xong (do o 793 cau) roi do chien luoc thu 3 o 50 cau, va IN CA BA
    CANH NHAU nhu the so sanh duoc:
        Dense-only          82.0%  (650/793)
        Hybrid RRF          79.2%  (628/793)
        Hybrid + Reranker   92.0%  ( 46/50)   <-- KHAC QUY MO
    92.0% tro thanh con so vo nghia trong bang so sanh - dung loai sai lech
    ma ca T018 dang co gang tranh.

    Day DUNG cung lop bug ma du an DA HOC va DA CHAN o `app/ingest.py`
    (`BatchSizeMismatchError`: checkpoint khong ghi `batch_size` -> resume
    voi batch size khac se am tham bo sot hang nghin van ban). Ap dung y
    nguyen nguyen tac do: PHAT HIEN va TU CHOI chay, KHONG tu dong hoa giai
    (constitution Dieu 1 - "tha crash con hon lam sai trong im lang").
    """


def _check_question_count_matches_checkpoint(
    checkpoint: dict, n_questions: int
) -> None:
    """So sanh so cau hoi cua lan chay nay voi so da ghi trong checkpoint.

    Chi kiem khi day THUC SU la mot lan resume (da co chien luoc xong hoac
    dang do). Checkpoint cu (ghi truoc khi truong `n_questions` ton tai)
    khong co truong nay -> khong the so sanh tu du lieu khong co, bo qua
    (giong cach ingest.py xu ly checkpoint cu thieu `batch_size`)."""
    is_resume = bool(checkpoint.get("completed")) or checkpoint.get("in_progress")
    if not is_resume:
        return
    recorded = checkpoint.get("n_questions")
    if recorded is None:
        return
    if recorded != n_questions:
        raise QuestionCountMismatchError(
            f"so cau hoi KHONG khop checkpoint: checkpoint duoc ghi voi "
            f"{recorded} cau, nhung lan chay nay dang dung {n_questions} cau. "
            "Ket qua cac chien luoc se duoc do o HAI QUY MO KHAC NHAU roi in "
            "canh nhau nhu the so sanh duoc - con so vo nghia. TU CHOI chay "
            f"tiep. Hay dung lai --limit-queries cho ra {recorded} cau, hoac "
            "chay lai tu dau bang --restart."
        )


def _load_checkpoint() -> dict:
    """Doc checkpoint, CHUAN HOA `in_progress` ve dang dict-theo-ten.

    Format CU: `in_progress` la MOT object `{"name": ..., "next_index": ...}` -
    chi giu duoc state cua DUY NHAT mot chien luoc. Do la nguyen nhan bug that
    2026-08-08 lam mat 720/793 cau da rerank: khi mot chien luoc KHAC ghi
    checkpoint, no de mat state cua chien luoc dang do dang.

    Format MOI: `in_progress` la dict `{ten_chien_luoc: state}` - moi chien
    luoc giu state RIENG, khong the de nhau. Ham nay doc duoc ca hai dang de
    khong pha vo checkpoint cu dang ton tai tren dia."""
    if not CHECKPOINT_PATH.is_file():
        return {"completed": {}, "in_progress": {}}
    data = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    ip = data.get("in_progress")
    if ip is None:
        data["in_progress"] = {}
    elif isinstance(ip, dict) and "name" in ip:
        # Format cu -> moi.
        data["in_progress"] = {ip["name"]: ip}
    return data


def _save_checkpoint(checkpoint: dict) -> None:
    tmp_path = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(CHECKPOINT_PATH)


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], rrf_k: int = RRF_K
) -> list[str]:
    """RRF chuan (Cormack et al. 2009): score(id) = tong qua moi danh sach
    cua 1/(rrf_k + rank), rank bat dau tu 1. Id chi xuat hien o MOT trong
    cac danh sach van duoc tinh diem (khong bi loai). Sao chep nguyen cong
    thuc tu D:\\RAG Chatbot\\app\\hybrid_retriever.py::reciprocal_rank_fusion
    (Dieu 1 - tham chieu doc project cu, khong sua no), rut gon tham so vi
    o day khong can bundle kem Document object (article_id da du de tra
    full text sau qua `embedder.get_texts`).

    Tra ve list article_id theo diem giam dan. `ranked_lists` rong hoac
    toan danh sach con rong -> tra ve list rong."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(scores, key=lambda doc_id: scores[doc_id], reverse=True)


def dense_search_topk(
    queries: list[str], fetch_k: int
) -> list[list[str]]:
    """Top-fetch_k article_id KHONG loc threshold (khac
    `app.retrieval.entry_point.find_entry_points` - ham do LOC theo
    `config.SIMILARITY_THRESHOLD` cho production `/chat`, o day can top-k
    THUAN TUY de khop dung phuong phap "Dense-only"/nhanh dense trong RRF
    cua project truoc, khong loc gi ca).

    Mot loi goi Chroma DUY NHAT cho TOAN BO queries (Chroma ho tro nhieu
    query_embeddings trong 1 lan goi) - nhanh hon N loi goi rieng."""
    from app.retrieval.embedder import embed_texts, get_chroma_collection

    if not queries:
        return []
    query_embeddings = embed_texts(queries)
    collection = get_chroma_collection()
    raw = collection.query(query_embeddings=query_embeddings, n_results=fetch_k)
    return [ids for ids in (raw.get("ids") or [])]


class Reranker:
    """Wrap `sentence_transformers.CrossEncoder` - lazy-load (chi tai model
    lan dau goi `rerank()`), cache instance o cap object (KHONG tao
    CrossEncoder moi moi lan goi - cung so bay 12e voi SentenceTransformer
    trong `app.retrieval.embedder`, tranh crash native tren Windows do
    load lai model xen ke)."""

    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            from app.retrieval.embedder import _resolve_device

            logger.info(
                "dang tai reranker model %r (device=%s, max_length=%d)",
                self.model_name,
                _resolve_device(),
                _RERANKER_MAX_LENGTH,
            )
            self._model = CrossEncoder(
                self.model_name, device=_resolve_device(), max_length=_RERANKER_MAX_LENGTH
            )
        return self._model

    def rerank(
        self, query: str, candidate_ids: list[str], texts: dict[str, str], top_k: int
    ) -> list[str]:
        """Cham diem lai tung cap (query, full_text) bang cross-encoder,
        tra ve top_k article_id sap theo diem giam dan.

        Candidate_id KHONG co trong `texts` (hiem - vd Article chua embed,
        chi 8/60,568 tai thoi diem viet, xem TIEN_DO.md DOT 13) bi BO QUA
        khoi rerank (khong the cham diem khong co noi dung) thay vi crash.
        `candidate_ids` rong -> tra ve rong, khong tai model."""
        scoreable = [(cid, texts[cid]) for cid in candidate_ids if cid in texts]
        if not scoreable:
            return []
        model = self._get_model()
        pairs = [(query, text) for _cid, text in scoreable]
        scores = model.predict(pairs)
        ranked = sorted(zip(scoreable, scores), key=lambda pair: pair[1], reverse=True)
        return [cid for (cid, _text), _score in ranked[:top_k]]


def _evaluate(
    name: str,
    retrieve_fn,
    questions: list[str],
    expected: list[str],
    k: int,
    checkpoint: dict,
    checkpoint_every: int = CHECKPOINT_EVERY,
) -> dict:
    """Danh gia MOT chien luoc: `retrieve_fn(question) -> list[article_id]`
    (da xep hang). Recall@k/MRR dinh nghia GIONG HET
    `scripts.bench_bm25_backends.recall_and_mrr` (mot dap an dung/cau) -
    KHONG tai dung ham do truc tiep vi o day retrieve tung cau MOT (can
    goi Chroma/reranker theo batch khac nhau tuy chien luoc), nhung cong
    thuc diem giu nguyen y het.

    `checkpoint`: resume tu `checkpoint["in_progress"]` NEU "name" trong do
    khop `name` truyen vao (lan chay truoc bi ngat GIUA CHUNG chinh chien
    luoc nay) - bo qua cac cau hoi da tinh, chi chay tiep tu
    "next_index". Ghi checkpoint sau moi `checkpoint_every` cau hoi VA khi
    xong (persist ra dia qua `_save_checkpoint`, khong chi giu trong RAM -
    de song sot duoc qua lan tien trinh bi dung nhu da xay ra that, xem
    TIEN_DO.md)."""
    state = (checkpoint.get("in_progress") or {}).get(name)
    if state:
        start_idx = state["next_index"]
        hits = state["hits"]
        rr_total = state["rr_total"]
        logger.info(
            "[resume] %s: tiep tuc tu cau %d/%d (da co %d hit)",
            name, start_idx + 1, len(questions), hits,
        )
    else:
        start_idx = 0
        hits = 0
        rr_total = 0.0

    t0 = time.monotonic()
    for i in range(start_idx, len(questions)):
        question, want = questions[i], expected[i]
        ranked = retrieve_fn(question)[:k]
        if want in ranked:
            hits += 1
            rr_total += 1.0 / (ranked.index(want) + 1)

        if (i + 1) % checkpoint_every == 0 or (i + 1) == len(questions):
            # Ghi vao KHOA RIENG cua chien luoc nay - truoc day dong nay gan
            # `checkpoint["in_progress"] = {...}` nen de mat state cua chien
            # luoc khac dang do dang (bug that, xem _load_checkpoint).
            checkpoint.setdefault("in_progress", {})[name] = {
                "name": name, "next_index": i + 1, "hits": hits, "rr_total": rr_total,
            }
            _save_checkpoint(checkpoint)

    elapsed = time.monotonic() - t0
    n = len(questions)
    recall = hits / n if n else 0.0
    mrr = rr_total / n if n else 0.0
    logger.info(
        "%s: Recall@%d = %.1f%% (%d/%d), MRR = %.3f, %.1fs (lan chay nay, khong tinh phan resume)",
        name, k, recall * 100, hits, n, mrr, elapsed,
    )
    result = {"name": name, "recall_at_k": recall, "hits": hits, "total": n, "mrr": mrr, "elapsed_s": elapsed}
    checkpoint["completed"][name] = result
    # Chi xoa `in_progress` khi no THUOC VE chinh chien luoc vua xong.
    # BUG THAT (2026-08-08) da lam mat 720/793 cau da rerank (~5.6 gio may):
    # truoc day dong nay la `checkpoint["in_progress"] = None` VO DIEU KIEN, nen
    # khi them chien luoc "2b" vao giua luc reranker dang co state do dang
    # (next_index=720), viec 2b hoan tat da XOA state cua reranker -> lan chay
    # sau bat dau lai tu 0.
    (checkpoint.get("in_progress") or {}).pop(name, None)
    _save_checkpoint(checkpoint)
    return result


def run_eval(
    data_dir: str | Path,
    *,
    limit_docs: int | None = None,
    # None = TOAN BO gold set. Mac dinh cu la 50 - mot cai bay cho script
    # BASELINE: chay khong tham so se ra con so tren 50 cau roi bi hieu la
    # baseline chinh thuc (da that su xay ra, xem QuestionCountMismatchError).
    # Baseline phai mac dinh do toan bo, giong `eval_zalo_recall.py` cua du an
    # cu (`--limit` la tuy chon).
    limit_queries: int | None = None,
    k: int = DEFAULT_K,
    fetch_k: int = DEFAULT_FETCH_K,
    reranker_model: str = DEFAULT_RERANKER_MODEL,
    restart: bool = False,
) -> list[dict]:
    """Vong lap chinh - tach khoi `main()` de test/goi truc tiep duoc,
    cung pattern voi `scripts.bench_bm25_backends.main`.

    `restart=True`: bo qua checkpoint cu, chay lai TOAN BO tu dau (mac
    dinh False - resume tu checkpoint neu co, giong
    `eval_zalo_recall.py --restart`)."""
    import bm25s

    from app.retrieval.embedder import get_texts
    from scripts.bench_bm25_backends import (
        filter_gold_to_indexed_corpus,
        load_corpus,
        load_gold,
        tokenize,
    )

    logger.info("doc corpus...")
    ids, texts_list = load_corpus(data_dir, limit=limit_docs)
    logger.info("  %d tai lieu", len(ids))

    logger.info("tokenize + build BM25 index (bm25s)...")
    corpus_tokens = [tokenize(t) for t in texts_list]
    bm25_index = bm25s.BM25(method="robertson")
    bm25_index.index(corpus_tokens, show_progress=False)

    all_q, all_e = load_gold()
    questions, expected = filter_gold_to_indexed_corpus(all_q, all_e, set(ids))
    if limit_queries is not None:
        questions = questions[:limit_queries]
        expected = expected[:limit_queries]
    if not questions:
        raise SystemExit("Khong con cau hoi nao sau khi loc - tang --limit-docs.")
    logger.info("%d cau hoi gold set Zalo (sau khi loc)", len(questions))

    checkpoint = {"completed": {}, "in_progress": {}} if restart else _load_checkpoint()
    if checkpoint["completed"] or checkpoint["in_progress"]:
        logger.info(
            "tim thay checkpoint: %d chien luoc da xong (%s), %s",
            len(checkpoint["completed"]), list(checkpoint["completed"]),
            f"{len(checkpoint.get('in_progress') or {})} chien luoc dang do dang",
        )
    # TRUOC khi chay bat ky chien luoc nao: tu choi neu quy mo lech (xem
    # QuestionCountMismatchError). Neu khong, cac chien luoc se duoc do o hai
    # quy mo khac nhau roi in canh nhau.
    _check_question_count_matches_checkpoint(checkpoint, len(questions))
    checkpoint["n_questions"] = len(questions)

    def _bm25_topk(query: str, k_: int) -> list[str]:
        query_tokens = tokenize(query)
        idx, _scores = bm25_index.retrieve([query_tokens], k=k_, show_progress=False)
        return [ids[i] for i in idx[0]]

    results: list[dict] = []

    name1 = "1. Dense-only"
    logger.info("--- 1/3: %s ---", name1)
    if name1 in checkpoint["completed"]:
        logger.info("[skip - da xong] %s", name1)
        results.append(checkpoint["completed"][name1])
    else:
        dense_top_k = dense_search_topk(questions, fetch_k=k)
        results.append(
            _evaluate(name1, lambda q, _cache=dict(zip(questions, dense_top_k)): _cache[q], questions, expected, k, checkpoint)
        )

    name2 = "2. Hybrid (BM25 + dense, RRF)"
    logger.info("--- 2/3: %s ---", name2)
    dense_fetch = dense_search_topk(questions, fetch_k=fetch_k)
    dense_fetch_by_q = dict(zip(questions, dense_fetch))

    def _hybrid(q: str) -> list[str]:
        sparse = _bm25_topk(q, fetch_k)
        dense = dense_fetch_by_q[q]
        return reciprocal_rank_fusion([sparse, dense])

    if name2 in checkpoint["completed"]:
        logger.info("[skip - da xong] %s", name2)
        results.append(checkpoint["completed"][name2])
    else:
        results.append(_evaluate(name2, _hybrid, questions, expected, k, checkpoint))

    # === Dong "2b": Hybrid dung rank_bm25 thay vi bm25s ===
    # MUC DICH: LUONG HOA anh huong cua backend BM25 len ket qua da fuse, thay
    # vi de no thanh mot bien gay nhieu AN. Do that o DOT 14: hai backend chi
    # khop ~66% thu hang va lech 6.3 diem % Recall@4 khi dung MOT MINH - nen
    # khong the gia dinh "fuse xong thi giong nhau".
    #
    # Chi chay tang BM25+RRF (KHONG reranker): reranker la phan dat nhat (~7.5s/
    # cau) va chi phi GIONG NHAU du backend nao, nen chay lai voi no chi de
    # tra gia gap doi cho phan khong doi.
    name2b = "2b. Hybrid (rank_bm25 + dense, RRF)"
    logger.info("--- 2b: %s ---", name2b)
    if name2b in checkpoint["completed"]:
        logger.info("[skip - da xong] %s", name2b)
        results.append(checkpoint["completed"][name2b])
    else:
        from rank_bm25 import BM25Okapi

        logger.info("  build index rank_bm25 (backend cua du an cu)...")
        rank_index = BM25Okapi(corpus_tokens)

        def _rank_bm25_topk(query: str, k_: int) -> list[str]:
            import numpy as np

            scores = rank_index.get_scores(tokenize(query))
            return [ids[i] for i in np.argsort(scores)[::-1][:k_]]

        def _hybrid_rank_bm25(q: str) -> list[str]:
            return reciprocal_rank_fusion(
                [_rank_bm25_topk(q, fetch_k), dense_fetch_by_q[q]]
            )

        results.append(
            _evaluate(name2b, _hybrid_rank_bm25, questions, expected, k, checkpoint)
        )

    name3 = "3. Hybrid + Reranker"
    logger.info("--- 3/3: %s ---", name3)
    hybrid_candidates_by_q = {q: _hybrid(q)[:fetch_k] for q in questions}

    if name3 in checkpoint["completed"]:
        logger.info("[skip - da xong] %s", name3)
        results.append(checkpoint["completed"][name3])
    else:
        all_candidate_ids = sorted({cid for cands in hybrid_candidates_by_q.values() for cid in cands})
        logger.info("  lay full text cho %d candidate id (batched)...", len(all_candidate_ids))
        candidate_texts = get_texts(all_candidate_ids)

        # Giai phong model embedding TRUOC khi tai reranker: den day moi ket
        # qua dense da tinh san xong nen no khong con can, va giu ca hai model
        # tren GPU 6GB lam VRAM len 96% -> lan chay truoc CHET o cau 720/793.
        # Phai goi SAU `get_texts` (get_texts dung Chroma collection, khong
        # dung model - nhung de thu tu nay cho ro rang y dinh).
        from app.retrieval.embedder import release_model

        logger.info("  giai phong model embedding de nhuong VRAM cho reranker")
        release_model()

        reranker = Reranker(reranker_model)

        def _hybrid_rerank(q: str) -> list[str]:
            return reranker.rerank(q, hybrid_candidates_by_q[q], candidate_texts, top_k=k)

        results.append(_evaluate(name3, _hybrid_rerank, questions, expected, k, checkpoint))

    logger.info("\n=== TOM TAT (Recall@%d, baseline MOI o 67k) ===", k)
    for r in results:
        logger.info("  %s: Recall@%d = %.1f%%, MRR = %.3f", r["name"], k, r["recall_at_k"] * 100, r["mrr"])

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("da ghi ket qua vao %s", RESULT_PATH)

    return results


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=str)
    parser.add_argument("--limit-docs", type=int, default=None)
    # default=None = TOAN BO gold set (793 cau). Truoc day la 50 - cai bay da
    # thuc su gay ra so lieu sai (xem QuestionCountMismatchError). Doi default
    # cua `run_eval` MA KHONG doi default o day la sua nua voi: argparse van
    # truyen 50 vao, ghi de gia tri mac dinh cua ham.
    parser.add_argument(
        "--limit-queries",
        type=int,
        default=None,
        help="Chi do N cau dau (mac dinh: TOAN BO gold set) - chi dung de debug.",
    )
    parser.add_argument("-k", type=int, default=DEFAULT_K)
    parser.add_argument("--fetch-k", type=int, default=DEFAULT_FETCH_K)
    parser.add_argument("--reranker-model", type=str, default=DEFAULT_RERANKER_MODEL)
    parser.add_argument(
        "--restart", action="store_true",
        help="Bo qua checkpoint cu, chay lai tu dau hoan toan.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_arg_parser().parse_args()
    run_eval(
        args.data_dir,
        limit_docs=args.limit_docs,
        limit_queries=args.limit_queries,
        k=args.k,
        fetch_k=args.fetch_k,
        reranker_model=args.reranker_model,
        restart=args.restart,
    )


if __name__ == "__main__":
    main()
