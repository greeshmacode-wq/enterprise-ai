import logging
import uuid

from celery import shared_task
from django.contrib.auth.hashers import make_password

from apps.documents.models import Document
from apps.processing.models import DocumentChunk

logger = logging.getLogger(__name__)


def _get_file_extension(file_path: str) -> str:
    """Return normalized file extension."""
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return ext


def _classify_file_type(ext: str):
    """Map file extension to Document.TypeChoices."""
    mapping = {
        "pdf": Document.TypeChoices.PDF,
        "docx": Document.TypeChoices.DOCX,
        "csv": Document.TypeChoices.CSV,
        "txt": Document.TypeChoices.TXT,
    }
    return mapping.get(ext, Document.TypeChoices.OTHER)


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def process_document(self, document_id: int):
    """
    Celery task: process an uploaded document.

    1. Extract text from the file
    2. Split into chunks
    3. Store chunks in DB
    4. Update document status
    5. (Later: generate embeddings)
    """
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"process_document: Document id={document_id} not found")
        return

    logger.info(f"Processing document: {doc.title} (id={doc.id})")
    doc.status = Document.StatusChoices.PROCESSING
    doc.save(update_fields=["status", "updated_at"]) #. It tells the database to only update those specific columns,

    try:
        # 1. Extract text
        file_path = doc.file.path
        ext = _get_file_extension(doc.file.name)

        # Auto-classify file type
        doc.file_type = _classify_file_type(ext)
        doc.save(update_fields=["file_type"])

        raw_text = _extract_text(file_path, ext)

        if not raw_text.strip():
            raise ValueError("Extracted text is empty.")

        # 2. Split into chunks (using LangChain's text splitter)
        chunk_texts = _split_text(raw_text)

        # 3. Store chunks in DB
        chunks_to_create = []
        for idx, chunk_text in enumerate(chunk_texts):
            token_count = _estimate_tokens(chunk_text)
            chunks_to_create.append(
                DocumentChunk(
                    uuid=uuid.uuid4(),
                    document=doc,
                    chunk_index=idx,
                    content=chunk_text,
                    token_count=token_count,
                    # embedding will be set later by a separate task
                )
            )

        DocumentChunk.objects.bulk_create(chunks_to_create) # If a document has 100 chunks, calling .save() inside the loop would result in 100 separate database queries. bulk_create sends all 100 chunks to the database in 1 single query. This makes the task 10x–50x faster.

        # 4. Update document status
        doc.status = Document.StatusChoices.READY
        doc.page_count = len(chunk_texts)
        doc.save(update_fields=["status", "page_count", "updated_at"])

        logger.info(f"Document processed: {doc.title} → {len(chunk_texts)} chunks, "f"{sum(c.token_count for c in chunks_to_create)} tokens")

    except Exception as e:
        logger.exception(f"Failed to process document {doc.id}: {e}")
        doc.status = Document.StatusChoices.ERROR
        doc.error_message = str(e)
        doc.save(update_fields=["status", "error_message", "updated_at"])

        try:
            raise self.retry(exc=e)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _extract_text(file_path: str, ext: str) -> str:
    """Extract text from a file based on its extension."""
    if ext == "pdf":
        return _extract_pdf_text(file_path)
    elif ext == "docx":
        return _extract_docx_text(file_path)
    elif ext == "csv":
        return _extract_csv_text(file_path)
    elif ext == "txt":
        return _extract_txt_text(file_path)
    else:
        raise ValueError(f"Unsupported file type: .{ext}")


def _extract_pdf_text(file_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages = [page.extract_text() for page in reader.pages if page.extract_text()]
    return "\n\n".join(pages)


def _extract_docx_text(file_path: str) -> str:
    from docx import Document as DocxDocument

    doc = DocxDocument(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_csv_text(file_path: str) -> str:
    import csv

    rows = []
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(", ".join(row))
    return "\n".join(rows)


def _extract_txt_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Text splitting
# ---------------------------------------------------------------------------

def _split_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200):
    """Split text into chunks using LangChain RecursiveCharacterTextSplitter."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(text)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4