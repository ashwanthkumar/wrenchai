"""RAG service — ChromaDB-backed vector search for car manuals."""

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


class RAGService:
    """Indexes manual chunks into ChromaDB and provides semantic search."""

    def __init__(self, persist_path: str) -> None:
        self._client = chromadb.PersistentClient(path=persist_path)
        self._embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self._collection = self._client.get_or_create_collection(
            name="car_manuals",
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def index_chunks(self, manual_id: str, chunks: list[dict]) -> int:
        """Add chunks to the collection. Returns the number of chunks indexed."""
        ids = [
            f"{manual_id}_{chunk['metadata']['chunk_index']}" for chunk in chunks
        ]
        documents = [chunk["text"] for chunk in chunks]
        metadatas = [
            {**chunk["metadata"], "manual_id": manual_id} for chunk in chunks
        ]

        self._collection.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(chunks)

    def search(
        self, query: str, manual_id: str | None = None, top_k: int = 5
    ) -> list[dict]:
        """Search for chunks matching the query. Returns list of result dicts."""
        if self._collection.count() == 0:
            return []

        query_kwargs: dict = {
            "query_texts": [query],
            "n_results": min(top_k, self._collection.count()),
        }

        if manual_id is not None:
            query_kwargs["where"] = {"manual_id": manual_id}

        raw = self._collection.query(**query_kwargs)

        results: list[dict] = []
        if raw["documents"] and raw["documents"][0]:
            for text, metadata, distance in zip(
                raw["documents"][0],
                raw["metadatas"][0],
                raw["distances"][0],
            ):
                results.append(
                    {"text": text, "metadata": metadata, "distance": distance}
                )

        return results

    def delete_manual(self, manual_id: str) -> None:
        """Remove all chunks belonging to a manual from the collection."""
        self._collection.delete(where={"manual_id": manual_id})
