"""Tests cho app/serving/api.py (T014, POST /chat).

Khong co Ollama/Neo4j/Chroma that trong cac test nay - mock o ranh gioi
(cung quy uoc "honest mocking" nhu tests/retrieval/test_traversal.py mock
Neo4jClient.run, tests/retrieval/test_entry_point.py mock embed_texts/
Chroma): mock `find_entry_points`, `traverse`, `embedder.get_texts`,
`Neo4jClient`, va `_call_ollama` (helper Ollama-calling da tach rieng khoi
route handler, xem docstring api.py). Endpoint nay khong duoc phep goi
mang that toi Ollama/Neo4j trong unit test.

Cac case theo task-3e-brief.md:
  1. Khong tim duoc entry point nao -> tra loi "khong tim thay" ro rang,
     `traverse`/`Neo4jClient`/`_call_ollama` KHONG duoc goi (early-return
     that su, khong phai tinh co dung).
  2. Truong hop binh thuong: entry point + traversal nho, TAT CA article
     da duoc embed (nhom 2) -> ngu canh dung dung noi dung that, prompt gui
     cho Ollama chua noi dung cac article, response co citation_path/
     edges_used khop voi traversal result.
  3. Mot article `is_external=True` trong traversal result -> noi dung
     KHONG duoc gui cho LLM nhu that (chi co marker "khong co du lieu"),
     va citation_path phan anh `is_external: true`.
  4. Mot article that, khong external, nhung KHONG co trong ket qua mock
     cua `embedder.get_texts` (mo phong "chua duoc embed") -> fallback ve
     preview tu Neo4j, khong crash, khong bi coi la external.
  5. `_call_ollama` rieng: xac nhan goi dung `/api/generate` voi
     model/prompt/stream=false, va parse dung truong "response" tu JSON
     tra ve - khop API shape THAT da verify tren Ollama that dang chay o
     may nay (xem module docstring api.py).
"""
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.retrieval.entry_point import EntryPointResult
from app.retrieval.traversal import TraversalEdge, TraversalResult
from app.serving import api


class _FakeNeo4jClient:
    """Context manager gia lap cho `Neo4jClient` - `run` la MagicMock de
    test kiem tra duoc query/tham so gui di, tra ve `rows` da chuan bi san
    (mo phong ket qua `_MISSING_ARTICLE_INFO_QUERY`)."""

    def __init__(self, rows: list[dict] | None = None):
        self.run = MagicMock(return_value=rows or [])

    def __enter__(self) -> "_FakeNeo4jClient":
        return self

    def __exit__(self, *args) -> None:
        return None


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(api.app)


# --- Case 1: khong co entry point -------------------------------------------


def test_no_entry_points_returns_graceful_answer_without_traversal_or_ollama(
    monkeypatch, test_client
):
    monkeypatch.setattr(api, "find_entry_points", MagicMock(return_value=[]))
    mock_traverse = MagicMock()
    monkeypatch.setattr(api, "traverse", mock_traverse)
    mock_call_ollama = MagicMock()
    monkeypatch.setattr(api, "_call_ollama", mock_call_ollama)
    # Cac test nay kiem tra luong KHONG rerank (mock find_entry_points/get_texts
    # co dinh); tat rerank de khong tai cross-encoder that. Rerank co test rieng.
    monkeypatch.setattr(api.config, "RERANK_ENABLED", False)
    mock_neo4j_cls = MagicMock()
    monkeypatch.setattr(api, "Neo4jClient", mock_neo4j_cls)

    response = test_client.post("/chat", json={"question": "cau hoi khong lien quan"})

    assert response.status_code == 200
    body = response.json()
    assert body["citation_path"] == []
    assert body["edges_used"] == []
    assert "không tìm thấy" in body["answer"].lower()

    mock_traverse.assert_not_called()
    mock_call_ollama.assert_not_called()
    mock_neo4j_cls.assert_not_called()


# --- Case 2: truong hop binh thuong, tat ca da embed ------------------------


def test_normal_case_all_embedded_builds_context_and_returns_citation_path(
    monkeypatch, test_client
):
    monkeypatch.setattr(
        api,
        "find_entry_points",
        MagicMock(return_value=[EntryPointResult(article_id="art_1", similarity=0.9)]),
    )
    traversal_result = TraversalResult(
        visited_article_ids={"art_1", "art_2"},
        edges=[TraversalEdge("art_1", "art_2", "REFERENCES")],
        external_article_ids=set(),
        visited_term_ids=set(),
    )
    monkeypatch.setattr(api, "traverse", MagicMock(return_value=traversal_result))
    monkeypatch.setattr(
        api.embedder,
        "get_texts",
        MagicMock(
            return_value={
                "art_1": "Noi dung day du cua Dieu 1 ve nghi phep nam.",
                "art_2": "Noi dung day du cua Dieu 2 duoc Dieu 1 tham chieu toi.",
            }
        ),
    )
    fake_client = _FakeNeo4jClient()
    monkeypatch.setattr(api, "Neo4jClient", lambda *a, **kw: fake_client)
    mock_call_ollama = MagicMock(return_value="cau tra loi mo phong")
    monkeypatch.setattr(api, "_call_ollama", mock_call_ollama)
    # Cac test nay kiem tra luong KHONG rerank (mock find_entry_points/get_texts
    # co dinh); tat rerank de khong tai cross-encoder that. Rerank co test rieng.
    monkeypatch.setattr(api.config, "RERANK_ENABLED", False)

    response = test_client.post("/chat", json={"question": "nghi phep nam the nao?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "cau tra loi mo phong"
    assert body["citation_path"] == [
        {"article_id": "art_1", "is_entry_point": True, "is_external": False, "is_preview": False},
        {"article_id": "art_2", "is_entry_point": False, "is_external": False, "is_preview": False},
    ]
    assert body["edges_used"] == [
        {"from_article_id": "art_1", "to_id": "art_2", "relationship_type": "REFERENCES"}
    ]

    # khong can query Neo4j bo sung - ca hai article deu da co trong texts
    fake_client.run.assert_not_called()

    mock_call_ollama.assert_called_once()
    prompt = mock_call_ollama.call_args.args[0]
    assert "Noi dung day du cua Dieu 1 ve nghi phep nam." in prompt
    assert "Noi dung day du cua Dieu 2 duoc Dieu 1 tham chieu toi." in prompt
    assert "art_1" in prompt
    assert "art_2" in prompt


# --- Case 3: article is_external=True ---------------------------------------


def test_external_article_content_not_sent_to_llm_and_marked_in_citation_path(
    monkeypatch, test_client
):
    monkeypatch.setattr(
        api,
        "find_entry_points",
        MagicMock(return_value=[EntryPointResult(article_id="art_1", similarity=0.9)]),
    )
    traversal_result = TraversalResult(
        visited_article_ids={"art_1", "art_ext"},
        edges=[TraversalEdge("art_1", "art_ext", "REFERENCES")],
        external_article_ids={"art_ext"},
        visited_term_ids=set(),
    )
    monkeypatch.setattr(api, "traverse", MagicMock(return_value=traversal_result))
    monkeypatch.setattr(
        api.embedder,
        "get_texts",
        MagicMock(return_value={"art_1": "Noi dung that cua Dieu 1."}),
    )
    fake_client = _FakeNeo4jClient(
        rows=[
            {
                "article_id": "art_ext",
                "is_external": True,
                "noi_dung_preview": None,
            }
        ]
    )
    monkeypatch.setattr(api, "Neo4jClient", lambda *a, **kw: fake_client)
    mock_call_ollama = MagicMock(return_value="cau tra loi mo phong")
    monkeypatch.setattr(api, "_call_ollama", mock_call_ollama)
    # Cac test nay kiem tra luong KHONG rerank (mock find_entry_points/get_texts
    # co dinh); tat rerank de khong tai cross-encoder that. Rerank co test rieng.
    monkeypatch.setattr(api.config, "RERANK_ENABLED", False)

    response = test_client.post("/chat", json={"question": "cau hoi"})

    assert response.status_code == 200
    body = response.json()
    citation_by_id = {c["article_id"]: c for c in body["citation_path"]}
    assert citation_by_id["art_ext"]["is_external"] is True
    assert citation_by_id["art_ext"]["is_preview"] is False
    assert citation_by_id["art_1"]["is_external"] is False

    # Neo4j duoc goi batched CHI cho id khong co trong texts (art_ext)
    fake_client.run.assert_called_once()
    _, run_kwargs = fake_client.run.call_args
    assert run_kwargs["ids"] == ["art_ext"]

    prompt = mock_call_ollama.call_args.args[0]
    assert "art_ext" in prompt
    assert "KHÔNG có trong dữ liệu đã ingest" in prompt
    # khong bao gio bia noi dung that cho article external (khong co du
    # lieu gi de bia ngoai marker)
    assert "None" not in prompt


# --- Case 4: article that, khong external, chua duoc embed -----------------


def test_not_yet_embedded_article_falls_back_to_neo4j_preview(monkeypatch, test_client):
    monkeypatch.setattr(
        api,
        "find_entry_points",
        MagicMock(return_value=[EntryPointResult(article_id="art_1", similarity=0.9)]),
    )
    traversal_result = TraversalResult(
        visited_article_ids={"art_1", "art_not_embedded"},
        edges=[TraversalEdge("art_1", "art_not_embedded", "REFERENCES")],
        external_article_ids=set(),
        visited_term_ids=set(),
    )
    monkeypatch.setattr(api, "traverse", MagicMock(return_value=traversal_result))
    monkeypatch.setattr(
        api.embedder,
        "get_texts",
        MagicMock(return_value={"art_1": "Noi dung that cua Dieu 1."}),
    )
    fake_client = _FakeNeo4jClient(
        rows=[
            {
                "article_id": "art_not_embedded",
                "is_external": False,
                "noi_dung_preview": "Tom tat ngan gon cua Dieu chua embed.",
            }
        ]
    )
    monkeypatch.setattr(api, "Neo4jClient", lambda *a, **kw: fake_client)
    mock_call_ollama = MagicMock(return_value="cau tra loi mo phong")
    monkeypatch.setattr(api, "_call_ollama", mock_call_ollama)
    # Cac test nay kiem tra luong KHONG rerank (mock find_entry_points/get_texts
    # co dinh); tat rerank de khong tai cross-encoder that. Rerank co test rieng.
    monkeypatch.setattr(api.config, "RERANK_ENABLED", False)

    response = test_client.post("/chat", json={"question": "cau hoi"})

    assert response.status_code == 200
    body = response.json()
    citation_by_id = {c["article_id"]: c for c in body["citation_path"]}
    # KHONG duoc coi la external - day la noi dung that, chi la chua embed
    assert citation_by_id["art_not_embedded"]["is_external"] is False
    # nhung PHAI duoc danh dau la preview (rut gon) de nguoi goi biet do la
    # noi dung it tin cay hon full text - day chinh la finding review vua sua
    assert citation_by_id["art_not_embedded"]["is_preview"] is True
    assert citation_by_id["art_1"]["is_preview"] is False

    prompt = mock_call_ollama.call_args.args[0]
    assert "Tom tat ngan gon cua Dieu chua embed." in prompt
    assert "preview rút gọn" in prompt


# --- Case 5: _call_ollama - API shape that cua Ollama ------------------------


def test_call_ollama_posts_to_generate_endpoint_and_parses_response_field(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "model": "qwen2.5:7b-instruct",
        "response": "cau tra loi that",
        "done": True,
    }
    mock_response.raise_for_status = MagicMock()
    mock_post = MagicMock(return_value=mock_response)
    monkeypatch.setattr(api.httpx, "post", mock_post)
    monkeypatch.setattr(api.config, "OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(api.config, "OLLAMA_MODEL", "qwen2.5:7b-instruct")
    monkeypatch.setattr(api.config, "OLLAMA_NUM_CTX", 8192)
    monkeypatch.setattr(api.config, "OLLAMA_TEMPERATURE", 0.2)

    result = api._call_ollama("mot prompt test")

    assert result == "cau tra loi that"
    mock_post.assert_called_once_with(
        "http://localhost:11434/api/generate",
        json={
            "model": "qwen2.5:7b-instruct",
            "prompt": "mot prompt test",
            "stream": False,
            "options": {"num_ctx": 8192, "temperature": 0.2},
        },
        timeout=api._OLLAMA_TIMEOUT_SECONDS,
    )
    mock_response.raise_for_status.assert_called_once()


def test_call_ollama_raises_on_http_error(monkeypatch):
    """Khong nuot loi HTTP (vd Ollama khong reachable/model khong ton tai) -
    de FastAPI tra ve 500 ro rang thay vi tra loi im lang sai."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "boom", request=MagicMock(), response=MagicMock()
    )
    monkeypatch.setattr(api.httpx, "post", MagicMock(return_value=mock_response))

    with pytest.raises(httpx.HTTPStatusError):
        api._call_ollama("mot prompt test")


# === T028: gioi han ngu canh + dung THU TU XEP HANG ========================
# Sau khi them vector cap Khoan, so ung vien trung binh tang 6.0 -> 17.1
# Article/cau hoi. Do that tren 793 cau Zalo gold: recall bao hoa o muc cat 10
# (71.1% o k=4, 75.4% tu k=10 tro len), nen cat o 10 khong mat gi ma giam 41%
# ngu canh.
#
# BUG TIEM AN duoc sua cung luc: truoc day `_build_prompt`/citation_path sap
# theo `sorted(contexts)` - thu tu CHU CAI cua article_id, khong lien quan do
# lien quan. Chua lo ra vi khong ai cat; nhung khi da cat thi cat theo chu cai
# se giu 10 Dieu TUY Y.


def test_context_is_capped_at_max_context_articles(monkeypatch, test_client):
    monkeypatch.setattr(api.config, "MAX_CONTEXT_ARTICLES", 3)
    monkeypatch.setattr(
        api,
        "find_entry_points",
        MagicMock(return_value=[EntryPointResult(article_id="art_entry", similarity=0.9)]),
    )
    many = [f"art_t{i}" for i in range(10)]
    traversal_result = TraversalResult(
        visited_article_ids={"art_entry", *many},
        edges=[TraversalEdge("art_entry", t, "REFERENCES") for t in many],
        external_article_ids=set(),
        visited_term_ids=set(),
    )
    monkeypatch.setattr(api, "traverse", MagicMock(return_value=traversal_result))
    monkeypatch.setattr(
        api.embedder, "get_texts",
        MagicMock(return_value={aid: f"noi dung {aid}" for aid in ["art_entry", *many]}),
    )
    monkeypatch.setattr(api, "Neo4jClient", lambda *a, **kw: _FakeNeo4jClient())
    monkeypatch.setattr(api, "_call_ollama", MagicMock(return_value="tra loi"))

    body = test_client.post("/chat", json={"question": "cau hoi"}).json()

    assert len(body["citation_path"]) == 3, "khong cat theo MAX_CONTEXT_ARTICLES"


def test_capped_context_keeps_entry_point_and_ranked_order_not_alphabetical(
    monkeypatch, test_client
):
    # Entry point ten "zzz" (cuoi bang chu cai) PHAI duoc giu; Article traversal
    # ten "aaa" (dau bang chu cai) phai xuong sau. Neu con sap theo chu cai thi
    # test nay do.
    monkeypatch.setattr(api.config, "MAX_CONTEXT_ARTICLES", 2)
    monkeypatch.setattr(
        api,
        "find_entry_points",
        MagicMock(return_value=[EntryPointResult(article_id="zzz_entry", similarity=0.9)]),
    )
    traversal_result = TraversalResult(
        visited_article_ids={"zzz_entry", "aaa_first_edge", "bbb_second_edge"},
        edges=[
            TraversalEdge("zzz_entry", "aaa_first_edge", "REFERENCES"),
            TraversalEdge("zzz_entry", "bbb_second_edge", "REFERENCES"),
        ],
        external_article_ids=set(),
        visited_term_ids=set(),
    )
    monkeypatch.setattr(api, "traverse", MagicMock(return_value=traversal_result))
    monkeypatch.setattr(
        api.embedder, "get_texts",
        MagicMock(return_value={
            "zzz_entry": "noi dung entry",
            "aaa_first_edge": "noi dung canh 1",
            "bbb_second_edge": "noi dung canh 2",
        }),
    )
    monkeypatch.setattr(api, "Neo4jClient", lambda *a, **kw: _FakeNeo4jClient())
    monkeypatch.setattr(api, "_call_ollama", MagicMock(return_value="tra loi"))

    body = test_client.post("/chat", json={"question": "cau hoi"}).json()
    ids = [c["article_id"] for c in body["citation_path"]]

    assert ids == ["zzz_entry", "aaa_first_edge"], (
        "phai theo thu tu xep hang (entry point truoc), khong theo chu cai"
    )
    assert body["citation_path"][0]["is_entry_point"] is True


# --- Rerank path (P3): cross-encoder cham diem lai truoc khi cat ------------


def test_rerank_enabled_reorders_context_by_reranker(monkeypatch, test_client):
    """Khi RERANK_ENABLED, chat() phai goi rerank_ids va DUNG thu tu no tra ve
    (o day dao art_1<->art_2) lam thu tu ngu canh + citation_path."""
    monkeypatch.setattr(api.config, "RERANK_ENABLED", True)
    monkeypatch.setattr(
        api,
        "find_entry_points",
        MagicMock(return_value=[EntryPointResult(article_id="art_1", similarity=0.9)]),
    )
    traversal_result = TraversalResult(
        visited_article_ids={"art_1", "art_2"},
        edges=[TraversalEdge("art_1", "art_2", "REFERENCES")],
        external_article_ids=set(),
        visited_term_ids=set(),
    )
    monkeypatch.setattr(api, "traverse", MagicMock(return_value=traversal_result))
    monkeypatch.setattr(
        api.embedder,
        "get_texts",
        MagicMock(return_value={"art_1": "noi dung 1", "art_2": "noi dung 2"}),
    )
    # Reranker dao thu tu: art_2 dung dau (giu la ung vien lien quan nhat).
    mock_rerank = MagicMock(return_value=["art_2", "art_1"])
    monkeypatch.setattr(api, "rerank_ids", mock_rerank)
    monkeypatch.setattr(api, "Neo4jClient", lambda *a, **kw: _FakeNeo4jClient())
    monkeypatch.setattr(api, "_call_ollama", MagicMock(return_value="tra loi"))

    body = test_client.post("/chat", json={"question": "cau hoi"}).json()

    mock_rerank.assert_called_once()
    # citation_path theo THU TU RERANK: art_2 truoc art_1.
    assert [c["article_id"] for c in body["citation_path"]] == ["art_2", "art_1"]
    # art_1 van la entry point du bi xep sau boi reranker.
    art1 = next(c for c in body["citation_path"] if c["article_id"] == "art_1")
    assert art1["is_entry_point"] is True
