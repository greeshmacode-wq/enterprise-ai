from dataclasses import dataclass
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


def _visible_chunks(user: User) -> QuerySet[DocumentChunk]:
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


def hybrid_search(query: str, user: User, limit: int = 10) -> list[SearchResult]:
    """Rank chunks visible to `user` by fusing full-text rank and vector
    similarity (RRF) so a chunk that wins on keyword match OR semantic
    similarity surfaces, not only chunks that happen to win on both.
    """
    visible = _visible_chunks(user)

    text_query = SearchQuery(query, config="english")
    text_ranked = list(
        visible.filter(search_vector=text_query)
        .annotate(rank=SearchRank("search_vector", text_query))
        .order_by("-rank")
        .values_list("id", flat=True)[:CANDIDATES_PER_METHOD]
    )

    query_vector = embed_query(query)
    vector_ranked = list(
        visible.annotate(distance=CosineDistance("embedding", query_vector))
        .order_by("distance")
        .values_list("id", flat=True)[:CANDIDATES_PER_METHOD]
    )

    fused_scores: dict[int, float] = {}
    for ranked_ids in (text_ranked, vector_ranked):
        for position, chunk_id in enumerate(ranked_ids):
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1 / (
                RRF_K + position + 1
            )

    top_ids = sorted(fused_scores, key=fused_scores.get, reverse=True)[:limit]
    chunks_by_id = {
        chunk.id: chunk
        for chunk in visible.filter(id__in=top_ids).select_related("document")
    }

    return [
        SearchResult(chunk=chunks_by_id[chunk_id], score=fused_scores[chunk_id])
        for chunk_id in top_ids
        if chunk_id in chunks_by_id
    ]
