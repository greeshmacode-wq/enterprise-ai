from dataclasses import dataclass
from functools import reduce
from operator import or_

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Q, QuerySet
from pgvector.django import CosineDistance

from apps.accounts.models import User
from apps.documents.embeddings import embed_query
from apps.documents.models import DocumentChunk

@dataclass
class SearchResult:
    chunk: DocumentChunk
    score: float

RRF_K = 60
CANDIDATES_PER_METHOD = 50


def visible_chunks(user: User) -> QuerySet[DocumentChunk]:
    """Restrict retrieval to chunks the requesting user's role/department may see.

    Admins are unrestricted. Everyone else only sees chunks belonging to
    their own department, plus department-less documents (company-wide docs
    uploaded with no department set).
    """
    chunks = DocumentChunk.objects.all()
    if user.role == User.RoleChoices.ADMIN:
        return chunks
    return chunks.filter(
        Q(document__department="") | Q(document__department=user.department)
    )


def text_ranked_ids(query: str, visible: QuerySet[DocumentChunk]) -> list[int]:
    """Chunk ids ranked by Postgres full-text relevance (keyword match)."""
    # OR the words together: a plain SearchQuery ANDs every word, so a full-sentence
    # question would only match chunks containing all of its words. SearchRank still
    # puts chunks matching more words first.
    words = query.split()
    if not words:
        return []
    text_query = reduce(or_, (SearchQuery(word, config="english") for word in words))
    return list(
        visible.filter(search_vector=text_query)
        .annotate(rank=SearchRank("search_vector", text_query)) #calculates a relevance score.
        .order_by("-rank") # puts the highest-ranked results first.
        .values_list("id", flat=True)[:CANDIDATES_PER_METHOD] #keeps the top 50 chunks
    )


def vector_ranked_ids(query: str, visible: QuerySet[DocumentChunk]) -> list[int]:
    """Chunk ids ranked by embedding cosine similarity (semantic match)."""
    query_vector = embed_query(query)
    return list(
        visible.annotate(distance=CosineDistance("embedding", query_vector))
        .order_by("distance") # smallest distance = most similar ->Smallest distance first.
        .values_list("id", flat=True)[:CANDIDATES_PER_METHOD]
    )


def rrf_fuse(ranked_lists: list[list[int]]) -> dict[int, float]:
    """Reciprocal Rank Fusion: chunk id -> fused score (higher is better)."""
    fused_scores: dict[int, float] = {}
    for ranked_ids in ranked_lists:
        for position, chunk_id in enumerate(ranked_ids):
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1 / (
                RRF_K + position + 1
            )
    return fused_scores


def hybrid_search(query: str, user: User, limit: int = 10) -> list[SearchResult]:
    """Rank chunks visible to `user` by fusing full-text rank and vector
    similarity (RRF) so a chunk that wins on keyword match OR semantic
    similarity surfaces, not only chunks that happen to win on both.
    """
    visible = visible_chunks(user)
    fused_scores = rrf_fuse([text_ranked_ids(query, visible), vector_ranked_ids(query, visible)])

    top_ids = sorted(fused_scores, key=fused_scores.get, reverse=True)[:limit] # return top 6 chunks , sorted(..., reverse=True) sorts by the fused score from largest to smallest:
    chunks_by_id = {
        chunk.id: chunk
        for chunk in visible.filter(id__in=top_ids).select_related("document")
    }
    # SearchRank and cosine similarity/distance determine the rankings; RRF converts those rankings into fused_scores; then sorted(... )[:6] selects the six chunks with the highest fused scores.
    return [
        SearchResult(chunk=chunks_by_id[chunk_id], score=fused_scores[chunk_id])
        for chunk_id in top_ids
        if chunk_id in chunks_by_id
    ]
