"""
Crawl config persistence — stores the list of target URLs the crawl agent
fetches. Persisted to a JSON file under data/ so it survives restarts and is
editable at runtime from the admin UI (PUT /agents/crawl/config).
"""
import json
import os
import threading
from pathlib import Path

from loguru import logger

# Default URLs — used on first run / when the config file is missing.
# Can also be overridden via env var CRAWL_TARGET_URLS (comma-separated).
_DEFAULT_URLS = [
    "https://www.foody.vn/ho-chi-minh/chuyen-muc/do-an",
    "https://www.grab.com/vn/food/",
    "https://bep.vn/tin-tuc",
    "https://www.nhahangviet.vn/tin-tuc",
    "https://www.ngonaz.com/tin-tuc",
]

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "crawl_config.json"
_lock = threading.Lock()


def _env_defaults() -> list[str]:
    raw = os.getenv("CRAWL_TARGET_URLS")
    if raw:
        urls = [u.strip() for u in raw.split(",") if u.strip()]
        if urls:
            return urls
    return list(_DEFAULT_URLS)


def get_crawl_urls() -> list[str]:
    """Return the currently configured crawl URLs.

    Reads from the JSON config file; falls back to env/defaults if the file
    is missing or unreadable.
    """
    try:
        if _CONFIG_PATH.exists():
            with _lock:
                data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            urls = data.get("urls")
            if isinstance(urls, list):
                cleaned = [u.strip() for u in urls if isinstance(u, str) and u.strip()]
                return cleaned
    except Exception as e:
        logger.warning(f"Crawl config: failed to read {_CONFIG_PATH}: {e}")
    return _env_defaults()


def set_crawl_urls(urls: list[str]) -> list[str]:
    """Persist a new list of crawl URLs. Returns the cleaned list that was saved."""
    cleaned: list[str] = []
    seen = set()
    for u in urls:
        if not isinstance(u, str):
            continue
        s = u.strip()
        if s and s not in seen:
            seen.add(s)
            cleaned.append(s)

    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            _CONFIG_PATH.write_text(
                json.dumps({"urls": cleaned}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        logger.info(f"Crawl config: saved {len(cleaned)} URLs to {_CONFIG_PATH}")
    except Exception as e:
        logger.error(f"Crawl config: failed to write {_CONFIG_PATH}: {e}")
        raise

    return cleaned
