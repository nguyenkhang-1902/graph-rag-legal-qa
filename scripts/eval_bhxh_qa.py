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
    m = re.search(r"\b([ABCD])\b", ans.strip().upper())
    return bool(m) and m.group(1) == gold.upper()


def _score_free(ans: str, key_facts: list[str], ranked: list[str], gold_ids: list[str]) -> tuple[bool, bool]:
    a = _strip(ans)
    facts_ok = all(_strip(k) in a for k in key_facts)
    cite_ok = any(g in ranked for g in gold_ids)  # gold Dieu duoc truy xuat
    return facts_ok, cite_ok


def main() -> None:
    data = json.loads(QA_PATH.read_text(encoding="utf-8"))
    qs = data["questions"]
    by_type: dict[str, list[bool]] = {"true_false": [], "multiple_choice": [], "free_text": []}
    free_cite: list[bool] = []
    retr_hit: list[bool] = []
    wrong: list[str] = []

    with Neo4jClient() as client:
        for q in qs:
            ranked, texts = _retrieve(q["question"], client)
            retr_hit.append(any(g in ranked for g in q["gold_article_ids"]))
            ctx = _context_block(ranked, texts)
            t = q["type"]
            if t == "true_false":
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
    allb = by_type['true_false'] + by_type['multiple_choice'] + by_type['free_text']
    print(f"  === TONG accuracy   : {pct(allb)} ===")
    if wrong:
        print("  Sai:")
        for w in wrong:
            print(f"    - {w}")


if __name__ == "__main__":
    main()
