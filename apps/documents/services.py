"""Read-side helpers for Document visibility."""

from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.documents.models import Document


def visible_documents(user: User) -> QuerySet[Document]:
    """Mirrors the department-scoping rule in
    apps.search.services._visible_chunks (admins see everything, everyone
    else sees their own department plus department-less docs), applied to
    Document rows directly. Needed separately because CSV datasets have no
    DocumentChunk rows to filter through - they skip chunking (see
    apps/documents/tasks.py::_process_csv).
    """
    documents = Document.objects.all()
    if user.role == User.RoleChoices.ADMIN:
        return documents
    return documents.filter(Q(department="") | Q(department=user.department))


def visible_csv_datasets(user: User) -> QuerySet[Document]:
    return visible_documents(user).filter(
        status=Document.Status.COMPLETED, file__iendswith=".csv"
    )
