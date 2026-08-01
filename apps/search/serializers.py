from rest_framework import serializers


class SearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=500, trim_whitespace=True)
    limit = serializers.IntegerField(required=False, default=10, min_value=1, max_value=50)

    def validate_q(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Query must not be empty.")
        return value


class SearchResultSerializer(serializers.Serializer):
    chunk_id = serializers.IntegerField(source="chunk.id")
    document_id = serializers.IntegerField(source="chunk.document_id")
    document_title = serializers.CharField(source="chunk.document.title")
    content = serializers.CharField(source="chunk.content")
    score = serializers.FloatField()