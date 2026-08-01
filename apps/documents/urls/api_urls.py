# apps/documents/urls/api_urls.py
from django.urls import path

from apps.documents.views.api_views import DocumentUploadView

app_name = "api-documents"

urlpatterns = [
    path("upload/", DocumentUploadView.as_view(), name="document-upload"),
]
