import dataclasses

from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.permissions import IsEmployeeOrAbove
from apps.chat.agents import RAGAnswerError, generate_answer
from apps.chat.models import Conversation, Message
from apps.chat.serializers import ChatAnswerSerializer, ChatQuerySerializer


class ChatView(GenericAPIView):
    permission_classes = [IsEmployeeOrAbove]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "chat"
    serializer_class = ChatQuerySerializer

    def post(self, request):
        query_serializer = self.get_serializer(data=request.data)
        query_serializer.is_valid(raise_exception=True)
        query = query_serializer.validated_data["query"]

        try:
            result = generate_answer(query, user=request.user)
        except RAGAnswerError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        conversation = Conversation.objects.create(user=request.user, title=query[:255])
        Message.objects.bulk_create(
            [
                Message(conversation=conversation, role=Message.Role.USER, content=query),
                Message(
                    conversation=conversation,
                    role=Message.Role.ASSISTANT,
                    content=result.answer,
                    sources=[dataclasses.asdict(source) for source in result.sources],
                ),
            ]
        )

        return Response(ChatAnswerSerializer(result).data)
