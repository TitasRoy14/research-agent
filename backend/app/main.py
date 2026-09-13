from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import ResearchRequest, ResearchResponse
from app.graph import research_graph, to_source_refs, GraphState

app = FastAPI(title="Zephra Multi-Source Research Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/research", response_model=ResearchResponse)
async def research(req: ResearchRequest) -> ResearchResponse:
    initial_state: GraphState = {
        "question": req.question,
        "sub_queries": [],
        "raw_results": [],
        "merged_sources": [],
        "ranked_sources": [],
        "answer": None,
        "errors": [],
    }

    final_state = await research_graph.ainvoke(initial_state)

    if final_state["answer"] is None:
        # Every provider failed and synthesis never ran -- surface this
        # as a clear 502 rather than a generic 500.
        raise HTTPException(
            status_code=502,
            detail={"message": "Unable to retrieve any evidence.", "errors": final_state["errors"]},
        )

    return ResearchResponse(
        question=req.question,
        sub_queries=final_state["sub_queries"],
        answer=final_state["answer"],
        sources=to_source_refs(final_state["ranked_sources"]),
        provider_errors=final_state["errors"],
    )
