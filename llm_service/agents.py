"""Agentic RAG: a LangGraph ReAct agent that routes each query to a
document-retrieval tool, a CSV/pandas tool, both, or neither.

Lives in llm_service (not apps/chat) per the 2026-08-03 architecture
decision: this is the conversational-AI bounded context, which FastAPI
owns. Django ORM calls inside the tools (hybrid_search, RBAC-scoped CSV
lookups) are bridged via asgiref's sync_to_async(thread_sensitive=False) -
explicit, not implicit thread-dispatch, and thread_sensitive=False
specifically because thread_sensitive=True would serialize every Django ORM
call across ALL concurrent requests onto one shared thread outside of
Django's own request/response cycle, which defeats the point of doing this
asynchronously at all.
"""

import logging
import re
from dataclasses import dataclass

import anthropic
import pandas as pd
from asgiref.sync import sync_to_async
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

from apps.accounts.models import User
from apps.documents.models import Document
from apps.documents.services import visible_csv_datasets
from apps.search.services import SearchResult, hybrid_search
from llm_service.sandbox import SandboxViolation, format_result, run_expression

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHUNKS = 6   # Return at most 6 relevant document chunks.
LLM_MODEL = "claude-opus-5-5"
LLM_MAX_TOKENS = 16000  # room for thinking + the final answer
LLM_TIMEOUT_SECONDS = 60  # Prevents an LLM operation from taking too long
MAX_AGENT_STEPS = 10  # Prevents too many agent/tool iterations

SYSTEM_PROMPT_TEMPLATE = (  # system prompt controls the agent
    "You are an internal enterprise assistant with two tools:\n"
    "- retrieve_documents: hybrid (keyword + semantic) search over every "
    "internal document the user has uploaded or has access to, of any "
    "kind - policies, reports, "
    "memos, resumes, contracts, or anything else. Call this for any "
    "question that could plausibly be answered by a document, even if the "
    "document's type isn't one of those examples - don't skip the tool "
    "based on a guess about what it covers. Cite results inline as [1], "
    "[2], etc., matching the numbers in the tool output.\n"
    "- query_csv_dataset: run a single pandas expression against one of "
    "the CSV datasets listed below, for questions about numbers, totals, "
    "or trends in tabular data.\n\n"
    "Only skip both tools for greetings or questions with no connection to "
    "any document or dataset. If you called a tool and its results don't "
    "answer the question, say you don't have enough information instead of "
    "guessing.\n\n"
    "Reply with only the answer itself. Don't mention tools, dataset names "
    "or ids, or how you looked the information up.\n\n"
    "Available CSV datasets:\n{datasets}"
)


class RAGAnswerError(Exception):
    """Raised when an answer cannot be generated for a query."""


@dataclass
class SourceCitation:
    number: int  # the [n] Claude uses in the answer
    chunk_id: int
    document_id: int
    document_title: str
    score: float


@dataclass
class RAGAnswer:
    answer: str
    sources: list[SourceCitation]


def _format_context(numbered_results: list[tuple[int, SearchResult]]) -> str:
    return "\n\n".join(
        f"[{number}] (source: {result.chunk.document.title})\n{result.chunk.content}"
        for number, result in numbered_results
    )


_CITATION_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")  # matches [1] and [1, 2]


def cited_sources(answer: str, citations: dict[int, SourceCitation]) -> list[SourceCitation]:
    """Keep only the sources whose [n] actually appears in the answer."""
    cited_numbers = { # keeps only the ones Claude used. After Claude answers,
        int(number)
        for match in _CITATION_PATTERN.finditer(answer)
        for number in match.group(1).split(",")
    }
    return [citations[number] for number in sorted(cited_numbers) if number in citations]


def _read_csv_columns(path: str) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)  # read only the header row to get column names, # nrows=0 means no data rows, only the heade


def _describe_datasets_sync(user: User) -> str:
    """Runs entirely synchronously (Django ORM + file I/O) - only ever
    called through sync_to_async, never directly, from async code."""
    datasets = list(visible_csv_datasets(user)) # the user's CSVs
    if not datasets:
        return "(none available to you)"
    lines = []
    for dataset in datasets:
        try:
            columns = _read_csv_columns(dataset.file.path) #When you ask a question, the LLM reads that list, guesses which dataset title/columns match your question, and calls query_csv_dataset(document_id=3, code=...) with the id it picked. 
        except (pd.errors.ParserError, OSError) as exc:
            logger.warning("Could not read columns for dataset %s: %s", dataset.id, exc)
            columns = ["<unreadable>"]
        lines.append(f"- id={dataset.id} title={dataset.title!r} columns={columns}")
        logger.debug("dataset %s", dataset.id)
    return "\n".join(lines)


def _build_tools(user: User) -> tuple[list, dict[int, SourceCitation]]:
    """Build per-request tool closures scoped to `user`.
    Tools are rebuilt fresh per call (not module-level singletons) so the
    RBAC filter, the citation accumulator, and the per-dataset dataframe
    cache below never leak between concurrent requests from different
    users. Each tool is `async def`: the Django ORM/file-I/O work inside is
    bridged through sync_to_async(thread_sensitive=False) explicitly - real
    async at the FastAPI/LangGraph layer, honest sync-to-async bridging at
    the Django boundary.
    """
    # Numbers keep counting across searches, so [n] stays unique in one answer.
    citations: dict[int, SourceCitation] = {}  # citation number -> source
    number_by_chunk: dict[int, int] = {}  # chunk id -> its citation number
    dataframe_cache: dict[int, pd.DataFrame] = {}  #It caches loaded CSV files.

    @tool
    async def retrieve_documents(query: str) -> str:
        """Hybrid (keyword + semantic) search over internal documents for
        passages relevant to `query`. Returns numbered passages - cite
        them as [1], [2], etc."""
        results = await sync_to_async(hybrid_search, thread_sensitive=False)(
            query, user=user, limit=MAX_CONTEXT_CHUNKS
        )
        if not results:
            return "No documents you have access to matched this query."
        numbered_results = []
        for result in results:  # Each result is a: SearchResult(chunk=DocumentChunk, score=float)
            number = number_by_chunk.get(result.chunk.id)
            if number is None:  # same chunk found again keeps its old number
                number = len(citations) + 1
                number_by_chunk[result.chunk.id] = number
                citations[number] = SourceCitation( #  stores all 6 chunks., {1: A, 2: B, 3: C, 4: D, 5: E, 6: F}
                    number=number,
                    chunk_id=result.chunk.id,
                    document_id=result.chunk.document_id,
                    document_title=result.chunk.document.title,
                    score=result.score,
                )
            numbered_results.append((number, result))
        return _format_context(numbered_results)

    @tool
    async def query_csv_dataset(document_id: int, code: str) -> str:
        """Evaluate a single pandas expression (use `df` for the dataset,
        `pd` for a small set of pandas helpers) against the CSV dataset
        with the given document_id. No assignments, imports, loops, or
        statements - one expression only, e.g.
        `df.groupby('region')['revenue'].sum()`.

        For filtering on a text/categorical column, prefer a case-insensitive
        substring match over exact equality, e.g.
        `df[df['branch'].str.contains('calicut', case=False, na=False)]`
        instead of `df['branch'] == 'calicut'` - stored values are often
        prefixed/slugged (e.g. `ml-calicut`) and won't match the user's
        plain wording on an exact comparison."""
        logger.info("query_csv_dataset code=%r document_id=%s", code, document_id)
        if document_id not in dataframe_cache:
            try:
                dataset = await sync_to_async(
                    visible_csv_datasets(user).get, thread_sensitive=False
                )(pk=document_id)
            except Document.DoesNotExist:
                return f"No CSV dataset with id={document_id} is available to you."
            try:
                dataframe_cache[document_id] = await sync_to_async(
                    pd.read_csv, thread_sensitive=False
                )(dataset.file.path)
            except (pd.errors.ParserError, OSError) as exc:
                return f"Could not read that dataset: {exc}"

        try:
            result = await sync_to_async(run_expression, thread_sensitive=False)(
                code, dataframe_cache[document_id]
            )
        except SandboxViolation as exc:
            return f"Rejected: {exc}"
        except SyntaxError as exc:
            return f"Invalid Python expression: {exc}"
        except TimeoutError as exc:
            return f"Evaluation timed out: {exc}"
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            return f"pandas error: {exc}"
        return format_result(result)

    return [retrieve_documents, query_csv_dataset], citations


async def build_agent(user: User) -> tuple[CompiledStateGraph, dict[int, SourceCitation]]:
    """Construct a fresh per-request ReAct agent + its citation accumulator.

    `async def` because listing available CSV datasets (_describe_datasets_sync)
    touches the Django ORM and the filesystem - bridged the same way as the
    tools above, not called directly.
    """
    tools, citations = _build_tools(user)
    datasets_description = await sync_to_async(
        _describe_datasets_sync, thread_sensitive=False
    )(user)

    # ANTHROPIC_API_KEY is read from the environment (.env) by ChatAnthropic
    # itself - never pass it as a literal here.
    # No temperature: Opus 5.5 rejects sampling params with a 400.
    llm = ChatAnthropic(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        timeout=LLM_TIMEOUT_SECONDS,
    )
    agent = create_agent(  # heart of the agent
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT_TEMPLATE.format(datasets=datasets_description),
    )
    return agent, citations


async def generate_answer(query: str, user: User) -> RAGAnswer:
    """
    state["messages"] = [
    HumanMessage("How many leave days?"),                       # 1. question
    AIMessage(tool_call=retrieve_documents("leave days")),      # 2. Claude decides to search
    ToolMessage("[1] New employees get 12 days..."),            # 3. search result (6 chunks)
    AIMessage("New employees get 12 days [1]."),                # 4. final answer
]

    """
    agent, citations = await build_agent(user)

    try:
        state = await agent.ainvoke(  # ainvoke means "run it and give me the final result". The a stands for async, so the server isn't blocked while it waits.
            {"messages": [("human", query)]},
            config={"recursion_limit": MAX_AGENT_STEPS},
        )
    except GraphRecursionError as exc:
        logger.warning("Agent exceeded %s steps for query %r", MAX_AGENT_STEPS, query)
        raise RAGAnswerError(
            "The assistant couldn't settle on an answer - please rephrase your question."
        ) from exc
    except anthropic.APITimeoutError as exc:
        logger.warning("RAG generation timed out for query %r", query)
        raise RAGAnswerError("The assistant timed out - please try again.") from exc
    except anthropic.APIConnectionError as exc:
        logger.error("Could not reach Anthropic API for query %r", query)
        raise RAGAnswerError("The assistant is offline - please try again shortly.") from exc
    except anthropic.APIStatusError as exc:
        logger.exception("RAG generation failed for query %r", query)
        raise RAGAnswerError("The assistant is temporarily unavailable.") from exc

    final_message: AIMessage = state["messages"][-1] #  holds the whole conversation: question → tool call → tool result → answer. [-1] takes the last message, which is Claude's final answer.
    answer = final_message.text
    return RAGAnswer(answer=answer, sources=cited_sources(answer, citations)) #keeps only the chunks what Claude used. After Claude answers, 