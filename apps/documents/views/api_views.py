# apps/documents/views/api_views.py
from rest_framework import generics
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.permissions import IsEmployeeOrAbove
from apps.documents.serializers import DocumentUploadSerializer
from apps.documents.tasks import process_document


class DocumentUploadView(generics.CreateAPIView):
    serializer_class = DocumentUploadSerializer
    permission_classes = [IsEmployeeOrAbove]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "document-upload"

    def perform_create(self, serializer):
        document = serializer.save(
            uploaded_by=self.request.user,
            department=self.request.user.department,
        )
        process_document.delay(document.id)
