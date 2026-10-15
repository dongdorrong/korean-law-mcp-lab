import unittest
from scripts.live_contract import TransportError, probe_search


class FakeLiveBoundaryTests(unittest.TestCase):
    def test_auth_rate_timeout_schema_states(self):
        self.assertEqual("authentication_failed", probe_search(lambda _: (_ for _ in ()).throw(TransportError(401)), "x")["status"])
        self.assertEqual("rate_limited", probe_search(lambda _: (_ for _ in ()).throw(TransportError(429)), "x")["status"])
        self.assertEqual("authorization_failed", probe_search(lambda _: (_ for _ in ()).throw(TransportError(403)), "x")["status"])
        self.assertEqual("upstream_error", probe_search(lambda _: (_ for _ in ()).throw(TransportError(503)), "x")["status"])
        self.assertEqual("transport_error", probe_search(lambda _: (_ for _ in ()).throw(OSError()), "x")["status"])
        self.assertEqual("timeout", probe_search(lambda _: (_ for _ in ()).throw(TimeoutError()), "x")["status"])
        self.assertEqual("schema_error", probe_search(lambda _: {"results": [{"law_title": "x"}]}, "x")["status"])
        valid = probe_search(lambda _: {"results": [{"law_title": "합성", "article_no": "제1조", "text": "합성", "source_uri": "synthetic://law"}]}, "x")
        self.assertEqual("response_shape_valid_offline", valid["status"])
        self.assertFalse(valid["live_verified"])


if __name__ == "__main__":
    unittest.main()
