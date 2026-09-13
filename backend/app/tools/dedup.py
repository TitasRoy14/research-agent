from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from rapidfuzz import fuzz

from app.schemas import RawResult

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, urlencode(query), ""))


def merge_and_dedupe(results: list[RawResult]) -> list[dict]:
    """Returns a list of dicts: {url, title, snippet, providers: [...]}"""
    merged: list[dict] = []

    for r in results:
        if not r.url:
            continue
        norm = normalize_url(r.url)
        match = None
        for m in merged:
            if m["_norm_url"] == norm:
                match = m
                break
            if fuzz.token_sort_ratio(m["title"], r.title) >= 90:
                match = m
                break
        if match:
            if r.provider not in match["providers"]:
                match["providers"].append(r.provider)
            if len(r.snippet) > len(match["snippet"]):
                match["snippet"] = r.snippet
        else:
            merged.append(
                {
                    "_norm_url": norm,
                    "url": r.url,
                    "title": r.title,
                    "snippet": r.snippet,
                    "providers": [r.provider],
                }
            )

    for m in merged:
        m.pop("_norm_url", None)
    return merged
