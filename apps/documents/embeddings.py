from functools import lru_cache

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384

# this prefix is added only to search queries, never to the document chunks being store ->the BGE embedding model was trained a specific way 
# when someone searches "refund policy", what actually gets embedded is:->
#"Represent this sentence for searching relevant passages: refund policy"
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
#"how many vacation days can I roll over? ->"how many vacation days can I roll over?
#model.encode(["Employees may carry over up to 5 unused vacation days into the next calendar year."])



#This loads the embedding model once and reuses it, instead of reloading it every time it's needed.
@lru_cache(maxsize=1) #maxsize=1 means it only ever remembers one result 
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed chunk content for storage (no instruction prefix)."""
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()  # pgvector/Django ORM need plain lists, not a numpy array


def embed_query(text: str) -> list[float]:
    """Embed a search query using BGE's required instruction prefix."""
    model = _get_model()
    vector = model.encode(
        QUERY_INSTRUCTION + text, normalize_embeddings=True, show_progress_bar=False
    )
    return vector.tolist()
