"""Tests cho app/config.py (T004).

Xac nhan: (1) gia tri mac dinh load dung khi khong co override qua env,
(2) override qua bien moi truong duoc doc dung kieu (int/float/str).

`app/config.py` doc os.environ o MODULE LEVEL (constants), nen test
override phai monkeypatch bien moi truong TRUOC roi importlib.reload
module - khong the chi gan lai bien Python sau khi import.
"""
import importlib

import app.config as config_module

CONFIG_ENV_VARS = [
    "MAX_HOP",
    "SIMILARITY_THRESHOLD",
    "INGEST_BATCH_SIZE",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "CHROMA_PERSIST_DIR",
    "CHROMA_COLLECTION_NAME",
    "EMBEDDING_MODEL",
    "EMBED_BATCH_SIZE",
]


def _reload_with_clean_env(monkeypatch):
    """Xoa het bien env lien quan (tranh phu thuoc vao .env that co the
    ton tai tren may dev), roi reload module de lay lai gia tri mac dinh."""
    for var in CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return importlib.reload(config_module)


def test_defaults_load_correctly(monkeypatch):
    cfg = _reload_with_clean_env(monkeypatch)

    assert cfg.MAX_HOP == 2
    assert isinstance(cfg.MAX_HOP, int)
    assert cfg.SIMILARITY_THRESHOLD == 0.75
    assert isinstance(cfg.SIMILARITY_THRESHOLD, float)
    assert cfg.INGEST_BATCH_SIZE == 200
    assert isinstance(cfg.INGEST_BATCH_SIZE, int)

    assert cfg.NEO4J_URI == "bolt://localhost:7687"
    assert cfg.NEO4J_USER == "neo4j"
    assert cfg.NEO4J_PASSWORD == "changeme"

    assert cfg.OLLAMA_BASE_URL == "http://localhost:11434"
    assert cfg.OLLAMA_MODEL == "qwen2.5:7b-instruct"

    assert cfg.CHROMA_PERSIST_DIR == "./chroma_db"
    assert cfg.CHROMA_COLLECTION_NAME == "legal_articles"

    assert cfg.EMBEDDING_MODEL == "BAAI/bge-m3"
    assert cfg.EMBED_BATCH_SIZE == 32
    assert isinstance(cfg.EMBED_BATCH_SIZE, int)


def test_max_hop_env_override_read_as_int(monkeypatch):
    _reload_with_clean_env(monkeypatch)
    monkeypatch.setenv("MAX_HOP", "3")
    cfg = importlib.reload(config_module)

    assert cfg.MAX_HOP == 3
    assert isinstance(cfg.MAX_HOP, int)


def test_similarity_threshold_env_override_read_as_float(monkeypatch):
    _reload_with_clean_env(monkeypatch)
    monkeypatch.setenv("SIMILARITY_THRESHOLD", "0.9")
    cfg = importlib.reload(config_module)

    assert cfg.SIMILARITY_THRESHOLD == 0.9
    assert isinstance(cfg.SIMILARITY_THRESHOLD, float)


def test_ingest_batch_size_env_override_read_as_int(monkeypatch):
    _reload_with_clean_env(monkeypatch)
    monkeypatch.setenv("INGEST_BATCH_SIZE", "500")
    cfg = importlib.reload(config_module)

    assert cfg.INGEST_BATCH_SIZE == 500
    assert isinstance(cfg.INGEST_BATCH_SIZE, int)


def test_neo4j_and_ollama_env_overrides_read_as_str(monkeypatch):
    _reload_with_clean_env(monkeypatch)
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j-host:7687")
    monkeypatch.setenv("NEO4J_USER", "custom_user")
    monkeypatch.setenv("NEO4J_PASSWORD", "s3cr3t")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama-host:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:8b")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", "/data/chroma")
    cfg = importlib.reload(config_module)

    assert cfg.NEO4J_URI == "bolt://neo4j-host:7687"
    assert cfg.NEO4J_USER == "custom_user"
    assert cfg.NEO4J_PASSWORD == "s3cr3t"
    assert cfg.OLLAMA_BASE_URL == "http://ollama-host:11434"
    assert cfg.OLLAMA_MODEL == "llama3:8b"
    assert cfg.CHROMA_PERSIST_DIR == "/data/chroma"


def test_embedding_env_overrides_read_as_str_and_int(monkeypatch):
    _reload_with_clean_env(monkeypatch)
    monkeypatch.setenv("CHROMA_COLLECTION_NAME", "custom_collection")
    monkeypatch.setenv("EMBEDDING_MODEL", "some/other-model")
    monkeypatch.setenv("EMBED_BATCH_SIZE", "64")
    cfg = importlib.reload(config_module)

    assert cfg.CHROMA_COLLECTION_NAME == "custom_collection"
    assert cfg.EMBEDDING_MODEL == "some/other-model"
    assert cfg.EMBED_BATCH_SIZE == 64
    assert isinstance(cfg.EMBED_BATCH_SIZE, int)


def teardown_module(module):
    """Reload mot lan cuoi voi env sach de khong ro ri state sang test khac
    chay sau trong cung tien trinh pytest (module-level singleton)."""
    for var in CONFIG_ENV_VARS:
        import os

        os.environ.pop(var, None)
    importlib.reload(config_module)
