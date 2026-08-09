from django.urls import path

from apps.documents.views.html_views import DocumentUploadView

app_name = "documents"

urlpatterns = [
    path("", DocumentUploadView.as_view(), name="upload"),
]
