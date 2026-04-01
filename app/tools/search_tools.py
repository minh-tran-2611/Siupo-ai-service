import os
from serpapi import GoogleSearch
from loguru import logger

SERPAPI_KEY = os.getenv("SERPAPI_KEY")


async def search_internet(query: str) -> dict:
    """Search the internet for information using SerpApi."""
    logger.info(f"Tool: search_internet({query})")

    if not SERPAPI_KEY:
        return {"error": "SERPAPI_KEY not configured"}

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": 5
    }

    search = GoogleSearch(params)
    results = search.get_dict()

    # Extract relevant information
    organic_results = results.get("organic_results", [])
    extracted = []
    for r in organic_results[:5]:
        extracted.append({
            "title": r.get("title"),
            "snippet": r.get("snippet"),
            "link": r.get("link")
        })

    return {"results": extracted}
