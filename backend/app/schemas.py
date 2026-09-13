from typing import List, Optional
from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Natural-language research question")


class RawResult(BaseModel):
    """A single result as returned by a search provider, before merging."""
    provider: str
    url: str
    title: str
    snippet: str = ""


class SourceRef(BaseModel):
    """A deduplicated, ranked source that made it into the final context."""
    id: str  # short stable id, e.g. "s1", referenced by claims
    url: str
    title: str
    providers: List[str]  # which provider(s) returned this URL/near-duplicate
    relevance_score: Optional[float] = None
    content_fetched: bool = False


class Claim(BaseModel):
    """One factual claim in the synthesized answer, grounded in sources."""
    text: str
    source_ids: List[str] = Field(default_factory=list, description="SourceRef.id values backing this claim")


class ResearchAnswer(BaseModel):
    """Structured output the synthesis LLM call must produce."""
    summary: str = Field(..., description="Concise direct answer to the question, 2-5 sentences")
    claims: List[Claim] = Field(default_factory=list, description="Key supporting claims, each grounded in >=1 source")
    conflicts: List[str] = Field(default_factory=list, description="Points where sources disagree, described plainly")
    uncertainties: List[str] = Field(default_factory=list, description="Aspects of the question left unanswered or under-evidenced")


class ResearchResponse(BaseModel):
    """Top-level API response."""
    question: str
    sub_queries: List[str]
    answer: ResearchAnswer
    sources: List[SourceRef]
    provider_errors: List[str] = Field(default_factory=list, description="Non-fatal provider/fetch failures encountered")
