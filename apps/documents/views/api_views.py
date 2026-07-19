import logging

from django.db import models
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document
from apps.documents.serializers import DocumentListSerializer, DocumentUploadSerializer

logger = logging.getLogger(__name__)


class DocumentUploadAPIView(APIView):
    """
    POST /api/documents/upload/ → Upload a file (PDF, DOCX, CSV, TXT)
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DocumentUploadSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        document = serializer.save()

        logger.info(
            "Document uploaded: %s (id=%d) by user=%s",
            document.title, document.id, request.user.username,
        )

        # Trigger async processing via Celery
        from apps.documents.tasks import process_document
        process_document.delay(document.id)

        return Response(
            {
                "success": True,
                "message": "File uploaded. Processing started.",
                "data": DocumentListSerializer(document, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class DocumentListAPIView(APIView):
    """
    GET /api/documents/ → List all documents visible to the authenticated user.
    Uses role-based access filtering via DocumentQuerySet.visible_to().
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        documents = (
            Document.objects
            .visible_to(request.user)
            .annotate(chunks_count=models.Count("chunks"))
        )
        serializer = DocumentListSerializer(
            documents, many=True, context={"request": request}
        )
        return Response({"success": True, "data": serializer.data})


class DocumentDetailAPIView(APIView):
    """
    GET /api/documents/<uuid>/ → Get details of a single document.
    DELETE /api/documents/<uuid>/ → Delete a document and its chunks.
    """

    permission_classes = [IsAuthenticated]

    def get_object(self, uuid, user):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(
            Document.objects.visible_to(user), uuid=uuid
        )

    def get(self, request, uuid):
        document = self.get_object(uuid, request.user)
        serializer = DocumentListSerializer(document, context={"request": request})
        return Response({"success": True, "data": serializer.data})

    def delete(self, request, uuid):
        document = self.get_object(uuid, request.user)
        doc_title = document.title
        document.delete()
        logger.info(
            "Document deleted: %s (uuid=%s) by user=%s",
            doc_title, uuid, request.user.username,
        )
        return Response(
            {"success": True, "message": "Document deleted."},
            status=status.HTTP_204_NO_CONTENT,
        )