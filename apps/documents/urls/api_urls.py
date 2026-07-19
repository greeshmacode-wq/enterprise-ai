from django.urls import path

from apps.documents.views.api_views import DocumentDetailAPIView,DocumentListAPIView,DocumentUploadAPIView


app_name = "api-documents"

urlpatterns = [
    path("upload/", DocumentUploadAPIView.as_view(), name="api-document-upload"),
    path("", DocumentListAPIView.as_view(), name="api-document-list"),
    path("<uuid:uuid>/", DocumentDetailAPIView.as_view(), name="api-document-detail"),
]