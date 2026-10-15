import json
import unittest
from pathlib import Path
from scripts.live_contract import TransportError, probe_search

FIXTURE = Path(__file__).resolve().parent / "fixtures/pinned-mcp-search-contract.json"


class FakeLiveBoundaryTests(unittest.TestCase):
    def test_pinned_xml_shape_and_fake_error_states(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual("f71b28c992db7b1347b7cfb68695c38392339ef0", fixture["commit"])
        self.assertEqual("authentication_failed", probe_search(lambda _: (_ for _ in ()).throw(TransportError(401)), "x")["status"])
        self.assertEqual("authorization_failed", probe_search(lambda _: (_ for _ in ()).throw(TransportError(403)), "x")["status"])
        self.assertEqual("rate_limited", probe_search(lambda _: (_ for _ in ()).throw(TransportError(429)), "x")["status"])
        self.assertEqual("upstream_error", probe_search(lambda _: (_ for _ in ()).throw(TransportError(503)), "x")["status"])
        self.assertEqual("transport_error", probe_search(lambda _: (_ for _ in ()).throw(OSError()), "x")["status"])
        self.assertEqual("timeout", probe_search(lambda _: (_ for _ in ()).throw(TimeoutError()), "x")["status"])
        self.assertEqual("schema_error", probe_search(lambda _: "<LawSearch><law><법령명한글>bad</law></LawSearch>", "x")["status"])
        self.assertEqual("schema_error", probe_search(lambda _: "<LawSearch><law><법령명한글>bad</법령명한글></law></LawSearch>", "x")["status"])
        result = probe_search(lambda _: fixture["synthetic_response"], "합성")
        self.assertEqual("response_shape_valid_offline", result["status"])
        self.assertEqual("000001", result["hits"][0]["law_id"])
        self.assertFalse(result["live_verified"])


if __name__ == "__main__":
    unittest.main()
