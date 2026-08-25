"""Tests bao ve TINH TOAN VEN quy trinh build (khong chay Neo4j/Chroma/mang):
danh muc URL + import orchestrator. Cac bug quy trinh (slug trung, che_do sai,
import gay) bi bat o day truoc khi chay build that."""
from scripts.fetch_bhxh_corpus import BHXH_CORPUS_URLS, _slug_from_url


def test_corpus_urls_have_unique_slugs():
    # Slug trung -> 2 van ban ghi de nhau tren dia -> mat du lieu am tham.
    slugs = [_slug_from_url(e["url"]) for e in BHXH_CORPUS_URLS]
    assert len(slugs) == len(set(slugs)), "co slug trung trong BHXH_CORPUS_URLS"


def test_corpus_entries_wellformed():
    for e in BHXH_CORPUS_URLS:
        assert e["url"].startswith("https://vbpl.vn/van-ban/chi-tiet/")
        assert "--" in e["url"], "URL phai la dang slug--id day du"
        assert isinstance(e["che_do"], list) and e["che_do"], "che_do phai la list khong rong"


def test_build_corpus_imports():
    # Import orchestrator - bat loi import/cu phap som.
    import scripts.build_corpus as bc
    assert hasattr(bc, "main") and hasattr(bc, "_ingest_from_disk")
