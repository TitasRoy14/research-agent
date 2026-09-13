import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings

MAX_CHARS = 4000


@retry(
    stop=stop_after_attempt(2),  # content fetch is best-effort: fail fast, don't stall the pipeline
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
    reraise=True,
)
async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    resp = await client.get(url, timeout=settings.http_timeout_seconds, follow_redirects=True)
    resp.raise_for_status()
    return resp

async def fetch_page_text(url: str) -> str | None:
    """Returns cleaned page text, or None if the page could not be
    fetched or parsed. Never raises -- a fetch failure degrades to
    'rank/cite on snippet alone', it does not fail the whole request."""
    try:
        async with httpx.AsyncClient(headers={"User-Agent": "ZephraResearchAgent/1.0"}) as client:
            resp = await _get(client, url)
    except Exception:
        return None

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type:
        return None

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        return text[:MAX_CHARS] if text else None
    except Exception:
        return None
