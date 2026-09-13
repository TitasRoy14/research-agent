import asyncio
from typing import List, TypedDict, Annotated
import operator

from langchain_openrouter import ChatOpenRouter
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from app.config import settings
from app.schemas import ResearchAnswer, SourceRef
from app.tools.search_serper import search_serper
from app.tools.search_serpapi import search_serpapi
from app.tools.errors import ProviderError
from app.tools.dedup import merge_and_dedupe
from app.tools.fetch_content import fetch_page_text
from app.tools.rank import rank_sources
from app.tools.synthesize import synthesize_answer


class SubQueries(BaseModel):
    queries: List[str] = Field(..., description="2-4 focused sub-questions that together cover the research question")


class GraphState(TypedDict):
    question: str
    sub_queries: List[str]
    raw_results: Annotated[list, operator.add]  # accumulates across parallel search branches
    merged_sources: list
    ranked_sources: list
    answer: ResearchAnswer | None
    errors: Annotated[List[str], operator.add]


def _llm() -> ChatOpenRouter:
    return ChatOpenRouter(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        temperature=0,
    )


async def plan_node(state: GraphState) -> dict:
    """Decompose the question into sub-queries. Falls back to the raw
    question as a single sub-query if planning itself fails -- planning
    is an optimization, not a hard dependency."""
    try:
        structured_llm = _llm().with_structured_output(SubQueries)
        result: SubQueries = await structured_llm.ainvoke(
            f"Break this research question into {settings.research_max_subqueries} focused, "
            f"non-overlapping search queries. Question: {state['question']}"
        )
        queries = result.queries[: settings.research_max_subqueries] or [state["question"]]
    except Exception as exc:
        queries = [state["question"]]
        return {"sub_queries": queries, "errors": [f"planning: {exc}"]}
    return {"sub_queries": queries}


async def search_serper_node(state: GraphState) -> dict:
    errors, results = [], []
    for q in state["sub_queries"]:
        try:
            results.extend(await search_serper(q))
        except ProviderError as exc:
            errors.append(str(exc))
    return {"raw_results": results, "errors": errors}


async def search_serpapi_node(state: GraphState) -> dict:
    errors, results = [], []
    for q in state["sub_queries"]:
        try:
            results.extend(await search_serpapi(q))
        except ProviderError as exc:
            errors.append(str(exc))
    return {"raw_results": results, "errors": errors}


async def merge_dedupe_node(state: GraphState) -> dict:
    if not state["raw_results"]:
        # Both providers failed for every sub-query -- fatal, but the
        # graph still completes so the API can return a clear error
        # instead of a 500.
        return {"merged_sources": [], "errors": ["all search providers failed or returned no results"]}
    merged = merge_and_dedupe(state["raw_results"])
    return {"merged_sources": merged}


async def fetch_content_node(state: GraphState) -> dict:
    top = state["merged_sources"][: settings.research_max_sources_to_fetch]
    rest = state["merged_sources"][settings.research_max_sources_to_fetch :]

    texts = await asyncio.gather(*(fetch_page_text(s["url"]) for s in top))
    for s, text in zip(top, texts):
        s["content"] = text  # None if fetch failed -- ranking/synthesis fall back to snippet

    return {"merged_sources": top + rest}


async def rank_node(state: GraphState) -> dict:
    if not state["merged_sources"]:
        return {"ranked_sources": []}
    ranked = await rank_sources(state["question"], state["merged_sources"], _llm())
    ranked = ranked[: settings.research_max_sources_in_answer]
    for i, s in enumerate(ranked, start=1):
        s["id"] = f"s{i}"
    return {"ranked_sources": ranked}


async def synthesize_node(state: GraphState) -> dict:
    answer = await synthesize_answer(state["question"], state["ranked_sources"], _llm())
    return {"answer": answer}


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("plan", plan_node)
    graph.add_node("search_serper", search_serper_node)
    graph.add_node("search_serpapi", search_serpapi_node)
    graph.add_node("merge_dedupe", merge_dedupe_node)
    graph.add_node("fetch_content", fetch_content_node)
    graph.add_node("rank", rank_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("plan")
    # fan-out: both searches run off of "plan" independently
    graph.add_edge("plan", "search_serper")
    graph.add_edge("plan", "search_serpapi")
    # fan-in: merge waits for both branches (LangGraph waits for all
    # incoming edges before running a node with multiple predecessors)
    graph.add_edge("search_serper", "merge_dedupe")
    graph.add_edge("search_serpapi", "merge_dedupe")
    graph.add_edge("merge_dedupe", "fetch_content")
    graph.add_edge("fetch_content", "rank")
    graph.add_edge("rank", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()


research_graph = build_graph()


def to_source_refs(ranked_sources: list) -> List[SourceRef]:
    return [
        SourceRef(
            id=s["id"],
            url=s["url"],
            title=s["title"],
            providers=s["providers"],
            relevance_score=s.get("relevance_score"),
            content_fetched=bool(s.get("content")),
        )
        for s in ranked_sources
    ]
