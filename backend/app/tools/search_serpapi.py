import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.schemas import RawResult
from app.tools.errors import ProviderError

SERPAPI_URL = "https://serpapi.com/search.json"


@retry(
    stop=stop_after_attempt(settings.max_retries),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError)),
    reraise=True,
)
async def _get(client: httpx.AsyncClient, params: dict) -> dict:
    resp = await client.get(SERPAPI_URL, params=params, timeout=settings.http_timeout_seconds)
    resp.raise_for_status()
    return resp.json()


async def search_serpapi(query: str, max_results: int = 5) -> list[RawResult]:
    params = {
        "engine": "google",
        "q": query,
        "num": max_results,
        "api_key": settings.serpapi_api_key,
    }
    try:
        async with httpx.AsyncClient() as client:
            data = await _get(client, params)
    except Exception as exc:
        raise ProviderError(f"serpapi: {exc}") from exc

    results = []
    for item in data.get("organic_results", [])[:max_results]:
        results.append(
            RawResult(
                provider="serpapi",
                url=item.get("link", ""),
                title=item.get("title", "") or item.get("link", ""),
                snippet=item.get("snippet", "")[:800],
            )
        )
    return results
