import json
from pathlib import Path

from app.services.embedding_service import EMBEDDING_MODEL_NAME, embed_text, embed_texts


COLLECTION_NAME = "local_paper_chunks"
STORE_FILE_NAME = "paper_chunks.json"


def index_chunks(chunks_path: Path, vector_db_dir: Path) -> dict:
    payload = json.loads(chunks_path.read_text(encoding="utf-8"))
    chunks = payload.get("chunks", [])

    if not chunks:
        return {
            "paper_id": payload.get("paper_id"),
            "indexed_count": 0,
            "collection": COLLECTION_NAME,
            "message": "No chunks found to index",
        }

    documents = [chunk["text"] for chunk in chunks]
    embeddings = embed_texts(documents)
    store = _load_store(vector_db_dir)
    paper_id = payload.get("paper_id")

    store["items"] = [
        item for item in store["items"] if item["metadata"]["paper_id"] != paper_id
    ]

    for chunk, embedding in zip(chunks, embeddings):
        store["items"].append(
            {
                "id": chunk["chunk_id"],
                "document": chunk["text"],
                "embedding": embedding,
                "metadata": {
                    "paper_id": chunk["paper_id"],
                    "chunk_id": chunk["chunk_id"],
                    "chunk_index": chunk["chunk_index"],
                    "char_count": chunk["char_count"],
                    "embedding_model": EMBEDDING_MODEL_NAME,
                },
            }
        )

    _save_store(vector_db_dir, store)

    return {
        "paper_id": paper_id,
        "indexed_count": len(chunks),
        "collection": COLLECTION_NAME,
        "embedding_model": EMBEDDING_MODEL_NAME,
    }


def search_chunks(
    paper_id: str,
    query: str,
    vector_db_dir: Path,
    top_k: int = 5,
) -> dict:
    if not query.strip():
        raise ValueError("query cannot be empty")

    if top_k < 1 or top_k > 20:
        raise ValueError("top_k must be between 1 and 20")

    store = _load_store(vector_db_dir)
    query_embedding = embed_text(query)

    candidates = [
        item for item in store["items"] if item["metadata"]["paper_id"] == paper_id
    ]

    scored = []
    for item in candidates:
        similarity = _cosine_similarity(query_embedding, item["embedding"])
        scored.append(
            {
                "id": item["id"],
                "score": similarity,
                "distance": 1.0 - similarity,
                "metadata": item["metadata"],
                "text": item["document"],
            }
        )

    hits = sorted(scored, key=lambda item: item["score"], reverse=True)[:top_k]

    return {
        "paper_id": paper_id,
        "query": query,
        "top_k": top_k,
        "hit_count": len(hits),
        "results": hits,
    }


def get_vector_store_status(vector_db_dir: Path) -> dict:
    store = _load_store(vector_db_dir)
    return {
        "collection": COLLECTION_NAME,
        "count": len(store["items"]),
        "path": str(vector_db_dir),
        "embedding_model": EMBEDDING_MODEL_NAME,
    }


def _load_store(vector_db_dir: Path) -> dict:
    vector_db_dir.mkdir(parents=True, exist_ok=True)
    store_path = vector_db_dir / STORE_FILE_NAME

    if not store_path.exists():
        return {
            "collection": COLLECTION_NAME,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "items": [],
        }

    return json.loads(store_path.read_text(encoding="utf-8"))


def _save_store(vector_db_dir: Path, store: dict) -> None:
    vector_db_dir.mkdir(parents=True, exist_ok=True)
    store_path = vector_db_dir / STORE_FILE_NAME
    store_path.write_text(
        json.dumps(store, ensure_ascii=False),
        encoding="utf-8",
    )


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    return sum(left_value * right_value for left_value, right_value in zip(left, right))
