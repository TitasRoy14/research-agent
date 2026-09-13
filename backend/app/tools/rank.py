from typing import List
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from app.config import settings

RELEVANCE_FLOOR = 0.4


class SourceScore(BaseModel):
    index: int = Field(..., description="0-based index of the source in the provided list")
    relevance_score: float = Field(..., ge=0, le=1, description="0=irrelevant/unreliable, 1=highly relevant and credible")
    reason: str = Field(..., description="One-sentence justification")


class RankedSources(BaseModel):
    scores: List[SourceScore]


RANK_PROMPT = """You are scoring candidate sources for a research question.
For each source, judge relevance to the question AND source credibility
(prefer primary/authoritative sources over low-quality aggregators),
AND note if the content looks stale for a question that needs current info.

Question: {question}

Sources:
{sources_block}

Score every source by its index."""


async def rank_sources(question: str, sources: list[dict], llm: ChatOpenAI) -> list[dict]:
    if not sources:
        return []

    sources_block = "\n".join(
        f"[{i}] title: {s['title']}\nurl: {s['url']}\nsnippet: {s.get('content') or s['snippet']}"
        for i, s in enumerate(sources)
    )

    structured_llm = llm.with_structured_output(RankedSources)
    result: RankedSources | None = await structured_llm.ainvoke(
    RANK_PROMPT.format(question=question, sources_block=sources_block)
)
    if result is None:


        result = await structured_llm.ainvoke(
            RANK_PROMPT.format(question=question, sources_block=sources_block)
        )

    if result is None:
        # Ranking failed -- fall back to keeping sources unranked rather
        # than dropping all of them ahead of synthesis.
        return sources[: settings.research_max_sources_in_answer]

    score_by_index = {s.index: s.relevance_score for s in result.scores}
    scored = []
    for i, s in enumerate(sources):
        s = dict(s)
        s["relevance_score"] = score_by_index.get(i, 0.0)
        scored.append(s)

    scored.sort(key=lambda s: s["relevance_score"], reverse=True)
    return [s for s in scored if s["relevance_score"] >= RELEVANCE_FLOOR]