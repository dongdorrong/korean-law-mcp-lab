"""Offline injectable boundary for pinned korean-law-mcp searchLaw XML.

Pinned upstream LawApiClient.searchLaw returns XML text or throws on HTTP error.
No network client or credential handling is implemented here.
"""
from dataclasses import dataclass
from typing import Callable, Any
from xml.etree import ElementTree


@dataclass(frozen=True)
class TransportError(Exception):
    status: int


def probe_search(client: Callable[[str], str], query: str) -> dict[str, Any]:
    """Classify fake transport errors and parse pinned search_law XML law tags."""
    try:
        xml_text = client(query)
    except TimeoutError:
        return {"status": "timeout", "live_verified": False}
    except TransportError as exc:
        state = {401: "authentication_failed", 403: "authorization_failed", 429: "rate_limited"}.get(exc.status)
        return {"status": state or "upstream_error", "live_verified": False}
    except OSError:
        return {"status": "transport_error", "live_verified": False}
    if not isinstance(xml_text, str) or "<!DOCTYPE" in xml_text.upper():
        return {"status": "schema_error", "live_verified": False}
    try:
        document = ElementTree.fromstring(xml_text)
        hits = []
        for law in document.iter("law"):
            title = law.findtext("법령명한글")
            law_id = law.findtext("법령ID")
            mst = law.findtext("법령일련번호")
            if not title or not law_id or not mst:
                raise ValueError("missing law search field")
            hits.append({"law_title": title, "law_id": law_id, "mst": mst,
                         "promulgation_date": law.findtext("공포일자") or None,
                         "law_type": law.findtext("법령구분명") or None})
    except (ElementTree.ParseError, ValueError):
        return {"status": "schema_error", "live_verified": False}
    return {"status": "response_shape_valid_offline" if hits else "no_results_offline",
            "live_verified": False, "hits": hits}
