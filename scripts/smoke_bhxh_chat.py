"""smoke_bhxh_chat.py (BHXH-P2-T4): demo hoi-dap end-to-end tren corpus BHXH.

Goi truc tiep logic `app.serving.api.chat` (find_entry_points -> traverse ->
rank -> build_prompt -> Ollama) cho vai cau hoi BHXH thuc te, in cau tra loi
+ trich dan (article_id, dau * = entry point tu dense retrieval).

CACH DUNG:
    python -m scripts.smoke_bhxh_chat
(can Neo4j + Chroma da co corpus BHXH - xem scripts/fetch_bhxh_corpus.py va
scripts/embed_bhxh.py - va Ollama dang chay, model theo app/config.OLLAMA_MODEL).
"""
from __future__ import annotations

from app.serving.api import ChatRequest, chat

# Cau hoi nguoi lao dong pho thong thuong gap, phu 3 che do MVP + thất nghiệp.
DEMO_QUESTIONS = [
    "Điều kiện hưởng bảo hiểm xã hội một lần là gì?",
    "Lao động nữ được nghỉ thai sản bao nhiêu tháng?",
    "Mức hưởng lương hưu hằng tháng được tính như thế nào?",
    "Đóng bảo hiểm thất nghiệp bao lâu thì được hưởng trợ cấp?",
]


def _fmt_citations(citation_path: list[dict]) -> list[str]:
    return [
        f"{c.get('article_id')}{'*' if c.get('is_entry_point') else ''}"
        f"{' [ngoài corpus]' if c.get('is_external') else ''}"
        for c in citation_path
    ]


def main() -> None:
    for question in DEMO_QUESTIONS:
        print("\n" + "=" * 72)
        print("HỎI:", question)
        result = chat(ChatRequest(question=question))
        print("\nTRẢ LỜI:\n" + (result.get("answer") or "(trống)"))
        print("\nTRÍCH DẪN:", _fmt_citations(result.get("citation_path", [])))


if __name__ == "__main__":
    main()
