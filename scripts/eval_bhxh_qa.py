"""eval_bhxh_qa.py (PA-B): do CHAT LUONG CAU TRA LOI kieu ALQAC - khong chi
retrieval ma la generation co cham diem.

3 loai cau (data/eval/bhxh_qa_set.json):
  - true_false: LLM tra loi RANG BUOC "Dung"/"Sai" -> so khop dap an.
  - multiple_choice: LLM tra loi RANG BUOC A/B/C/D -> so khop.
  - free_text: LLM tra loi tu do -> kiem tra MOI key_fact xuat hien + gold Dieu
    duoc truy xuat (citation kha dung).

Dung CHINH luong retrieval cua chat() (find_entry_points -> traverse -> rank ->
[rerank]) de lay ngu canh, roi prompt rang buoc + Ollama.

CACH DUNG: python -m scripts.eval_bhxh_qa
(can Neo4j + Chroma corpus BHXH + Ollama chay.)
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from app import config
from app.graph_store.neo4j_client import Neo4jClient
from app.retrieval import embedder
from app.retrieval.entry_point import find_entry_points
from app.retrieval.ranking import rank_article_ids
from app.retrieval.reranker import rerank_ids
from app.retrieval.traversal import traverse
from app.serving.api import _call_ollama

QA_PATH = Path("data/eval/bhxh_qa_set.json")


def _retrieve(question: str, client: Neo4jClient) -> tuple[list[str], dict[str, str]]:
    """(ranked_ids top MAX_CONTEXT_ARTICLES, texts) - sao luong chat()."""
    fetch_k = config.RERANK_FETCH_K if config.RERANK_ENABLED else config.MAX_CONTEXT_ARTICLES
    eps = find_entry_points(question, top_k=fetch_k)
    if not eps:
        return [], {}
    entry_ids = [e.article_id for e in eps]
    tr = traverse(client, sorted(set(entry_ids)))
    pool = rank_article_ids(entry_ids, tr, limit=fetch_k)
    texts = embedder.get_texts(pool)
    if config.RERANK_ENABLED:
        ranked = rerank_ids(question, pool, texts, config.MAX_CONTEXT_ARTICLES)
    else:
        ranked = pool[: config.MAX_CONTEXT_ARTICLES]
    return ranked, texts


def _context_block(ranked: list[str], texts: dict[str, str]) -> str:
    return "\n\n".join(f"[Điều: {a}]\n{texts.get(a, '')}" for a in ranked) or "(không có ngữ cảnh)"


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFC", s).strip().lower()
    # Chuan hoa so 0 dau ("06 thang" -> "6 thang") de key-fact khong lech chi
    # vi cach LLM viet so (6 vs 06) - so khop noi dung, khong so khop format.
    return re.sub(r"\b0+(\d)", r"\1", s)


def _ask(question: str, ctx: str, instruction: str) -> str:
    prompt = (
        "Bạn là trợ lý pháp luật. CHỈ dựa vào NGỮ CẢNH dưới đây.\n"
        f"{instruction}\n\n"
        f"NGỮ CẢNH:\n{ctx}\n\nCÂU HỎI: {question}\n\nTRẢ LỜI:"
    )
    return _call_ollama(prompt)


def _score_true_false(ans: str, gold: str) -> bool:
    a = _strip(ans)
    # Lay tu dau tien mang nghia dung/sai.
    said_sai = bool(re.search(r"\bsai\b|\bkhông đúng\b", a))
    said_dung = bool(re.search(r"\bđúng\b", a)) and not said_sai
    pred = "đúng" if said_dung else ("sai" if said_sai else "?")
    return pred == _strip(gold)


def _score_mc(ans: str, gold: str) -> bool:
    """Bat chu cai dap an: uu tien mau "X)"/"X."/"X:"/"dap an X"/"chon X"
    (dau chuoi hoac sau tu chi dinh) - de tranh khop nham chu cai xuat hien
    ngau nhien trong giai thich. Fallback ve "\\b[ABCD]\\b" o dau chuoi."""
    up = ans.strip().upper()
    patterns = [
        r"^\s*([ABCD])\s*[\)\.:\-]",           # "C)" "C." "C:" "C -"
        r"(?:ĐÁP\s*ÁN|CHỌN|CÂU\s*TR[ẢA]\s*L[ỜO]I)\s*(?:LÀ|:|\s)+\s*([ABCD])\b",
        r"^\s*([ABCD])\s*$",                    # chi mot chu cai
        r"^\s*([ABCD])\b",                      # dau chuoi
    ]
    for p in patterns:
        m = re.search(p, up)
        if m:
            return m.group(1) == gold.upper()
    return False


def _score_free(ans: str, key_facts: list[str], ranked: list[str], gold_ids: list[str]) -> tuple[bool, bool]:
    a = _strip(ans)
    facts_ok = all(_strip(k) in a for k in key_facts)
    cite_ok = any(g in ranked for g in gold_ids)  # gold Dieu duoc truy xuat
    return facts_ok, cite_ok


# Cac cum tu chi guardrail hoat dong (LLM khong bia, tu choi lich su).
_REFUSAL_MARKERS = [
    "chưa tìm thấy", "không có", "không tìm thấy", "ngoài phạm vi",
    "không thuộc", "không liên quan", "không đủ căn cứ", "không thể trả lời",
    "không có thông tin", "không có dữ liệu",
]


def _score_out_of_scope(ans: str) -> bool:
    """Cau ngoai pham vi -> tra loi PHAI la tu choi/thua nhan khong co du lieu.
    KHONG duoc phep bia noi dung phap luat."""
    a = _strip(ans)
    return any(_strip(m) in a for m in _REFUSAL_MARKERS)


def main() -> None:
    data = json.loads(QA_PATH.read_text(encoding="utf-8"))
    qs = data["questions"]
    by_type: dict[str, list[bool]] = {"true_false": [], "multiple_choice": [], "free_text": [], "out_of_scope": []}
    free_cite: list[bool] = []
    retr_hit: list[bool] = []
    wrong: list[str] = []

    with Neo4jClient() as client:
        for q in qs:
            ranked, texts = _retrieve(q["question"], client)
            if q["gold_article_ids"]:
                retr_hit.append(any(g in ranked for g in q["gold_article_ids"]))
            ctx = _context_block(ranked, texts)
            t = q["type"]
            if t == "out_of_scope":
                # Dung goc chat() flow: ngu canh la BHXH nhung cau ngoai pham vi
                # -> LLM PHAI tu choi/thua nhan khong co du lieu, khong bia.
                ans = _ask(q["question"], ctx,
                           "Nếu ngữ cảnh không đủ để trả lời câu hỏi này, hãy trả lời: "
                           "\"Chưa tìm thấy quy định cụ thể trong dữ liệu\" và KHÔNG được bịa.")
                ok = _score_out_of_scope(ans)
            elif t == "true_false":
                ans = _ask(q["question"], ctx, "Chỉ trả lời DUY NHẤT một từ: \"Đúng\" hoặc \"Sai\".")
                ok = _score_true_false(ans, q["answer"])
            elif t == "multiple_choice":
                opts = "\n".join(f"{k}) {v}" for k, v in q["options"].items())
                ans = _ask(q["question"] + "\n" + opts, ctx,
                           "Chỉ trả lời DUY NHẤT một chữ cái: A, B, C hoặc D.")
                ok = _score_mc(ans, q["answer"])
            else:  # free_text
                ans = _ask(q["question"], ctx,
                           "Trả lời ngắn gọn, đúng trọng tâm, dựa vào ngữ cảnh.")
                facts_ok, cite_ok = _score_free(ans, q["key_facts"], ranked, q["gold_article_ids"])
                ok = facts_ok
                free_cite.append(cite_ok)
            by_type[t].append(ok)
            if not ok:
                wrong.append(f"[{t}] {q['question'][:60]} -> {ans.strip()[:60]!r}")

    def pct(xs: list[bool]) -> str:
        return f"{(sum(xs)/len(xs)):.1%} ({sum(xs)}/{len(xs)})" if xs else "n/a"

    print(f"=== EVAL QA BHXH ({len(qs)} cau) - model={config.OLLAMA_MODEL}, rerank={config.RERANK_ENABLED} ===")
    print(f"  Retrieval hit (gold Dieu duoc truy xuat): {pct(retr_hit)}")
    print(f"  True/False  accuracy: {pct(by_type['true_false'])}")
    print(f"  Multiple-choice acc : {pct(by_type['multiple_choice'])}")
    print(f"  Free-text key-facts : {pct(by_type['free_text'])}")
    print(f"  Free-text citation  : {pct(free_cite)}")
    print(f"  Out-of-scope refusal: {pct(by_type['out_of_scope'])}")
    allb = by_type['true_false'] + by_type['multiple_choice'] + by_type['free_text'] + by_type['out_of_scope']
    print(f"  === TONG accuracy   : {pct(allb)} ===")
    if wrong:
        print("  Sai:")
        for w in wrong:
            print(f"    - {w}")


if __name__ == "__main__":
    main()
