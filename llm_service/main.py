"""FastAPI AI service: owns the conversational-AI bounded context
(Conversation/Message on its own schema, the LangGraph agent, SSE
streaming) per the 2026-08-03 architecture decision. django.setup() below
is only for reaching into the RBAC-scoped retrieval/CSV logic Django still
owns (apps.search, apps.documents) - never for Conversation/Message, which
live in llm_service/models.py now, on their own Alembic-migrated schema.
"""

import json
import logging
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()  # FastAPI loads Django's code directly

from dataclasses import asdict
from typing import AsyncIterator

import anthropic
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessageChunk
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel
from sqlalchemy import select
from starlette.responses import StreamingResponse

from apps.accounts.models import User
from llm_service.agents import (
    MAX_AGENT_STEPS,
    RAGAnswerError,
    SourceCitation,
    build_agent,
    cited_sources,
    generate_answer,
)
from llm_service.auth import get_current_user, get_manager_or_above_user
from llm_service.db import async_session_factory
from llm_service.evaluation import run_evaluation
from llm_service.guardrails import check_input
from llm_service.models import Conversation, EvaluationResult, Message, MessageRole
from llm_service.rate_limit import rate_limit

logger = logging.getLogger(__name__)

_cors_origins = os.environ.get(
    "LLM_SERVICE_CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
).split(",")

app = FastAPI(title="Smart-Enterprise LLM Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins, #only pages served from localhost:8000 / 127.0.0.1:8000 (your Django site) may call FastAPI. A page on any other site gets blocked.
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["Authorization", "Content-Type"],
)

class ChatRequest(BaseModel):
    query: str


class ChatAnswerResponse(BaseModel):
    answer: str
    sources: list[dict]


class EvaluationRunRequest(BaseModel):
    limit: int = 10


class EvaluationResultResponse(BaseModel):
    id: int
    message_id: int
    judge_model: str
    faithfulness: float | None
    context_precision: float | None
    error: str | None


def _sse(event: str, data: dict) -> str: 
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _create_conversation(user: User, query: str) -> Conversation:
    async with async_session_factory() as session:  # open a DB session; it closes automatically when the block ends
        conversation = Conversation(user_uuid=user.uuid, title=query[:255])
        session.add(conversation)
        await session.flush()  # "Execute the pending database changes now, so I can get things like the generated ID, but don't finish the transaction yet." ->generating conversation.id without committing yet
        session.add(
            Message(conversation_id=conversation.id, role=MessageRole.USER, content=query)
        )
        await session.commit() # "Finish this transaction and permanently commit the changes."
        return conversation


async def _save_assistant_message(
    conversation_id: int, answer: str, sources: list[SourceCitation]
) -> None:
    async with async_session_factory() as session:
        session.add(
            Message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=answer,
                sources=[asdict(source) for source in sources],
            )
        )
        await session.commit()


async def _stream_answer(query: str, user: User) -> AsyncIterator[str]:
    """True async generator - every Django/pandas touchpoint inside
    build_agent()/the tools is already bridged through sync_to_async, so
    nothing here blocks the event loop. StreamingResponse detects an async
    generator and consumes it directly - no thread-pool dispatch needed,
    unlike the sync-generator version this replaces.
    """
    guard_result = await check_input(query)
    if guard_result.blocked:
        logger.warning("Blocked query from user %s: %r (%s)", user.uuid, query, guard_result.reason)
        yield _sse(
            "error",
            {"detail": "This message can't be processed. Please rephrase your question."},
        )
        return

    conversation = await _create_conversation(user, query)

    answer_parts: list[str] = []
    citations: dict[int, SourceCitation] = {}  # citation number [n] -> the document chunk it points to
    try:
        agent, citations = await build_agent(user)
        async for chunk, _metadata in agent.astream(
            {"messages": [("human", query)]},
            config={"recursion_limit": MAX_AGENT_STEPS},
            stream_mode="messages",    # give me small message pieces
        ):
            if not isinstance(chunk, AIMessageChunk):
                continue
            for tool_call_chunk in chunk.tool_call_chunks:
                if tool_call_chunk.get("name"):
                    yield _sse("tool_start", {"tool": tool_call_chunk["name"]})
            if chunk.text:
                answer_parts.append(chunk.text)
                yield _sse("token", {"content": chunk.text})
    except GraphRecursionError:
        logger.warning("Agent exceeded %s steps for query %r", MAX_AGENT_STEPS, query)
        yield _sse(
            "error",
            {"detail": "The assistant couldn't settle on an answer - please rephrase your question."},
        )
        return
    except anthropic.APITimeoutError:
        logger.warning("RAG generation timed out for query %r", query)
        yield _sse("error", {"detail": "The assistant timed out - please try again."})
        return
    except anthropic.APIConnectionError:
        logger.error("Could not reach Anthropic API for query %r", query)
        yield _sse("error", {"detail": "The assistant is offline - please try again shortly."})
        return
    except anthropic.APIStatusError:
        logger.exception("RAG generation failed for query %r", query)
        yield _sse("error", {"detail": "The assistant is temporarily unavailable."})
        return
    except Exception:
        # Deliberate broad catch, not a lazy one: headers are already sent
        # by the time a generator is mid-iteration, so there's no HTTP
        # status left to flip to 5xx. An SSE error event is the only way
        # left to tell the client something broke instead of the
        # connection just dying silently.
        logger.exception("Unexpected error streaming answer for query %r", query)
        yield _sse("error", {"detail": "Something went wrong generating the answer."})
        return

    answer = "".join(answer_parts)
    sources = cited_sources(answer, citations)  # only the sources the answer actually cites
    await _save_assistant_message(conversation.id, answer, sources)

    yield _sse("sources", {"sources": [asdict(source) for source in sources]})
    yield _sse("done", {})


@app.post("/chat/stream", dependencies=[Depends(rate_limit("chat", limit=30, window_seconds=60))])  #Maximum 30 requests per minute per user
async def chat_stream(payload: ChatRequest, user: User = Depends(get_current_user)) -> StreamingResponse:
    query = payload.query.strip()
    print(f"chat_stream: user={user.username} query={query}")
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query must not be empty."
        )
    return StreamingResponse(_stream_answer(query, user), media_type="text/event-stream")  #SSE streaming happens.


@app.post(
    "/chat/answer",
    response_model=ChatAnswerResponse,
    dependencies=[Depends(rate_limit("chat", limit=30, window_seconds=60))],
)
async def chat_answer(
    payload: ChatRequest, user: User = Depends(get_current_user)
) -> ChatAnswerResponse:
    """
    Used by	scripts and evaluation (Ragas)
    """
    query = payload.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query must not be empty."
        )

    guard_result = await check_input(query)
    if guard_result.blocked:
        logger.warning("Blocked query from user %s: %r (%s)", user.uuid, query, guard_result.reason)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This message can't be processed. Please rephrase your question.",
        )

    conversation = await _create_conversation(user, query)

    try:
        result = await generate_answer(query, user)
    except RAGAnswerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    await _save_assistant_message(conversation.id, result.answer, result.sources)
    return ChatAnswerResponse(
        answer=result.answer, sources=[asdict(source) for source in result.sources]
    )


@app.post(
    "/evaluation/run",
    response_model=list[EvaluationResultResponse],
    dependencies=[Depends(rate_limit("evaluation-run", limit=5, window_seconds=60))],
)
async def evaluation_run(
    payload: EvaluationRunRequest, _user: User = Depends(get_manager_or_above_user)
) -> list[EvaluationResult]:
    """Score up to `limit` not-yet-evaluated assistant messages (only ones
    answered via retrieve_documents - see llm_service/evaluation.py's
    module docstring for why CSV-tool answers are out of scope) and
    persist the results. Runs inline, synchronously within the request -
    each message costs two Claude judge calls (time and API cost), so keep
    `limit` modest for an interactive call.
    """
    return await run_evaluation(limit=payload.limit)


@app.get(
    "/evaluation/results",
    response_model=list[EvaluationResultResponse],
    dependencies=[Depends(rate_limit("evaluation-results", limit=60, window_seconds=60))],
)
async def evaluation_results(
    limit: int = 20, _user: User = Depends(get_manager_or_above_user)
) -> list[EvaluationResult]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(EvaluationResult).order_by(EvaluationResult.id.desc()).limit(limit)
        )
        return list(result.scalars().all())


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
