import json
import unittest
from pathlib import Path
from scripts.live_contract import TransportError, probe_search

FIXTURE = Path(__file__).resolve().parent / "fixtures/pinned-mcp-search-contract.json"


class FakeLiveBoundaryTests(unittest.TestCase):
    def test_xml_envelope_and_error_are_not_empty_success(self):
        cases = {
            "<LawSearch><totalCnt>0</totalCnt></LawSearch>": "no_results_offline",
            "<LawSearch><totalCnt>0</totalCnt><law/></LawSearch>": "schema_error",
            "<html><body>proxy error</body></html>": "schema_error",
            "<LawSearch><error>invalid authentication</error></LawSearch>": "authentication_failed",
            "<LawSearch><error>rate limit</error></LawSearch>": "rate_limited",
            "<LawSearch></LawSearch>": "schema_error",
            "<LawSearch><totalCnt>-1</totalCnt></LawSearch>": "schema_error",
            "<LawSearch><totalCnt>two</totalCnt></LawSearch>": "schema_error",
            "<LawSearch><totalCnt>1</totalCnt></LawSearch>": "schema_error",
            "<LawSearch><totalCnt>1</totalCnt><law><법령명한글>합성</법령명한글><법령ID>abc</법령ID><법령일련번호>12</법령일련번호></law></LawSearch>": "schema_error",
            "<LawSearch><totalCnt>1</totalCnt><law><법령명한글>합성</법령명한글><법령ID>1</법령ID><법령일련번호>12</법령일련번호><공포일자>tomorrow</공포일자></law></LawSearch>": "schema_error",
            "<LawSearch><totalCnt>0</totalCnt>": "schema_error",
        }
        for response, expected in cases.items():
            with self.subTest(response=response):
                self.assertEqual(expected, probe_search(lambda _: response, "x")["status"])
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        paged = fixture["synthetic_response"].replace("<totalCnt>1</totalCnt>", "<totalCnt>2</totalCnt>")
        self.assertEqual("response_shape_valid_offline", probe_search(lambda _: paged, "x")["status"])

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

    def test_calendar_validity_for_promulgation_date(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        response = fixture["synthetic_response"]
        for invalid in ("20269999", "20260229", "20261301", "00000101", "20260431"):
            with self.subTest(date=invalid):
                xml = response.replace("20260101", invalid)
                self.assertEqual("schema_error", probe_search(lambda _: xml, "x")["status"])
        leap = response.replace("20260101", "20240229")
        self.assertEqual("response_shape_valid_offline", probe_search(lambda _: leap, "x")["status"])


if __name__ == "__main__":
    unittest.main()
