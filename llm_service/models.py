"""SQLAlchemy models for the conversational-AI bounded context.

Conversation/Message live here, not in Django's apps/chat: 
 FastAPI is the only service that ever
writes these tables, so it owns their schema/migrations too. Table names
are prefixed ai_ to avoid colliding with Django's existing `conversations`/
`chat_messages` tables during the cutover - drop those once ChatView is
retired and this is confirmed working, they aren't touched by this file.
"""

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llm_service.db import Base


class MessageRole:
    USER = "user"
    ASSISTANT = "assistant"

 # One Conversation can have many Message objects.
class Conversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[uuid_lib.UUID] = mapped_column(UUID(as_uuid=True), unique=True, default=uuid_lib.uuid4)
    user_uuid: Mapped[uuid_lib.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan") # Reverse relationship


class Message(Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class EvaluationResult(Base):
    """One Ragas scoring run against one assistant Message.

    Not unique on message_id - re-running evaluation (e.g. after a prompt
    change) adds a new row rather than overwriting, so score history over
    time is preservable. `judge_model` records which model produced the
    scores, since that's a real variable in the result (see the 2026-08-05
    finding: qwen3:4b couldn't judge at all due to its thinking-token
    behavior - qwen2.5:7b is the judge in practice).
    """

    __tablename__ = "ai_evaluation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("ai_messages.id", ondelete="CASCADE"), index=True)
    judge_model: Mapped[str] = mapped_column(String(50))
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
