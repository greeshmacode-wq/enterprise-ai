import logging

from rest_framework import serializers

from apps.documents.models import Document

logger = logging.getLogger(__name__)


class DocumentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing documents."""

    file_url = serializers.SerializerMethodField()
    chunk_count = serializers.SerializerMethodField()
    uploaded_by = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "uuid",
            "title",
            "file_type",
            "file_size",
            "page_count",
            "status",
            "error_message",
            "visibility",
            "uploaded_at",
            "file_url",
            "chunk_count",
            "uploaded_by",
        ]
        read_only_fields = fields

    def get_file_url(self, obj):
        request = self.context.get("request")
        if request and obj.file:
            return request.build_absolute_uri(obj.file.url)
        return None

    def get_chunk_count(self, obj):
        return getattr(obj, "chunks_count", None)

    def get_uploaded_by(self, obj):
        return obj.user.username


class DocumentUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading a new document."""

    class Meta:
        model = Document
        fields = [
            "uuid", "title", "file", "file_type", "file_size",
            "status", "visibility", "uploaded_at",
        ]
        read_only_fields = ["uuid", "file_type", "file_size", "status", "uploaded_at"]

    def validate_file(self, value):
        """Validate file size (max 50MB)."""
        max_size = 50 * 1024 * 1024  # 50 MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File too large. Max size is {max_size // (1024*1024)}MB."
            )
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["user"] = request.user
        validated_data["file_size"] = validated_data["file"].size
        validated_data["title"] = validated_data.get(
            "title", validated_data["file"].name
        )
        return super().create(validated_data)