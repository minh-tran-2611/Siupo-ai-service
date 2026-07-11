import os
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import httpx
from loguru import logger


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract_page_info(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else None
    description_tag = soup.find("meta", attrs={"name": "description"})
    description = description_tag.get("content", "").strip() if description_tag else ""
    headings = [
        h.get_text(" ", strip=True)
        for h in soup.find_all(["h1", "h2"], limit=8)
        if h.get_text(" ", strip=True)
    ]
    text = " ".join(soup.get_text(" ", strip=True).split())

    return {
        "title": title or url,
        "snippet": description or text[:500],
        "link": url,
        "displayLink": urlparse(url).netloc,
        "headings": headings,
        "content": text[:3000],
    }


async def _fetch_url(url: str) -> dict:
    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 SiupoAI/1.0"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.warning(f"URL fetch failed: {e.response.status_code} {url}")
        return {
            "error": "URL fetch request failed",
            "status_code": e.response.status_code,
            "details": e.response.text[:500],
        }
    except httpx.HTTPError as e:
        logger.warning(f"URL fetch request error: {e}")
        return {"error": "URL fetch request error", "details": str(e)}

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return {
            "results": [{
                "title": str(response.url),
                "snippet": f"Fetched non-HTML content: {content_type or 'unknown content type'}",
                "link": str(response.url),
                "displayLink": urlparse(str(response.url)).netloc,
            }],
            "source": "direct_url",
        }

    return {"results": [_extract_page_info(str(response.url), response.text)], "source": "direct_url"}


async def search_internet(query: str) -> dict:
    """Search the internet using SerpAPI Google Search."""
    logger.info(f"Tool: search_internet({query})")

    if _looks_like_url(query):
        return await _fetch_url(query.strip())

    serpapi_key = os.getenv("SERPAPI_KEY")
    if not serpapi_key:
        return {
            "error": "Missing SERPAPI_KEY. Configure a SerpAPI API key for internet search.",
            "required_env": ["SERPAPI_KEY"],
        }

    params = {
        "engine": "google",
        "q": query,
        "api_key": serpapi_key,
        "num": 5,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://serpapi.com/search.json", params=params)
            response.raise_for_status()
            results = response.json()
    except httpx.HTTPStatusError as e:
        logger.warning(f"SerpAPI search failed: {e.response.status_code} {e.response.text[:300]}")
        return {
            "error": "SerpAPI search request failed",
            "status_code": e.response.status_code,
            "details": e.response.json() if e.response.headers.get("content-type", "").startswith("application/json") else e.response.text,
        }
    except httpx.HTTPError as e:
        logger.warning(f"SerpAPI search request error: {e}")
        return {"error": "SerpAPI search request error", "details": str(e)}

    extracted = []
    for r in results.get("organic_results", [])[:5]:
        extracted.append({
            "title": r.get("title"),
            "snippet": r.get("snippet"),
            "link": r.get("link"),
            "displayLink": r.get("displayed_link") or r.get("source"),
        })

    return {"results": extracted}
