"""ranking.py (T028 buoc 3/3): xep hang cac Article thu duoc tu retrieval
thanh MOT danh sach co thu tu, va gioi han so luong.

Trach nhiem duy nhat cua module nay (constitution Dieu 5): gop entry point +
ket qua traversal thanh danh sach article_id CO THU TU. Khong query vector
store (do la `entry_point.py`), khong query graph (do la `traversal.py`),
khong dung prompt (do la `serving/api.py`).

=== VI SAO CAN MODULE NAY ===
Sau khi them vector cap Khoan (T028 buoc 2), so ung vien trung binh tang tu
6.0 -> 17.1 Article/cau hoi. Do that tren 793 cau Zalo gold, recall BAO HOA o
muc cat = 10:
    k       4      6      8     10     12     15     20
    Recall 71.1%  74.0%  75.2%  75.4%  75.4%  75.4%  75.4%
Cat o 10 KHONG MAT GI ma giam 41% luong ngu canh dua cho LLM (nhanh hon, it
nhieu hon).

Nhung muon cat CO NGHIA thi phai co THU TU, va truoc module nay khong co:
  1. `TraversalResult.visited_article_ids` la mot SET - khong thu tu.
  2. `serving/api._build_prompt` sap ngu canh bang `sorted(contexts)` - thu tu
     CHU CAI cua article_id, khong lien quan do lien quan. Cat 10 tu do se giu
     10 Dieu TUY Y (bug tiem an, chua lo ra vi truoc day khong ai cat).

Logic xep hang dung DA TON TAI nhung nam trong `scripts/eval_graph_recall.py`
(`_ranked_retrieved_article_ids`). App KHONG duoc phu thuoc scripts, nen dua ve
day de ca serving LAN script eval dung CUNG mot nguon - neu de hai ban sao,
`/chat` va so lieu eval se dan lech nhau ma khong ai biet (Dieu 1).
"""
from __future__ import annotations

_REFERENCES = "REFERENCES"


def rank_article_ids(
    entry_point_article_ids: list[str],
    traversal_result,
    limit: int | None = None,
) -> list[str]:
    """Danh sach article_id CO THU TU, uu tien giam dan.

    Thu tu:
      1. Entry point theo DUNG thu tu duoc truyen vao - `find_entry_points` da
         sap theo similarity giam dan, KHONG sap lai o day.
      2. Article tim them qua traversal `REFERENCES`, theo thu tu LAN DAU xuat
         hien trong `traversal_result.edges` (thu tu Neo4j tra ve - xac dinh
         duoc, khong ngau nhien).

    Canh `DEFINES` bi BO QUA: no tro toi `Term`, khong phai Article - dua
    term_id vao danh sach Article se lam cac buoc sau (`get_texts`, citation
    path) tim khong thay.

    Trung lap duoc loai bo, GIU vi tri xuat hien DAU TIEN.

    `limit`: cat con toi da N phan tu (None = khong cat). Vi entry point dung
    truoc, cat luon giu entry point va chi bo phan traversal o duoi - dung uu
    tien mong muon (entry point co diem similarity THAT, Article traversal thi
    khong).
    """
    ranked: list[str] = []
    seen: set[str] = set()

    for article_id in entry_point_article_ids:
        if article_id not in seen:
            seen.add(article_id)
            ranked.append(article_id)

    for edge in traversal_result.edges:
        if edge.relationship_type != _REFERENCES:
            continue
        if edge.to_id not in seen:
            seen.add(edge.to_id)
            ranked.append(edge.to_id)

    if limit is not None:
        return ranked[:limit]
    return ranked
