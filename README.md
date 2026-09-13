# Zephra Multi-Source Web Research Agent

A research agent that answers a natural-language question by querying
two independent web-search providers, deduplicating and ranking the
results, fetching page content where needed, and synthesizing a
grounded answer with inline source citations, conflict notes, and
explicit uncertainty.

## Problem understanding

The brief asks for more than a "search → paste into an LLM" chain: the
core requirement is that the final answer be **grounded in retrieved,
vetted evidence**, with every claim traceable to a source, and with the
system explicit about what it *doesn't* know rather than filling gaps
from the model's general knowledge. Three things follow from that:

- **Two genuinely independent sources are required, not one source
  queried twice.** A single retriever, however good, has one failure
  mode (its own index/ranking bias); grounding claims against two
  separately-run providers gives an actual cross-check.
- **Retrieval, filtering, and answering have to be separable stages,
  each with its own failure handling** — the brief specifically calls
  out provider failures, rate limits, and timeouts as things the system
  must survive, which only makes sense if those stages are distinct
  enough to fail independently without taking down the whole request.
- **"Correct" here means defensible, not just fluent.** A confident,
  well-written answer with no real evidence behind it is a worse
  outcome than a shorter answer that says plainly what's uncertain or
  contested — so uncertainty and conflicting-source handling are
  first-class outputs, not an afterthought bolted onto the prompt.

The architecture below is a direct translation of those three points
into pipeline stages.

## Architecture

```
POST /research
      │
      ▼
   [plan]  ── decompose question into 2-4 sub-queries (LLM)
      │
      ├──────────────┬───────────────
      ▼              ▼
[search_serper]  [search_serpapi]    ── run concurrently, independent providers
      │              │
      └──────┬───────┘
             ▼
      [merge_dedupe]  ── normalize URLs, fuzzy-match titles, merge providers
             │
             ▼
      [fetch_content] ── fetch + extract text for top-N sources, best-effort
             │
             ▼
          [rank]       ── LLM scores relevance/credibility, drops weak sources
             │
             ▼
       [synthesize]    ── structured, cited answer + conflicts + uncertainties
             │
             ▼
        JSON response
```

Implemented as a LangGraph `StateGraph`: `backend/app/graph.py`. Each
step is a thin node wrapping a standalone, independently testable
function in `backend/app/tools/`.

- **Backend**: Python, FastAPI, LangGraph, LangChain
- **Frontend**: Next.js (App Router) + Tailwind, calls the backend over REST
- **LLM**: any model via [OpenRouter](https://openrouter.ai), accessed
  through `langchain_openai.ChatOpenAI` pointed at OpenRouter's
  OpenAI-compatible `base_url` (not the dedicated `langchain-openrouter`
  package — see below). Default model `anthropic/claude-sonnet-4.5`,
  configurable via `OPENROUTER_MODEL`
- **Search providers**: [Serper](https://serper.dev) (primary — Google
  SERP results) and [SerpApi](https://serpapi.com) (secondary — an
  independently run scraping/parsing pipeline over Google results)

## Why these technology choices

- **LangGraph over a plain chain**: the brief requires distinct,
  independently reasoned stages (decompose → retrieve → merge → rank →
  synthesize) with per-stage failure handling. A graph makes the fan-out
  (parallel search) and fan-in (merge waits for both branches) explicit
  and inspectable, rather than folding everything into one prompt.
- **Serper + SerpApi, not Tavily + Brave**: Brave Search API eliminated
  its card-free tier in February 2026 (every plan now requires a
  credit card on file, even the free monthly credit), which broke this
  project's original no-credit-card requirement. Serper and SerpApi
  are both real Google SERP data (organic results, snippets, featured
  answers) pulled through two independently run scraping/parsing
  pipelines — not two clients hitting the same underlying index — and
  both offer card-free signup.
- **`ChatOpenAI` against OpenRouter's endpoint, not the dedicated
  `langchain-openrouter` package**: the dedicated package was tried
  first, but it has an open bug
  ([langchain-ai/langchain#40364](https://github.com/langchain-ai/langchain/issues/40364)):
  OpenRouter reports some upstream provider faults as HTTP 200 with the
  error embedded in the response body, and that package's response
  parser doesn't handle that path — it corrupts structured-output
  parsing instead of raising a clean, catchable error. This surfaced
  directly during testing as a `ValidationError` on `rank`/`synthesize`
  with no informative cause. Switching to `ChatOpenAI` with
  `base_url="https://openrouter.ai/api/v1"` keeps the same OpenRouter
  account, key, and model, but uses the far more mature OpenAI-compatible
  client, which doesn't have this defect.
- **FastAPI**: native `async`/`await` needed to run both search
  providers and multiple page fetches concurrently without blocking.
- **Next.js**: single-question-in, structured-answer-out UI does not
  need SSR/data-fetching complexity; the App Router client component
  hits the FastAPI backend directly over REST.
- **MCP was deliberately not used.** MCP standardizes tool exposure
  for arbitrary external clients (IDEs, other agents). This project is
  a single-purpose backend calling two APIs directly; adding an MCP
  server/client layer would add protocol overhead without improving
  correctness, reliability, or evaluability, and no other agent is
  meant to reuse these tools independently.

## Key engineering decisions

- **Source selection**: Serper and SerpApi were chosen for genuine
  pipeline independence (separate scraping/parsing infrastructure over
  Google results) and card-free signup, making the project reproducible
  for a reviewer without a paid account. Trade-off worth knowing:
  Serper's free allowance (2,500 queries) is a one-time grant, not
  monthly, while SerpApi's (250/month) renews — so SerpApi is the more
  durable of the two if the repo sits unused for a while before review.
- **Merging & dedup**: URL normalization (strips scheme/tracking
  params/trailing slash) catches exact duplicates; `rapidfuzz`
  title-similarity (≥90) catches same-article-different-URL cases
  (e.g. AMP pages). Embedding-based semantic dedup was considered and
  rejected for this scope — it adds a model call per source for a
  problem URL+title matching already resolves in the common case. This
  is documented as a known limitation below.
- **Ranking**: a dedicated LLM call scores each merged source on
  relevance, credibility, and (for time-sensitive questions)
  recency, and sources below a 0.4 floor are dropped **before**
  synthesis — so weak evidence can't leak into the final answer even
  if the synthesis prompt is imperfect.
- **Conflict handling**: the synthesis prompt explicitly instructs the
  model not to silently resolve disagreements between sources; it must
  surface them in a separate `conflicts` field instead.
- **Hallucination reduction**: synthesis uses `with_structured_output`
  against a Pydantic schema that requires every `Claim` to list the
  `source_id`s backing it. Ranking already filtered out low-credibility
  sources, so the model is grounding claims only in vetted evidence.
- **Provider failure handling**: each search call is wrapped in
  `tenacity` retries (exponential backoff, 3 attempts) and a
  `ProviderError` is caught per-provider, per-sub-query — one
  provider failing doesn't take down the other. If **both** providers
  fail for every sub-query, the graph still completes and the API
  returns a clear `502` with the collected error messages instead of a
  generic exception. Page-content fetching is treated as strictly
  best-effort (2 retries, short timeout): a failed fetch just means
  that source is ranked/cited on its search snippet instead of full
  text, and never fails the request.
- **Planning fallback**: if the sub-query decomposition LLM call fails,
  the pipeline falls back to using the raw question as a single
  sub-query rather than aborting.

## Setup & execution

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env        # Windows: copy; macOS/Linux: cp
# fill in OPENROUTER_API_KEY, SERPER_API_KEY, SERPAPI_API_KEY in .env
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
copy .env.local.example .env.local   # Windows: copy; macOS/Linux: cp
npm run dev
```

Open `http://localhost:3000`, ask a question, and the frontend calls
the backend at `http://localhost:8000/research`.

### API only

```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the current risks of large-scale offshore wind projects?"}'
```

## Known limitations

- Dedup is URL/title-based, not semantic — two genuinely different
  URLs covering the same underlying fact without similar titles will
  be treated as separate sources.
- Content fetching only handles `text/html`; PDFs and JS-rendered
  pages are skipped (fall back to the search snippet).
- No persistence/caching layer — repeated identical questions re-run
  the full pipeline and re-spend API/search credits.
- Serper's free allowance (2,500 queries) is a one-time grant and does
  not renew monthly like SerpApi's — a repo that sits unused for a
  while may need a fresh Serper key or a small top-up before demoing.
- No streaming: the API returns the full result in one response, so
  the frontend shows a single loading state rather than live
  per-stage progress.
- Ranking and synthesis are separate LLM calls (by design, for
  separation of concerns and to allow a hard relevance floor before
  synthesis), which costs extra latency/tokens versus a single
  combined call.

## Possible future improvements

- Add a third, structurally different retrieval source (e.g. a
  domain-specific API or vector store over pre-indexed documents) to
  reduce reliance on general web search.
- Embedding-based near-duplicate detection for sources with dissimilar
  titles but overlapping content.
- Stream pipeline stage progress to the frontend over SSE/WebSocket.
- Cache search/fetch results by normalized query to cut cost on
  repeated or overlapping questions.
- PDF and JS-rendered page extraction (headless browser fallback).

## What I personally implemented

The core technology decisions — Pydantic models to define the shape of
every piece of data in the pipeline, Next.js for the frontend, and
FastAPI over Django for the backend (native `async`/`await` for
concurrent search/fetch calls) — are mine. I personally implemented
`app/tools/rank.py` and `app/tools/synthesize.py`, the two LLM-driven
stages where the evidence-scoring and grounded-citation requirements in
the brief actually live. The remaining scaffolding (search/fetch/dedup
tool modules, the LangGraph wiring, the FastAPI endpoint, the Next.js
UI) was built with AI-assisted tooling under my direction, following
the decisions above; I reviewed, debugged, and fixed real issues in
that code during testing, including the dependency-resolution conflict
on the LangChain 1.x upgrade and the `langchain-openrouter` bug
described above.