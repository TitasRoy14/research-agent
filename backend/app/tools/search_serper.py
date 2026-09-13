import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.schemas import RawResult
from app.tools.errors import ProviderError

SERPER_URL = "https://google.serper.dev/search"


@retry(
    stop=stop_after_attempt(settings.max_retries),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError)),
    reraise=True,
)
async def _post(client: httpx.AsyncClient, payload: dict, headers: dict) -> dict:
    resp = await client.post(SERPER_URL, json=payload, headers=headers, timeout=settings.http_timeout_seconds)
    resp.raise_for_status()
    return resp.json()


async def search_serper(query: str, max_results: int = 5) -> list[RawResult]:
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }
    payload = {"q": query, "num": max_results}
    try:
        async with httpx.AsyncClient() as client:
            data = await _post(client, payload, headers)
    except Exception as exc:
        raise ProviderError(f"serper: {exc}") from exc

    results = []
    for item in data.get("organic", [])[:max_results]:
        results.append(
            RawResult(
                provider="serper",
                url=item.get("link", ""),
                title=item.get("title", "") or item.get("link", ""),
                snippet=item.get("snippet", "")[:800],
            )
        )
    return results
