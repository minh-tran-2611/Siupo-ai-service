import os
import httpx

BE_BASE_URL = os.getenv("BE_BASE_URL", "http://host.docker.internal:8080")

# Default timeout: 30 seconds for connect, 60 seconds for read
DEFAULT_TIMEOUT = httpx.Timeout(
    connect=30.0,
    read=60.0,
    write=30.0,
    pool=30.0
)


def get_http_client() -> httpx.AsyncClient:
    """Get a configured async HTTP client with timeout."""
    return httpx.AsyncClient(
        base_url=BE_BASE_URL,
        timeout=DEFAULT_TIMEOUT
    )
