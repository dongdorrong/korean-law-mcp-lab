"""Offline injectable boundary for pinned korean-law-mcp searchLaw XML.

Pinned upstream LawApiClient.searchLaw returns XML text or throws on HTTP error.
No network client or credential handling is implemented here.
"""
from dataclasses import dataclass
from datetime import date as calendar_date
import re
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
        if document.tag != "LawSearch":
            raise ValueError("unexpected search envelope")
        errors = [node for node in document.iter() if node.tag.lower() in {"error", "errormessage", "errorcode", "resultcode", "resultmsg"}]
        if errors:
            message = " ".join("".join(node.itertext()) for node in errors).lower()
            if any(word in message for word in ("auth", "invalid oc", "인증", "apikey", "api key")):
                return {"status": "authentication_failed", "live_verified": False}
            if any(word in message for word in ("rate", "limit", "quota", "호출횟수", "제한")):
                return {"status": "rate_limited", "live_verified": False}
            return {"status": "upstream_error", "live_verified": False}
        counts = [node for node in document if node.tag in {"totalCnt", "검색결과개수"}]
        if len(counts) != 1 or not re.fullmatch(r"\d+", (counts[0].text or "").strip()):
            raise ValueError("missing or invalid result count")
        total = int(counts[0].text.strip())
        hits = []
        for law in document.findall("law"):
            title = law.findtext("법령명한글")
            law_id = law.findtext("법령ID")
            mst = law.findtext("법령일련번호")
            date = law.findtext("공포일자")
            if (not title or not title.strip() or not law_id or not law_id.isdecimal()
                    or not mst or not mst.isdecimal() or (date and not re.fullmatch(r"\d{8}", date))):
                raise ValueError("missing law search field")
            if date:
                calendar_date.fromisoformat(f"{date[:4]}-{date[4:6]}-{date[6:]}")
            hits.append({"law_title": title, "law_id": law_id, "mst": mst,
                         "promulgation_date": date or None,
                         "law_type": law.findtext("법령구분명") or None})
        if total < len(hits) or (total > 0 and not hits):
            raise ValueError("count and search rows disagree")
    except (ElementTree.ParseError, ValueError):
        return {"status": "schema_error", "live_verified": False}
    return {"status": "response_shape_valid_offline" if hits else "no_results_offline",
            "live_verified": False, "hits": hits}
