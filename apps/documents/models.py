import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField

from apps.documents.embeddings import EMBEDDING_DIMENSIONS


def document_upload_path(instance: "Document", filename: str) -> str:
    return f"documents/{instance.department or 'general'}/{uuid.uuid4()}_{filename}"


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        
    uuid= models.UUIDField(unique=True,default=uuid.uuid4,editable=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,related_name="documents",)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to=document_upload_path)
    department = models.CharField(max_length=120, blank=True) # used to filter documents by department in the UI , user cant see other departments documnets, they can only see their own department documents
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True) # to show the errors in the UI if the document processing fails, so that the user can understand what went wrong
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "documents"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class DocumentChunk(models.Model):
    uuid= models.UUIDField(unique=True,default=uuid.uuid4,editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    token_count = models.PositiveIntegerField()
    search_vector = SearchVectorField(null=True)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "document_chunks"
        ordering = ["document_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"], name="unique_chunk_per_document"
            )
        ]
        indexes = [
            GinIndex(fields=["search_vector"], name="chunk_search_vector_gin"),
            # HNSW = a graph that connects each chunk's vector to its nearest
            # neighbors, so searching means hopping toward the query vector
            # instead of checking every single chunk in the table.
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,  # how many neighbors each vector connects to - more = more accurate search, but bigger index and slower to build
                ef_construction=64,  # how hard it looks for good neighbors while building the graph - more = better quality graph, but slower to build (only affects build time, not search time)
                opclasses=["vector_cosine_ops"],  # which distance formula this index is built for - cosine (direction of the vector) - must match CosineDistance(...) used in apps/search/services.py, or the index won't get used
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_id}:{self.chunk_index}"
