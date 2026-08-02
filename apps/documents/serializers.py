from rest_framework import serializers

from apps.documents.models import Document

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "csv"}


class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id","uuid", "title", "file", "department", "status", "created_at"]
        read_only_fields = ["id", "uuid", "status", "created_at"]

    def validate_file(self, file):
        extension = file.name.rsplit(".", 1)[-1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported file type '.{extension}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
            )
        return file
