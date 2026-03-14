"""Tests for RAG service — ChromaDB-backed vector search."""

import pytest

from app.services.rag import RAGService


@pytest.fixture
def rag(tmp_path):
    """Provide a RAGService backed by a temporary ChromaDB directory."""
    return RAGService(persist_path=str(tmp_path / "chromadb"))


@pytest.fixture
def sample_chunks():
    """Sample chunks mimicking processed manual content."""
    return [
        {
            "text": "To change the oil, first warm up the engine for 5 minutes.",
            "metadata": {"chunk_index": 0, "page": 42, "section": "Maintenance"},
        },
        {
            "text": "Use SAE 5W-30 oil for best performance in most climates.",
            "metadata": {"chunk_index": 1, "page": 42, "section": "Maintenance"},
        },
        {
            "text": "The brake pads should be inspected every 20,000 miles.",
            "metadata": {"chunk_index": 2, "page": 55, "section": "Brakes"},
        },
    ]


@pytest.fixture
def other_chunks():
    """Chunks belonging to a different manual."""
    return [
        {
            "text": "Check tire pressure monthly and before long trips.",
            "metadata": {"chunk_index": 0, "page": 30, "section": "Tires"},
        },
        {
            "text": "Rotate tires every 7,500 miles for even wear.",
            "metadata": {"chunk_index": 1, "page": 31, "section": "Tires"},
        },
    ]


def test_index_chunks_returns_count(rag, sample_chunks):
    """index_chunks() returns the number of chunks indexed."""
    count = rag.index_chunks("manual_1", sample_chunks)
    assert count == 3


def test_index_chunks_stores_documents(rag, sample_chunks):
    """After indexing, collection count matches chunk count."""
    rag.index_chunks("manual_1", sample_chunks)
    collection = rag._collection
    assert collection.count() == 3


def test_search_returns_results(rag, sample_chunks):
    """search(query) returns list of dicts with text, metadata, distance."""
    rag.index_chunks("manual_1", sample_chunks)
    results = rag.search("how to change oil")
    assert len(results) > 0

    first = results[0]
    assert "text" in first
    assert "metadata" in first
    assert "distance" in first
    assert isinstance(first["text"], str)
    assert isinstance(first["metadata"], dict)
    assert isinstance(first["distance"], float)


def test_search_with_manual_id_filter(rag, sample_chunks, other_chunks):
    """search(query, manual_id='X') only returns chunks from manual X."""
    rag.index_chunks("manual_1", sample_chunks)
    rag.index_chunks("manual_2", other_chunks)

    results = rag.search("maintenance", manual_id="manual_1")
    for r in results:
        assert r["metadata"]["manual_id"] == "manual_1"

    results = rag.search("tires", manual_id="manual_2")
    for r in results:
        assert r["metadata"]["manual_id"] == "manual_2"


def test_search_top_k_limits_results(rag, sample_chunks):
    """search(query, top_k=2) returns at most 2 results."""
    rag.index_chunks("manual_1", sample_chunks)
    results = rag.search("oil change brakes maintenance", top_k=2)
    assert len(results) <= 2


def test_search_empty_collection(rag):
    """search() on empty collection returns empty list."""
    results = rag.search("anything at all")
    assert results == []


def test_delete_manual_removes_chunks(rag, sample_chunks):
    """After delete_manual(id), those chunks no longer appear in search."""
    rag.index_chunks("manual_1", sample_chunks)
    assert rag._collection.count() == 3

    rag.delete_manual("manual_1")
    assert rag._collection.count() == 0

    results = rag.search("oil change")
    assert results == []


def test_delete_manual_preserves_others(rag, sample_chunks, other_chunks):
    """Deleting manual A doesn't affect manual B's chunks."""
    rag.index_chunks("manual_1", sample_chunks)
    rag.index_chunks("manual_2", other_chunks)
    assert rag._collection.count() == 5

    rag.delete_manual("manual_1")
    assert rag._collection.count() == 2

    results = rag.search("tire pressure")
    assert len(results) > 0
    for r in results:
        assert r["metadata"]["manual_id"] == "manual_2"
