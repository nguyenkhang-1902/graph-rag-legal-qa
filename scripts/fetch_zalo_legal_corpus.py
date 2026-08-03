"""
Fetch toan bo corpus THAT co NHAN (ground-truth relevance) tu Zalo AI
Challenge 2021 - Legal Text Retrieval, dung lam nguon ingest chinh cho
Graph RAG Legal QA (graph-rag-legal-qa) o quy mo toan bo corpus
(~61.4k van ban that, goi tat "67k" trong tai lieu du an - xem
constitution.md/spec.md).

Adapted (T003, graph-rag-legal-qa) tu ban goc
`rag-chatbot-document-QA/scripts/fetch_zalo_legal_corpus.py` (project truoc,
CHI DOC, khong sua) - logic tai/ghi giu nguyen, chi doi:
  - Doc string + comment tham chieu sang project moi (bo cac duong dan noi
    bo cua project cu nhu case04/docs/engineering/... khong ton tai o day).
  - Xac nhan lai + noi ro: mac dinh (KHONG truyen --subset-size/--max-docs)
    da la che do FULL - tai toan bo corpus, khong co gioi han an nao khac.
    Day la che do BAT BUOC dung cho ingest that (constitution.md: "toan bo
    67k van ban", khong con la "2k/10k" de xuat ban dau).
  - "Buoc tiep theo" cuoi script tro ve entry point cua project moi
    (`app/ingest.py`, `scripts/eval_graph_recall.py`) thay vi project cu.

NGUON: "Zalo AI Challenge 2021 - Legal Text Retrieval" (van ban luat Viet
Nam that, dataset thi/benchmark cong khai, duoc dung lai trong MTEB - Massive
Text Embedding Benchmark - voi ten task "ZacLegalTextRetrieval", license
MIT). Tai qua Hugging Face dataset da duoc chuan hoa:
`GreenNode/zalo-ai-legal-text-retrieval-vn` (khong can API key/dang nhap
qua thu vien `datasets`).
  - subset "corpus": ~61.4k van ban luat that (cot _id, title, text)
  - subset "queries": 818 cau hoi that (cot _id, text)
  - subset "qrels"  : 793 cap (query-id, corpus-id, score) - nhan lien quan
    THAT, trung binh ~1 doc lien quan/query (toi da 2)

KHONG CHAY DUOC TRONG SANDBOX VERIFY (huggingface.co bi chan qua allowlist
proxy). Chay TREN MAY THAT (yeu cau `pip install datasets`, KHONG nam trong
requirements/base.txt vi day la script mot-lan, khong phai dependency
runtime cua app/).

2 CHE DO ghi ra:
  1. MAC DINH (khong truyen --subset-size): ghi HET ~61k van ban - day la
     che do BAT BUOC cho ingest that o quy mo du an nay (67k, batch +
     savepoint - xem research.md ADR-002). Luu y: buoc TAI (load_dataset)
     tu Hugging Face luon keo ve toan bo split "corpus" du dung che do nao,
     vi API cua thu vien `datasets` khong ho tro fetch rieng vai dong theo
     ID - --subset-size chi giam so FILE GHI RA DIA (giam so van ban phai
     ingest/embed sau nay), khong giam duoc luu luong tai ve ban dau.
  2. --subset-size N (TUY CHON, CHI DUNG DE TEST CUC BO - khong phai duong
     di mac dinh cua du an nay): CHI ghi ra N van ban - uu tien toan bo van
     ban ma 793 cap qrels can (~447 van ban duy nhat), roi them van ban
     nhieu ngau nhien (seed co dinh, xem --seed) tu phan con lai cho du N.
     Toan bo cau hoi trong gold set van co dap an dung nam trong subset -
     chi khac quy mo "kho tai lieu" nho hon 61k that su. Dung khi may cuc bo
     khong du manh de embed ca 61k van ban trong luc phat trien/debug
     pipeline - KHONG dung che do nay cho ingest chinh thuc cua du an
     (constitution.md da chot toan bo 67k van ban).

Ghi ra:
  <out>/*.md          - van ban luat that (.md, 1 file/doc)
  <out>/README.md     - ghi nguon + license
  scripts/quality_fixtures/gold_set_zalo.json - cau hoi that + doc lien quan
    THAT (dung de danh gia Recall@k/MRR qua scripts/eval_graph_recall.py -
    xem specs/001-graph-rag-core/tasks.md T017).

CACH DUNG (tren may that):
    pip install datasets
    python scripts/fetch_zalo_legal_corpus.py --out data/raw/legal_real                     # FULL ~61k (mac dinh, dung cho ingest that)
    python scripts/fetch_zalo_legal_corpus.py --out data/raw/legal_real --subset-size 2000   # subset that, CHI de test cuc bo
"""
import argparse
import json
import os
import random
import re
import sys

OUTPUT_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "legal_real")
GOLD_SET_OUT_DEFAULT = os.path.join(
    os.path.dirname(__file__), "quality_fixtures", "gold_set_zalo.json"
)
HF_DATASET = "GreenNode/zalo-ai-legal-text-retrieval-vn"

LICENSE_NOTE = (
    "# Nguon: Zalo AI Challenge 2021 - Legal Text Retrieval\n\n"
    "Toan bo file .md trong thu muc nay lay tu dataset\n"
    f"`{HF_DATASET}` (Hugging Face, subset \"corpus\"),\n"
    "duoc chuan hoa lai tu benchmark cong khai Zalo AI Challenge 2021 va\n"
    "hien la 1 task trong MTEB (\"ZacLegalTextRetrieval\"), **license MIT**.\n"
    "Van ban luat Viet Nam THAT (khong phai synthetic) - corpus chinh cua\n"
    "du an graph-rag-legal-qa (toan bo ~61k/67k van ban, xem constitution.md).\n\n"
    "Query + nhan lien quan (qrels) THAT di kem duoc ghi rieng vao\n"
    "scripts/quality_fixtures/gold_set_zalo.json - dung de do Recall@k/MRR\n"
    "that qua scripts/eval_graph_recall.py.\n"
)


def slugify_id(doc_id: str) -> str:
    return re.sub(r"[^\w-]", "_", str(doc_id))[:80]


def _write_doc(out_dir: str, doc_id: str, title: str, text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    filename = f"{slugify_id(doc_id)}.md"
    title = (title or "").strip()
    content = f"# {title}\n\n{text}\n" if title else text + "\n"
    with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
        f.write(content)
    return filename


def _build_gold_set(queries: dict, qrels, id_to_filename: dict) -> tuple[list, int]:
    gold_set = []
    skipped = 0
    for row in qrels:
        qid = str(row.get("query-id") or row.get("query_id"))
        cid = str(row.get("corpus-id") or row.get("corpus_id"))
        question = queries.get(qid)
        filename = id_to_filename.get(cid)
        if not question or not filename:
            skipped += 1
            continue
        gold_set.append(
            {
                "id": f"zalo-{qid}",
                "question": question,
                "expected_source_file": filename,
                "expected_corpus_id": cid,
            }
        )
    return gold_set, skipped


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default=OUTPUT_DEFAULT, help="Thu muc ghi corpus (.md)")
    parser.add_argument(
        "--gold-out", type=str, default=GOLD_SET_OUT_DEFAULT, help="File JSON ghi gold set (query+qrels that)"
    )
    parser.add_argument(
        "--max-docs", type=int, default=None,
        help="(che do FULL, bo qua neu dung --subset-size) Chi lay N doc DAU TIEN trong corpus - "
             "KHONG dam bao gold set con du van ban, chi dung de test nhanh."
    )
    parser.add_argument(
        "--subset-size", type=int, default=None,
        help="TUY CHON, CHI de test cuc bo (khong phai duong di mac dinh cua du an nay - "
             "constitution.md da chot toan bo 67k van ban cho ingest that). Neu dat: CHI ghi ra "
             "dung N van ban - uu tien toan bo van ban gold set (qrels) can, them van ban nhieu "
             "ngau nhien cho du N. Xem doc string dau file."
    )
    parser.add_argument("--seed", type=int, default=42, help="Seed random khi chon van ban nhieu cho --subset-size.")
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        from datasets import load_dataset
    except ImportError:
        print("Thieu thu vien `datasets`. Cai bang: pip install datasets", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "README.md"), "w", encoding="utf-8") as f:
        f.write(LICENSE_NOTE)

    id_to_filename: dict[str, str] = {}
    written = 0

    if args.subset_size:
        print("Che do --subset-size (CHI test cuc bo): tai 'queries' + 'qrels' TRUOC de biet corpus-id nao gold set can...")
        queries = {
            str(row.get("_id") or row.get("id")): row["text"]
            for row in load_dataset(HF_DATASET, "queries", split="test")
        }
        qrels = list(load_dataset(HF_DATASET, "qrels", split="test"))
        needed_ids = {str(row.get("corpus-id") or row.get("corpus_id")) for row in qrels}
        print(f"Gold set can {len(needed_ids)} van ban duy nhat (tu {len(qrels)} cap qrels).")

        # INCREMENTAL: giu nguyen file .md DA CO SAN tu lan chay truoc
        # (khong ghi de/xoa) - chi ghi THEM file con thieu de dat du
        # args.subset_size. Ly do quan trong hon ca tiet kiem I/O ghi dia
        # (von da re): file KHONG DOI NOI DUNG -> content_hash khong doi ->
        # app/ingest.py (co che incremental theo hash) se TU DONG BO QUA
        # embed lai file do - day la phan DAT nhat (BGE-m3 tren CPU), khong
        # phai ghi file .md.
        existing_files = {
            f for f in os.listdir(args.out) if f.endswith(".md") and f != "README.md"
        }
        print(f"Da co san {len(existing_files)} file .md trong {args.out} tu truoc - se GIU "
              f"NGUYEN (khong dong den), chi tai + ghi them phan con thieu.")

        print(f"Dang tai subset 'corpus' tu {HF_DATASET} (van phai tai ca ~61k dong qua mang de "
              f"biet full danh sach - khong tranh duoc buoc tai nay dua tren API cua thu vien "
              f"`datasets`, chi tranh duoc phan GHI DIA + EMBED LAI file da co san)...")
        corpus = load_dataset(HF_DATASET, "corpus", split="test")

        needed_rows = []
        new_distractor_candidates = []
        existing_distractor_count = 0
        for row in corpus:
            doc_id = str(row.get("_id") or row.get("id"))
            if doc_id in needed_ids:
                needed_rows.append(row)
                continue
            expected_filename = f"{slugify_id(doc_id)}.md"
            if expected_filename in existing_files:
                existing_distractor_count += 1
            else:
                new_distractor_candidates.append(row)

        distractor_budget_total = max(0, args.subset_size - len(needed_ids))
        still_need = max(0, distractor_budget_total - existing_distractor_count)
        rng = random.Random(args.seed)
        new_distractors = rng.sample(new_distractor_candidates, min(still_need, len(new_distractor_candidates)))

        total_after = len(needed_ids) + existing_distractor_count + len(new_distractors)
        print(f"Muc tieu: {args.subset_size} van ban. Da co san {existing_distractor_count} van "
              f"ban nhieu (giu nguyen) + {len(needed_ids)} van ban bat buoc. Can ghi THEM "
              f"{len(new_distractors)} van ban nhieu moi -> tong sau khi xong: ~{total_after} "
              f"van ban (needed_rows ghi de idempotent - noi dung khong doi neu doc_id khong doi).")

        for row in needed_rows + new_distractors:
            doc_id = str(row.get("_id") or row.get("id") or written)
            filename = _write_doc(args.out, doc_id, row.get("title"), row.get("text"))
            if filename is None:
                continue
            id_to_filename[doc_id] = filename
            written += 1
            if written % 500 == 0:
                print(f"  ... da ghi {written} file")

        print(f"Da ghi/cap nhat {written} file trong lan chay nay ({existing_distractor_count} "
              f"file nhieu cu KHONG bi dong den) vao {args.out} (che do subset).")

    else:
        print(f"Che do FULL (mac dinh - dung cho ingest that): dang tai subset 'corpus' tu "
              f"{HF_DATASET} (co the mat vai phut lan dau)...")
        corpus = load_dataset(HF_DATASET, "corpus", split="test")
        if args.max_docs:
            corpus = corpus.select(range(min(args.max_docs, len(corpus))))

        for row in corpus:
            doc_id = str(row.get("_id") or row.get("id") or written)
            filename = _write_doc(args.out, doc_id, row.get("title"), row.get("text"))
            if filename is None:
                continue
            id_to_filename[doc_id] = filename
            written += 1
            if written % 5000 == 0:
                print(f"  ... da ghi {written} file")

        print(f"Da ghi {written} van ban luat that vao {args.out}")

        print("Dang tai subset 'queries' + 'qrels' (gold set that)...")
        queries = {
            str(row.get("_id") or row.get("id")): row["text"]
            for row in load_dataset(HF_DATASET, "queries", split="test")
        }
        qrels = load_dataset(HF_DATASET, "qrels", split="test")

    gold_set, skipped = _build_gold_set(queries, qrels, id_to_filename)

    os.makedirs(os.path.dirname(args.gold_out), exist_ok=True)
    with open(args.gold_out, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": HF_DATASET,
                "license": "MIT",
                "description": (
                    "Gold set THAT (khong tu viet tay) tu Zalo AI Challenge 2021 "
                    "Legal Text Retrieval qua MTEB - moi item la 1 cau hoi that + "
                    "file .md (trong data/raw/legal_real/) chua cau tra loi lien quan that."
                ),
                "note_ve_matching": (
                    "Dung expected_source_file (so khop theo NGUON file, khong phai chuoi "
                    "con) - vi day la retrieval benchmark chuan (query -> dung DOC nao, "
                    "khong phai dung CAU nao trong doc). Khi do Recall@k, so sanh "
                    "doc.metadata['source'] cua ket qua retrieve voi expected_source_file."
                ),
                "gold_set": gold_set,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Da ghi {len(gold_set)} cap query-doc that vao {args.gold_out} (bo qua {skipped} cap thieu du lieu).")
    print("\nBuoc tiep theo:")
    print("  1. python -m app.ingest data/raw/legal_real   (ingest corpus vua ghi, batch + savepoint)")
    print("  2. python scripts/eval_graph_recall.py         (do Recall@k/MRR that - T017)")


if __name__ == "__main__":
    main()
