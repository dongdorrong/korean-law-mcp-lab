"""Offline injectable live-evidence boundary; intentionally has no network transport."""
from dataclasses import dataclass
from typing import Callable, Any


@dataclass(frozen=True)
class TransportError(Exception):
    status: int


def probe_search(client: Callable[[str], Any], query: str) -> dict[str, Any]:
    """Normalize a fake/live transport response without claiming live verification."""
    try:
        response = client(query)
    except TimeoutError:
        return {"status": "timeout", "live_verified": False}
    except TransportError as exc:
        state = {401: "authentication_failed", 403: "authorization_failed", 429: "rate_limited"}.get(exc.status)
        return {"status": state or "upstream_error", "live_verified": False}
    except OSError:
        return {"status": "transport_error", "live_verified": False}
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        return {"status": "schema_error", "live_verified": False}
    if any(not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key]
               for key in ("law_title", "article_no", "text", "source_uri")) for item in response["results"]):
        return {"status": "schema_error", "live_verified": False}
    return {"status": "response_shape_valid_offline", "live_verified": False,
            "results": response["results"]}
