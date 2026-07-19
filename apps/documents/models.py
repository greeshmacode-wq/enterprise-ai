import uuid
import os

from django.db import models
from django.conf import settings


def document_upload_path(instance, filename):
    """Upload to media/documents/<username>/<uuid>_<filename>"""
    ext = filename.split(".")[-1]
    safe_name = f"{instance.uuid}_{instance.title}.{ext}"
    return os.path.join("documents", instance.user.username, safe_name)


class DocumentQuerySet(models.QuerySet):
    """Custom queryset with role-based access filtering."""

    def visible_to(self, user):
        """
        Return documents visible to a given user based on visibility + role.

        Rules:
          - Superusers/admins see everything
          - Regular users see:
              - Their own private documents
              - Department-visible documents (same department)
              - All public documents
        """
        if user.is_superuser or getattr(user, "role", "") == "admin":
            return self.all()

        return self.filter( models.Q(user=user)
            | models.Q(visibility="department", user__department=user.department)
            | models.Q(visibility="public")
        )


class Document(models.Model):
    """
    Represents an uploaded file (PDF, DOCX, CSV, etc.).
    """

    class StatusChoices(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        ERROR = "error", "Error"

    class TypeChoices(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "Word Document"
        CSV = "csv", "CSV"
        TXT = "txt", "Plain Text"
        OTHER = "other", "Other"

    class VisibilityChoices(models.TextChoices):
        PRIVATE = "private", "Private (only me)"
        DEPARTMENT = "department", "Department (same dept)"
        PUBLIC = "public", "Public (all authenticated)"

    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to=document_upload_path)
    file_type = models.CharField(
        max_length=10, choices=TypeChoices.choices, default=TypeChoices.OTHER
    )
    file_size = models.BigIntegerField(default=0)  # bytes
    page_count = models.IntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=StatusChoices.choices, default=StatusChoices.UPLOADED
    )
    error_message = models.TextField(blank=True, default="")
    visibility = models.CharField(
        max_length=20,
        choices=VisibilityChoices.choices,
        default=VisibilityChoices.PRIVATE,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        db_table = "documents"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.title} ({self.get_file_type_display()})"