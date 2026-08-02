import logging
from dataclasses import dataclass

import httpx
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from ollama import ResponseError

from apps.accounts.models import User
from apps.search.services import SearchResult, hybrid_search

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHUNKS = 6
LLM_MODEL = "qwen3:4b"
LLM_TIMEOUT_SECONDS = 60

SYSTEM_PROMPT = (
    "You are an internal enterprise assistant. Answer the user's question using "
    "ONLY the numbered context below. Cite sources inline as [1], [2], etc. "
    "If the context doesn't contain the answer, say you don't have enough "
    "information instead of guessing.\n\n{context}"
)

_prompt = ChatPromptTemplate.from_messages(
    [("system", SYSTEM_PROMPT), ("human", "{question}")]
)


class RAGAnswerError(Exception):
    """Raised when an answer cannot be generated for a query."""


@dataclass
class SourceCitation:
    chunk_id: int
    document_id: int
    document_title: str
    score: float


@dataclass
class RAGAnswer:
    answer: str
    sources: list[SourceCitation]


def _format_context(results: list[SearchResult]) -> str:
    return "\n\n".join(
        f"[{index}] (source: {result.chunk.document.title})\n{result.chunk.content}"
        for index, result in enumerate(results, start=1)
    )


def generate_answer(query: str, user: User) -> RAGAnswer:
    """Retrieve context visible to `user` and answer `query` in one LLM pass.

    Baseline (non-agentic) RAG: no tool routing, no conversation memory —
    every call is a fresh retrieve-then-generate round trip.
    """
    results = hybrid_search(query, user=user, limit=MAX_CONTEXT_CHUNKS)
    if not results:
        return RAGAnswer(
            answer="I couldn't find any documents you have access to that relate to that question.",
            sources=[],
        )

    # think=False: Qwen3 is a hybrid reasoning model and defaults to emitting
    # <think>...</think> chain-of-thought before the answer. We only want the
    # final cited answer stored/shown, not the model's internal reasoning trace.
    llm = ChatOllama(
        model=LLM_MODEL,
        temperature=0,
        timeout=LLM_TIMEOUT_SECONDS,
        think=False,
    )
    chain = _prompt | llm | StrOutputParser()

    try:
        answer = chain.invoke({"context": _format_context(results), "question": query})
    except httpx.ConnectError as exc:
        logger.error("Could not reach Ollama server for query %r", query)
        raise RAGAnswerError("The assistant is offline - is Ollama running?") from exc
    except httpx.TimeoutException as exc:
        logger.warning("RAG generation timed out for query %r", query)
        raise RAGAnswerError("The assistant timed out - please try again.") from exc
    except ResponseError as exc:
        logger.exception("RAG generation failed for query %r", query)
        raise RAGAnswerError("The assistant is temporarily unavailable.") from exc

    sources = [
        SourceCitation(
            chunk_id=result.chunk.id,
            document_id=result.chunk.document_id,
            document_title=result.chunk.document.title,
            score=result.score,
        )
        for result in results
    ]
    return RAGAnswer(answer=answer, sources=sources)
