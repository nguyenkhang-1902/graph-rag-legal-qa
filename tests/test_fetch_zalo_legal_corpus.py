"""Tests cho scripts/fetch_zalo_legal_corpus.py (T003).

Chi test CLI arg parsing + logic thuan Python (slugify_id, _write_doc,
_build_gold_set) - KHONG goi mang / Hugging Face (script that chay tren
may that, xem docstring cua file). Muc tieu chinh: khoa lai hanh vi "mac
dinh = fetch toan bo corpus, khong co gioi han an" (constitution.md da
chot toan bo 67k van ban).

`scripts/` khong co `__init__.py` (khong phai package, theo plan.md) nen
module duoc load truc tiep tu duong dan file bang importlib.
"""
import importlib.util
import json
import os
import sys

SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "fetch_zalo_legal_corpus.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("fetch_zalo_legal_corpus", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def test_default_args_fetch_entire_corpus_no_cap():
    """Khong truyen --subset-size / --max-docs -> ca hai la None, tuc
    khong co gioi han an nao cat bot corpus (che do FULL mac dinh)."""
    parser = mod.build_arg_parser()
    args = parser.parse_args([])
    assert args.subset_size is None
    assert args.max_docs is None


def test_subset_size_is_opt_in_only():
    parser = mod.build_arg_parser()
    args = parser.parse_args(["--subset-size", "2000"])
    assert args.subset_size == 2000


def test_out_and_gold_out_default_paths_are_set():
    parser = mod.build_arg_parser()
    args = parser.parse_args([])
    assert args.out == mod.OUTPUT_DEFAULT
    assert args.gold_out == mod.GOLD_SET_OUT_DEFAULT
    assert args.seed == 42


def test_slugify_id_replaces_non_word_chars():
    assert mod.slugify_id("abc/def:123") == "abc_def_123"


def test_slugify_id_truncates_to_80_chars():
    long_id = "a" * 200
    result = mod.slugify_id(long_id)
    assert len(result) == 80


def test_write_doc_skips_empty_text(tmp_path):
    result = mod._write_doc(str(tmp_path), "doc1", "Title", "   ")
    assert result is None
    assert not os.listdir(tmp_path)


def test_write_doc_writes_file_with_title(tmp_path):
    filename = mod._write_doc(str(tmp_path), "doc1", "Tieu de", "Noi dung that.")
    assert filename == "doc1.md"
    content = (tmp_path / filename).read_text(encoding="utf-8")
    assert content == "# Tieu de\n\nNoi dung that.\n"


def test_write_doc_writes_file_without_title(tmp_path):
    filename = mod._write_doc(str(tmp_path), "doc2", "", "Noi dung khong tieu de.")
    content = (tmp_path / filename).read_text(encoding="utf-8")
    assert content == "Noi dung khong tieu de.\n"


def test_build_gold_set_matches_and_skips_missing():
    queries = {"q1": "Cau hoi 1?", "q2": "Cau hoi 2?"}
    id_to_filename = {"c1": "c1.md"}
    qrels = [
        {"query-id": "q1", "corpus-id": "c1", "score": 1},
        {"query-id": "q2", "corpus-id": "c-missing", "score": 1},
    ]
    gold_set, skipped = mod._build_gold_set(queries, qrels, id_to_filename)
    assert skipped == 1
    assert len(gold_set) == 1
    assert gold_set[0] == {
        "id": "zalo-q1",
        "question": "Cau hoi 1?",
        "expected_source_file": "c1.md",
        "expected_corpus_id": "c1",
    }


def test_build_gold_set_output_is_json_serializable():
    queries = {"q1": "Cau hoi 1?"}
    id_to_filename = {"c1": "c1.md"}
    qrels = [{"query-id": "q1", "corpus-id": "c1", "score": 1}]
    gold_set, _ = mod._build_gold_set(queries, qrels, id_to_filename)
    json.dumps(gold_set, ensure_ascii=False)  # khong raise
