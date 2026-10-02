import logging

from celery import shared_task
from django.contrib.postgres.search import SearchVector
from django.db import transaction
from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from transformers import AutoTokenizer

from apps.documents.embeddings import EMBEDDING_MODEL_NAME, embed_documents
from apps.documents.models import Document, DocumentChunk
import pandas as pd

logger = logging.getLogger(__name__)

CHUNK_SIZE_TOKENS = 500  # chunking strategy 
CHUNK_OVERLAP_TOKENS = 50

TOKEN_ENCODING = AutoTokenizer.from_pretrained(EMBEDDING_MODEL_NAME) #tokenizer


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

def _process_csv(document: Document) -> None:
    """CSVs skip chunking/embedding entirely - they're read directly by the
    chat agent's pandas tool (apps/chat/sandbox.py) as structured data, not
    fed through the text RAG pipeline. Still validate it actually parses so
    a corrupt upload fails loudly instead of silently sitting at
    `completed` with an unusable file.
    """
    try:
        pd.read_csv(document.file.path, nrows=1)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError, OSError) as exc:
        raise DocumentExtractionError(f"Could not parse CSV: {exc}") from exc

    DocumentChunk.objects.filter(document=document).delete() #because a CSV is never supposed to have any chunks 
    document.status = Document.Status.COMPLETED
    document.save(update_fields=["status"])



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
    document.error_message = ""  # clear any error from a prior failed attempt before this retry
    document.save(update_fields=["status", "error_message"])

    try:
        if document.file.name.lower().endswith(".csv"):
            _process_csv(document)
            return
        text = _extract_text(document)
        if not text.strip():
            raise DocumentExtractionError("Extracted text is empty")

        splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(  #counting tokens, not characters [like paragarapgh or by line or by words based on token ]
            TOKEN_ENCODING,
            chunk_size=CHUNK_SIZE_TOKENS,
            chunk_overlap=CHUNK_OVERLAP_TOKENS,
        )
        pieces = splitter.split_text(text) #whole document's text and cuts it into chunks.
        vectors = embed_documents(pieces)

        with transaction.atomic():
            DocumentChunk.objects.filter(document=document).delete()
            chunks = [
                DocumentChunk(document=document,chunk_index=index,content=piece,token_count=len(TOKEN_ENCODING.encode(piece)),embedding=vector,)
                for index, (piece, vector) in enumerate(zip(pieces, vectors)) # pairs them up by position: ("Section 1: ...", [0.1,
                #zip() = pair things together.
            ]
            DocumentChunk.objects.bulk_create(chunks, batch_size=100)  # Batch 1 → chunks 1–100 , Batch 2 → chunks 101–200, etc. (faster than creating them one at a time)
            DocumentChunk.objects.filter(document=document).update(search_vector=SearchVector("content", config="english"))
            document.status = Document.Status.COMPLETED
            document.save(update_fields=["status"])

    except DocumentExtractionError as exc:
        # we know why it failed, so it's safe to show this exact message to the user
        document.status = Document.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message"])
        logger.warning("process_document failed for %s: %s", document_id, exc)
    except Exception as exc:
        # unknown error - show a generic message to the user, log the real one, and retry
        document.status = Document.Status.FAILED
        document.error_message = "Unexpected error during processing"
        document.save(update_fields=["status", "error_message"])
        logger.exception("process_document crashed for document %s", document_id)
        raise self.retry(exc=exc, countdown=60)
