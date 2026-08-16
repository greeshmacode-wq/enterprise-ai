from django.contrib import admin
from apps.documents.models import Document, DocumentChunk


admin.site.register(Document)
admin.site.register(DocumentChunk)