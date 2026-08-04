"""build_multihop_eval_set.py (T016): dao (mine) cac chuoi REFERENCES that tu
graph da ingest, kem noi dung that, de con nguoi (Claude - tac nhan hoi thoai
cua session nay, do Khang duyet lai sau) doc va TU VIET cau hoi multi-hop that
dung de kiem tra SC-001 (spec.md).

QUAN TRONG - pham vi HEP hon ten task goi y (xem task-3f-brief.md muc "Important:
this task's scope is narrower than the task name suggests"): spec.md's Assumptions
noi ro cau hoi TIENG VIET tu nhien phai do CON NGUOI/Claude (hoi thoai) doc du
lieu that va tu viet - KHONG duoc sinh tu dong boi script/LLM API (constitution:
"khong phu thuoc API tra phi", Dieu 1). Script nay CHI lam nua "dao du lieu": tim
chuoi REFERENCES that + gan noi dung that vao MOI article trong chuoi, ghi ra
JSON de nguoi doc duyet - KHONG viet san cau hoi (do la buoc SAU, lam thu cong/
hoi thoai, ngoai pham vi script nay).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): truy van graph (qua
`Neo4jClient`, tai su dung - khong tu viet lai connection logic) + gan noi dung
that cho moi article trong chuoi (uu tien full text qua `embedder.get_texts`,
fallback `noi_dung_preview` tu Neo4j - CUNG phan biet is_preview da thiet lap o
`serving/api.py`, T014) + ghi JSON. KHONG goi LLM/API tra phi nao, KHONG tu sinh
van ban cau hoi.

CACH DUNG:
    python scripts/build_multihop_eval_set.py --out <path> [--limit N] [--min-content-length N]
    python -m scripts.build_multihop_eval_set --out <path>   (tuong duong - xem
        sys.path shim duoi day, ho tro ca hai cach goi vi backfill_embeddings.py
        chi ho tro "-m" nhung brief T016 vi du "python scripts/...py" truc tiep)

Vi du:
    python scripts/build_multihop_eval_set.py --out data/eval/multihop_candidates.json
    python scripts/build_multihop_eval_set.py --out /tmp/x.json --limit 20 --min-content-length 50

=== 2 tap ung vien (candidate pools) ===
1. `two_hop_candidates`: chuoi A -[:REFERENCES]-> B -[:REFERENCES]-> C, ca 3
   Article deu `is_external = false` (noi dung that, khong phai placeholder -
   khong the viet cau hoi co y nghia tu placeholder rong). A == C (vong lap
   trich dan A->B->A) KHONG bi loc bo - day la ung vien hop le, thu vi cho
   dang cau hoi "chu ky trich dan" (xem brief).
2. `one_hop_candidates`: cap A -[:REFERENCES]-> B, cung dieu kien is_external,
   tap ung vien PHU (mot so cau hoi hay chi can 2 Dieu, khong can 3 - MAX_HOP=2
   nhung mot cau hoi van co the chi nham 1 hop cua no).

Ca hai tap deu loc theo `--min-content-length`: MOI article trong chuoi phai co
noi dung kha dung (full text hoac preview) dai it nhat N ky tu - loc bo cac
Dieu gan-rong khong the tao cau hoi thu vi.

=== Sap xep xac dinh (deterministic) ===
Ca hai tap ung vien duoc sap xep theo tuple(article_ids) cua tung chuoi (cung
ky luat determinism nhu phan con lai cua du an - vd `traverse()`/`run_backfill`
luon `sorted(...)` truoc khi query/ghi) - chay lai script nhieu lan tren CUNG
trang thai graph se cho CUNG thu tu output.

=== `--limit` ap dung DOC LAP cho MOI tap (khong phai tong 2 tap cong lai) ===
Mac dinh (`DEFAULT_LIMIT_PER_POOL` = 80) nham dat muc tieu brief neu "surface it
nhat 60-80 ung vien" cho MOI dang cau hoi (2-hop la trong tam chinh vi khop
MAX_HOP=2, 1-hop la tap phu) - nhieu hon nhieu so voi >=30 cau hoi cuoi cung can
(khong phai moi ung vien deu thanh cau hoi tot, ro rang, xem brief)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

# Shim nho: cho phep goi truc tiep "python scripts/build_multihop_eval_set.py"
# (brief T016 dua vi du nay) MA VAN import duoc `app`/`scripts` (goi truc tiep
# mot file .py dat sys.path[0] la thu muc CHUA file do, tuc "scripts/", khong
# phai project root - khac voi "python -m scripts.X" dat cwd/project root vao
# sys.path). Chi chay khi can (script duoc thuc thi truc tiep), khong anh
# huong khi module duoc import binh thuong trong test (test import qua
# "from scripts.build_multihop_eval_set import ..." - luc do project root da
# co san tren sys.path qua co che rootdir cua pytest, xem tests/__init__.py).
if __name__ == "__main__" and __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graph_store.neo4j_client import Neo4jClient  # noqa: E402
from app.retrieval import embedder  # noqa: E402

logger = logging.getLogger(__name__)

# Xem module docstring muc "--min-content-length"/"--limit" o tren cho ly do
# chon 2 gia tri mac dinh nay.
DEFAULT_MIN_CONTENT_LENGTH = 80
DEFAULT_LIMIT_PER_POOL = 80

# 2 cau Cypher co dinh (khong tham so hoa boi input nguoi dung - khong co rui
# ro injection - nen khong can $param cho phan WHERE literal false).
#
# A == C (vong lap trich dan) KHONG bi loai o day - chi loc is_external, xem
# module docstring.
_TWO_HOP_QUERY = (
    "MATCH (a:Article)-[:REFERENCES]->(b:Article)-[:REFERENCES]->(c:Article) "
    "WHERE a.is_external = false AND b.is_external = false AND c.is_external = false "
    "RETURN a.article_id AS a_id, b.article_id AS b_id, c.article_id AS c_id, "
    "a.noi_dung_preview AS a_preview, b.noi_dung_preview AS b_preview, "
    "c.noi_dung_preview AS c_preview"
)

_ONE_HOP_QUERY = (
    "MATCH (a:Article)-[:REFERENCES]->(b:Article) "
    "WHERE a.is_external = false AND b.is_external = false "
    "RETURN a.article_id AS a_id, b.article_id AS b_id, "
    "a.noi_dung_preview AS a_preview, b.noi_dung_preview AS b_preview"
)


@dataclass
class Candidate:
    """Mot ung vien chuoi REFERENCES that, kem noi dung, san sang cho con
    nguoi doc va viet cau hoi. `articles` giu THU TU cua chuoi (co the co
    article_id LAP LAI trong truong hop vong lap A->B->A - moi lan xuat hien
    van giu nguyen vi tri trong chuoi, khong bi gop, de nguoi doc thay ro
    cau truc vong lap)."""

    chain_type: str  # "2-hop" hoac "1-hop"
    article_ids: list[str]
    relationship_path: list[dict[str, str]]
    articles: list[dict[str, object]]

    def to_dict(self) -> dict:
        return {
            "chain_type": self.chain_type,
            "article_ids": self.article_ids,
            "relationship_path": self.relationship_path,
            "articles": self.articles,
        }


def _collect_previews(rows: list[dict], id_preview_keys: list[tuple[str, str]]) -> dict[str, str | None]:
    """Gom `article_id -> noi_dung_preview` tu cac dong Cypher da tra ve san
    (KHONG can them mot loi goi Neo4j rieng - preview da co san trong RETURN
    cua ca 2 cau truy van chinh, xem `_TWO_HOP_QUERY`/`_ONE_HOP_QUERY`).
    Article xuat hien nhieu lan (o nhieu chuoi khac nhau, hoac ca 2 tap 1-hop
    va 2-hop) se co CUNG gia tri preview moi lan (thuoc tinh cua node, khong
    doi theo chuoi) - ghi de lan sau khong gay sai lech."""
    previews: dict[str, str | None] = {}
    for row in rows:
        for id_key, preview_key in id_preview_keys:
            previews[row[id_key]] = row.get(preview_key)
    return previews


def _resolve_article_content(
    article_id: str, previews: dict[str, str | None], texts: dict[str, str]
) -> tuple[str | None, bool]:
    """Uu tien full text tu Chroma (`texts`, ket qua cua `embedder.get_texts`)
    - danh dau `is_preview=False`. Neu khong co (chua duoc embed), fallback ve
    `noi_dung_preview` tu Neo4j - danh dau `is_preview=True`. Cung phan biet
    da thiet lap o `serving/api.py`'s `_ArticleContext`/`_classify_articles`
    (T014) - KHONG doi ten field de nguoi doc quen voi quy uoc do co the nhan
    ra ngay."""
    if article_id in texts:
        return texts[article_id], False
    return previews.get(article_id), True


def _build_article_entries(
    article_ids_in_order: list[str],
    previews: dict[str, str | None],
    texts: dict[str, str],
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for article_id in article_ids_in_order:
        content, is_preview = _resolve_article_content(article_id, previews, texts)
        entries.append(
            {"article_id": article_id, "content": content, "is_preview": is_preview}
        )
    return entries


def _content_length_ok(entries: list[dict[str, object]], min_content_length: int) -> bool:
    """MOI article trong chuoi phai dat do dai toi thieu - mot chuoi chi can
    MOT article gan-rong la khong the dung de viet cau hoi co y nghia (xem
    brief)."""
    return all(len(entry["content"] or "") >= min_content_length for entry in entries)


def _build_two_hop_candidates(
    rows: list[dict],
    previews: dict[str, str | None],
    texts: dict[str, str],
    min_content_length: int,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for row in rows:
        a_id, b_id, c_id = row["a_id"], row["b_id"], row["c_id"]
        articles = _build_article_entries([a_id, b_id, c_id], previews, texts)
        if not _content_length_ok(articles, min_content_length):
            continue
        candidates.append(
            Candidate(
                chain_type="2-hop",
                article_ids=[a_id, b_id, c_id],
                relationship_path=[
                    {"from": a_id, "to": b_id, "type": "REFERENCES"},
                    {"from": b_id, "to": c_id, "type": "REFERENCES"},
                ],
                articles=articles,
            )
        )
    candidates.sort(key=lambda c: tuple(c.article_ids))
    return candidates


def _build_one_hop_candidates(
    rows: list[dict],
    previews: dict[str, str | None],
    texts: dict[str, str],
    min_content_length: int,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for row in rows:
        a_id, b_id = row["a_id"], row["b_id"]
        articles = _build_article_entries([a_id, b_id], previews, texts)
        if not _content_length_ok(articles, min_content_length):
            continue
        candidates.append(
            Candidate(
                chain_type="1-hop",
                article_ids=[a_id, b_id],
                relationship_path=[{"from": a_id, "to": b_id, "type": "REFERENCES"}],
                articles=articles,
            )
        )
    candidates.sort(key=lambda c: tuple(c.article_ids))
    return candidates


def build_multihop_eval_set(
    client: Neo4jClient,
    *,
    min_content_length: int = DEFAULT_MIN_CONTENT_LENGTH,
    limit: int = DEFAULT_LIMIT_PER_POOL,
) -> dict:
    """Ham loi (khong CLI/IO file) - tach rieng de test truc tiep duoc (goi
    ham nay voi mock client, khong can qua sys.argv/file), cung pattern voi
    `run_backfill`/`run_ingest`.

    Chi 2 loi goi Neo4j (mot cho 2-hop, mot cho 1-hop - khong phai N loi goi
    cho N chuoi) + MOT loi goi `embedder.get_texts` batched cho TOAN BO
    article_id lien quan (ca 2 tap) - tranh N+1 round-trip."""
    two_hop_rows = client.run(_TWO_HOP_QUERY)
    one_hop_rows = client.run(_ONE_HOP_QUERY)

    previews = _collect_previews(
        two_hop_rows, [("a_id", "a_preview"), ("b_id", "b_preview"), ("c_id", "c_preview")]
    )
    previews.update(
        _collect_previews(one_hop_rows, [("a_id", "a_preview"), ("b_id", "b_preview")])
    )

    all_article_ids = sorted(previews.keys())
    texts = embedder.get_texts(all_article_ids)

    two_hop = _build_two_hop_candidates(two_hop_rows, previews, texts, min_content_length)
    one_hop = _build_one_hop_candidates(one_hop_rows, previews, texts, min_content_length)

    return {
        "min_content_length": min_content_length,
        "limit_per_pool": limit,
        "two_hop_candidates": [c.to_dict() for c in two_hop[:limit]],
        "one_hop_candidates": [c.to_dict() for c in one_hop[:limit]],
    }


def run_build_multihop_eval_set(
    out_path: str | Path,
    *,
    min_content_length: int = DEFAULT_MIN_CONTENT_LENGTH,
    limit: int = DEFAULT_LIMIT_PER_POOL,
    client: Neo4jClient | None = None,
) -> dict:
    """Dieu phoi day du: mo (hoac dung) Neo4jClient, xay ung vien, ghi JSON
    ra `out_path`. `client`: injectable cho test (mock) - mac dinh tu tao
    Neo4jClient() khi khong truyen (duong di CLI thuc te), cung pattern
    "owns_client" voi `run_backfill`."""
    owns_client = client is None
    client = client if client is not None else Neo4jClient()
    try:
        result = build_multihop_eval_set(
            client, min_content_length=min_content_length, limit=limit
        )
    finally:
        if owns_client:
            client.close()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "da ghi %d ung vien 2-hop + %d ung vien 1-hop vao %s",
        len(result["two_hop_candidates"]),
        len(result["one_hop_candidates"]),
        out_path,
    )
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dao ung vien chuoi REFERENCES that (2-hop + 1-hop) tu graph da "
            "ingest, kem noi dung that, de con nguoi doc va viet cau hoi "
            "multi-hop that (SC-001) - script nay KHONG tu sinh van ban cau "
            "hoi (xem module docstring)."
        )
    )
    parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Duong dan file JSON de ghi ket qua (vd data/eval/multihop_candidates.json).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT_PER_POOL,
        help=(
            f"So ung vien toi da MOI tap (2-hop VA 1-hop rieng, khong phai "
            f"tong 2 tap) - mac dinh {DEFAULT_LIMIT_PER_POOL}."
        ),
    )
    parser.add_argument(
        "--min-content-length",
        type=int,
        default=DEFAULT_MIN_CONTENT_LENGTH,
        help=(
            f"Do dai toi thieu (ky tu) noi dung cua MOI article trong chuoi "
            f"- mac dinh {DEFAULT_MIN_CONTENT_LENGTH}."
        ),
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = build_arg_parser()
    args = parser.parse_args()
    run_build_multihop_eval_set(
        args.out, min_content_length=args.min_content_length, limit=args.limit
    )


if __name__ == "__main__":
    main()
