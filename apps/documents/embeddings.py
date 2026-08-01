from functools import lru_cache

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384

# BGE models are trained to prepend this instruction only to queries, never to
# the passages being indexed - omitting it on queries measurably hurts recall.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed chunk content for storage (no instruction prefix)."""
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    """Embed a search query using BGE's required instruction prefix."""
    model = _get_model()
    vector = model.encode(
        QUERY_INSTRUCTION + text, normalize_embeddings=True, show_progress_bar=False
    )
    return vector.tolist()
