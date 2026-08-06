"""Tests cho app/extraction/relation_llm.py (T013): rule-based candidate
narrowing (find_relation_candidates) + LLM classification
(classify_candidate/_call_ollama) cho AMENDS/SUPERSEDES/CONFLICTS_WITH
(data-model.md).

Theo dung TIEN_DO.md muc "Viec can lam tiep theo" #2 - pham vi P1 CHI xu
ly candidate co TEN VAN BAN DICH ro rang trong CHINH cau chua trich dan
(tai dung reference_extractor.extract_references, khong duplicate regex) -
truong hop khong neu ten van ban (chi biet qua Document.title dang rong)
BI LOAI, khong phai bug (xem test_*_self_document_citation_excluded).

Pattern mock LLM giong tests/serving/test_api.py: monkeypatch
`relation_llm._call_ollama` cho test classify_candidate (khong goi Ollama
that), test rieng cho `_call_ollama` xac nhan dung API shape qua
monkeypatch httpx.post.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.extraction import relation_llm
from app.extraction.relation_llm import (
    ExtractedRelation,
    RelationCandidate,
    classify_candidate,
    find_relation_candidates,
)

# --- find_relation_candidates (rule-based candidate narrowing) -------------


def test_amends_trigger_with_cross_doc_citation_produces_candidate():
    text = "Điều 5 Luật Doanh nghiệp 2020 được sửa đổi, bổ sung như sau:"
    candidates = find_relation_candidates(text, current_doc_slug="luat-xyz")

    assert len(candidates) == 1
    assert candidates[0].target_article_id == "luat-doanh-nghiep-2020_dieu-5"
    assert candidates[0].relationship_type_hint == "AMENDS"


def test_supersedes_trigger_with_cross_doc_citation_produces_candidate():
    text = "Điều 10 Nghị định 123/2020/NĐ-CP được thay thế bởi quy định mới."
    candidates = find_relation_candidates(text, current_doc_slug="luat-xyz")

    assert len(candidates) == 1
    assert candidates[0].target_article_id == "nghi-dinh-123-2020-nd-cp_dieu-10"
    assert candidates[0].relationship_type_hint == "SUPERSEDES"


def test_conflicts_with_trigger_with_cross_doc_citation_produces_candidate():
    text = "Điều 8 Luật Đầu tư 2020 hết hiệu lực kể từ ngày văn bản này có hiệu lực."
    candidates = find_relation_candidates(text, current_doc_slug="luat-xyz")

    assert len(candidates) == 1
    assert candidates[0].target_article_id == "luat-dau-tu-2020_dieu-8"
    assert candidates[0].relationship_type_hint == "CONFLICTS_WITH"


def test_trigger_without_citation_produces_no_candidate():
    text = "Văn bản này sửa đổi, bổ sung một số điều của các văn bản liên quan."
    candidates = find_relation_candidates(text, current_doc_slug="luat-xyz")

    assert candidates == []


def test_citation_without_trigger_produces_no_candidate():
    text = "...theo quy định tại Điều 5 Luật Doanh nghiệp 2020..."
    candidates = find_relation_candidates(text, current_doc_slug="luat-xyz")

    assert candidates == []


def test_self_document_citation_with_trigger_is_excluded():
    """Trich dan KHONG neu ten van ban (tu tham chieu, resolve ve
    current_doc_slug) - ngay ca khi co trigger, bi loai (Document.title
    dang rong, khong the xac nhan day co thuc su la quan he lien-van-ban
    hay khong - xem TIEN_DO.md, khong doan bua)."""
    text = "Điều 5 được sửa đổi, bổ sung như sau: ..."
    candidates = find_relation_candidates(text, current_doc_slug="luat-xyz")

    assert candidates == []


def test_duplicate_target_across_sentences_deduped_keep_first():
    text = (
        "Điều 5 Luật Doanh nghiệp 2020 được sửa đổi, bổ sung như sau: nội dung mới.\n"
        "Điều 5 Luật Doanh nghiệp 2020 cũng bị bãi bỏ một phần."
    )
    candidates = find_relation_candidates(text, current_doc_slug="luat-xyz")

    assert len(candidates) == 1
    assert candidates[0].relationship_type_hint == "AMENDS"


def test_no_trigger_no_citation_returns_empty_list():
    text = "Đây là một đoạn văn bản bình thường, không có gì đặc biệt."
    candidates = find_relation_candidates(text, current_doc_slug="luat-xyz")

    assert candidates == []


# --- classify_candidate / _parse_llm_response (LLM confirmation) -----------


def _make_candidate() -> RelationCandidate:
    return RelationCandidate(
        target_article_id="luat-doanh-nghiep-2020_dieu-5",
        relationship_type_hint="AMENDS",
        trigger_keyword="sửa đổi, bổ sung",
        sentence="Điều 5 Luật Doanh nghiệp 2020 được sửa đổi, bổ sung như sau:",
    )


def test_classify_candidate_returns_extracted_relation_on_valid_json(monkeypatch):
    mock_call_ollama = MagicMock(
        return_value=(
            '{"relationship_type": "AMENDS", "confidence": 0.9, '
            '"ly_do": "câu nêu rõ sửa đổi, bổ sung Điều 5"}'
        )
    )
    monkeypatch.setattr(relation_llm, "_call_ollama", mock_call_ollama)

    result = classify_candidate("luat-xyz_dieu-1", _make_candidate())

    assert result == ExtractedRelation(
        target_article_id="luat-doanh-nghiep-2020_dieu-5",
        relationship_type="AMENDS",
        confidence=0.9,
        ly_do="câu nêu rõ sửa đổi, bổ sung Điều 5",
    )
    mock_call_ollama.assert_called_once()


def test_classify_candidate_returns_none_when_relationship_type_is_none(monkeypatch):
    """LLM tu xac nhan cau nay KHONG thuc su the hien quan he (candidate
    rule-based chi la goi y, LLM la nguon quyet dinh cuoi cung -
    data-model.md)."""
    mock_call_ollama = MagicMock(
        return_value=(
            '{"relationship_type": "NONE", "confidence": 0.1, "ly_do": "không rõ ràng"}'
        )
    )
    monkeypatch.setattr(relation_llm, "_call_ollama", mock_call_ollama)

    result = classify_candidate("luat-xyz_dieu-1", _make_candidate())

    assert result is None


def test_classify_candidate_returns_none_on_malformed_json(monkeypatch, caplog):
    mock_call_ollama = MagicMock(return_value="đây không phải JSON hợp lệ")
    monkeypatch.setattr(relation_llm, "_call_ollama", mock_call_ollama)

    result = classify_candidate("luat-xyz_dieu-1", _make_candidate())

    assert result is None


def test_classify_candidate_returns_none_when_relationship_type_invalid(monkeypatch):
    """LLM tra ve mot loai quan he ngoai 3 loai da chot (data-model.md) -
    khong tin tuong mu quang, coi nhu khong xac nhan duoc."""
    mock_call_ollama = MagicMock(
        return_value='{"relationship_type": "FOO", "confidence": 0.9, "ly_do": "x"}'
    )
    monkeypatch.setattr(relation_llm, "_call_ollama", mock_call_ollama)

    result = classify_candidate("luat-xyz_dieu-1", _make_candidate())

    assert result is None


def test_classify_candidate_strips_markdown_code_fence_before_parsing(monkeypatch):
    """Ollama doi khi boc JSON trong ```json ... ``` du prompt yeu cau
    khong lam vay - xu ly thuc te thay vi gia dinh output luon sach."""
    mock_call_ollama = MagicMock(
        return_value=(
            '```json\n{"relationship_type": "SUPERSEDES", "confidence": 0.75, '
            '"ly_do": "thay thế toàn bộ nội dung"}\n```'
        )
    )
    monkeypatch.setattr(relation_llm, "_call_ollama", mock_call_ollama)

    result = classify_candidate("luat-xyz_dieu-1", _make_candidate())

    assert result is not None
    assert result.relationship_type == "SUPERSEDES"
    assert result.confidence == 0.75


# --- _call_ollama - API shape (giong tests/serving/test_api.py) ------------


def test_call_ollama_posts_to_generate_endpoint_and_parses_response_field(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "cau tra loi that", "done": True}
    mock_response.raise_for_status = MagicMock()
    mock_post = MagicMock(return_value=mock_response)
    monkeypatch.setattr(relation_llm.httpx, "post", mock_post)
    monkeypatch.setattr(relation_llm.config, "OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(relation_llm.config, "OLLAMA_MODEL", "qwen2.5:7b-instruct")

    result = relation_llm._call_ollama("mot prompt test")

    assert result == "cau tra loi that"
    mock_post.assert_called_once_with(
        "http://localhost:11434/api/generate",
        json={
            "model": "qwen2.5:7b-instruct",
            "prompt": "mot prompt test",
            "stream": False,
        },
        timeout=relation_llm._OLLAMA_TIMEOUT_SECONDS,
    )


def test_call_ollama_raises_on_http_error(monkeypatch):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "boom", request=MagicMock(), response=MagicMock()
    )
    monkeypatch.setattr(relation_llm.httpx, "post", MagicMock(return_value=mock_response))

    with pytest.raises(httpx.HTTPStatusError):
        relation_llm._call_ollama("mot prompt test")
