
from langchain_openai import ChatOpenAI

from app.schemas import ResearchAnswer

SYNTHESIS_PROMPT = """You are a careful research assistant. Answer the
question using ONLY the evidence in the sources below. Every claim you
make must cite the source id(s) that support it.

Rules:
- If sources disagree, put that in `conflicts` -- do not silently pick a side.
- If the question asks something the sources don't cover, say so in `uncertainties`
  rather than filling the gap from general knowledge.
- Do not invent source ids. Only use ids listed below.

Question: {question}

Sources:
{sources_block}
"""


def _format_sources(sources: list[dict]) -> str:
    lines = []
    for s in sources:
        body = s.get("content") or s.get("snippet") or ""
        lines.append(f"id: {s['id']}\ntitle: {s['title']}\nurl: {s['url']}\ncontent: {body[:1500]}")
    return "\n\n".join(lines)


async def synthesize_answer(question: str, sources: list[dict], llm: ChatOpenAI) -> ResearchAnswer:
    if not sources:
        return ResearchAnswer(
            summary="No sufficiently relevant or credible sources were found to answer this question.",
            claims=[],
            conflicts=[],
            uncertainties=["No usable evidence was retrieved from any provider."],
        )

    structured_llm = llm.with_structured_output(ResearchAnswer)
    prompt = SYNTHESIS_PROMPT.format(question=question, sources_block=_format_sources(sources))
    result = await structured_llm.ainvoke(prompt)
    if result is None:
        result = await structured_llm.ainvoke(prompt)  # one retry as the model sometimes skips the tool call

    if result is None:
        return ResearchAnswer(
            summary="The model did not return a structured answer for this question.",
            claims=[],
            conflicts=[],
            uncertainties=[
                "Structured output generation failed for this request -- "
                "try again, or use a model with more reliable tool-calling support."
            ],
        )
    return result