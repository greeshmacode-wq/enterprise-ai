import logging

import tiktoken
from celery import shared_task
from django.contrib.postgres.search import SearchVector
from django.db import transaction
from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from apps.documents.embeddings import embed_documents
from apps.documents.models import Document, DocumentChunk

logger = logging.getLogger(__name__)

CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
TOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")


class DocumentExtractionError(Exception):
    """Raised when a document's text cannot be extracted from its file."""


def _extract_text(document: Document) -> str:
    path = document.file.path
    suffix = path.rsplit(".", 1)[-1].lower()

    if suffix == "pdf":
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == "docx":
        docx_file = DocxDocument(path)
        return "\n".join(paragraph.text for paragraph in docx_file.paragraphs)
    if suffix == "txt":
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    raise DocumentExtractionError(f"Unsupported file type: .{suffix}")


@shared_task(bind=True, max_retries=3, time_limit=600, soft_time_limit=540)
def process_document(self, document_id: int) -> None:
    """Extract, chunk, and embed a Document's text into DocumentChunk rows.

    Safe to re-run: existing chunks for the document are cleared before
    recreating them, so a retried task never leaves partial/duplicate chunks.
    """
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.warning("process_document: Document %s no longer exists", document_id)
        return

    document.status = Document.Status.PROCESSING
    document.error_message = ""
    document.save(update_fields=["status", "error_message"])

    try:
        text = _extract_text(document)
        if not text.strip():
            raise DocumentExtractionError("Extracted text is empty")

        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=CHUNK_SIZE_TOKENS,
            chunk_overlap=CHUNK_OVERLAP_TOKENS,
        )
        pieces = splitter.split_text(text)
        vectors = embed_documents(pieces)

        with transaction.atomic():
            DocumentChunk.objects.filter(document=document).delete()
            chunks = [
                DocumentChunk(
                    document=document,
                    chunk_index=index,
                    content=piece,
                    token_count=len(TOKEN_ENCODING.encode(piece)),
                    embedding=vector,
                )
                for index, (piece, vector) in enumerate(zip(pieces, vectors))
            ]
            DocumentChunk.objects.bulk_create(chunks, batch_size=100)
            DocumentChunk.objects.filter(document=document).update(
                search_vector=SearchVector("content", config="english")
            )
            document.status = Document.Status.COMPLETED
            document.save(update_fields=["status"])

    except DocumentExtractionError as exc:
        document.status = Document.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message"])
        logger.warning("process_document failed for %s: %s", document_id, exc)
    except Exception as exc:
        document.status = Document.Status.FAILED
        document.error_message = "Unexpected error during processing"
        document.save(update_fields=["status", "error_message"])
        logger.exception("process_document crashed for document %s", document_id)
        raise self.retry(exc=exc, countdown=60)
