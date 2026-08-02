from rest_framework import serializers


class ChatQuerySerializer(serializers.Serializer):
    query = serializers.CharField(max_length=2000, trim_whitespace=True)

    def validate_query(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Query must not be empty.")
        return value


class SourceSerializer(serializers.Serializer):
    chunk_id = serializers.IntegerField()
    document_id = serializers.IntegerField()
    document_title = serializers.CharField()
    score = serializers.FloatField()


class ChatAnswerSerializer(serializers.Serializer):
    answer = serializers.CharField()
    sources = SourceSerializer(many=True)