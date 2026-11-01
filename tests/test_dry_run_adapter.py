import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from law_adapter.dry_run import preview

FIXTURE = Path(__file__).parent / "fixtures/legal-evidence-cases.json"


class DryRunAdapterTests(unittest.TestCase):
    def setUp(self):
        self.case = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.doc = dict(document_id="synthetic/law/1", body=self.case["body"],
                        uri="https://example.invalid/synthetic-law", metadata=self.case["metadata"])
        self.rehash(self.doc)

    def rehash(self, doc):
        doc["content_hash"] = "sha256:" + hashlib.sha256(doc["body"].encode()).hexdigest()

    def run_preview(self, **kwargs):
        return preview(requested_kind=kwargs.pop("requested_kind", "snapshot"),
                       as_of=self.case["as_of"], stale_after_days=self.case["stale_after_days"], **kwargs)

    def test_citation_safety_and_future_effective_date_are_preserved(self):
        result = self.run_preview(snapshot_documents=[self.doc])
        item = result["evidence"][0]
        citation = dict(self.case["expected_citation"], revision=self.doc["content_hash"])
        self.assertEqual(item["citation"], citation)
        self.assertEqual(item["temporal_relation"], "future_enforcement_date")
        self.assertEqual(item["legal_effect_status"], "not_determined")
        self.assertEqual(item["amendment_status"], "not_determined")
        self.assertEqual(item["supersession_status"], "not_determined")
        self.assertFalse(item["legal_advice"])
        self.assertTrue(item["human_review_required"])
        self.assertFalse(item["live_verified"])
        self.assertIsNone(item["live_verified_at"])
        boundary = preview(requested_kind="snapshot", as_of="2026-12-31T16:00:00Z",
                           snapshot_documents=[self.doc])["evidence"][0]
        self.assertEqual(boundary["temporal_relation"], "date_not_future")  # 한국은 이미 1월 1일.

    def test_live_request_never_reads_or_substitutes_offline_material(self):
        def forbidden():
            raise AssertionError("live must not inspect snapshot fallback")
            yield
        result = self.run_preview(requested_kind="live", snapshot_documents=forbidden(), user_documents=forbidden())
        self.assertEqual(result["status"], "live_validation_required")
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["live_validation_status"], "not_tested_owner_key_required")

    def test_user_supplied_claims_cannot_turn_into_live_or_upstream_evidence(self):
        self.doc["metadata"].update(evidence_kind="live", live_verified=True, upstream_commit="claimed")
        result = self.run_preview(requested_kind="user_provided", user_documents=[self.doc])
        item = result["evidence"][0]
        self.assertEqual(item["evidence_kind"], "user_provided")
        self.assertEqual(item["source"]["kind"], "user_supplied")
        self.assertIsNone(item["source"]["upstream_commit"])
        self.assertFalse(item["live_verified"])
        with self.assertRaisesRegex(ValueError, "snapshot provenance"):
            self.run_preview(snapshot_documents=[self.doc])

    def test_latestness_fixture_boundaries_and_missing_observation(self):
        for case in self.case["freshness_cases"]:
            with self.subTest(case=case):
                self.doc["metadata"]["observed_at"] = case["observed_at"]
                item = self.run_preview(snapshot_documents=[self.doc])["evidence"][0]
                self.assertEqual((item["freshness_status"], item["freshness_reason"]),
                                 (case["expected"], case["reason"]))
        self.doc["metadata"]["observed_at"] = "2020-01-01T00:00:00Z"
        item = preview(requested_kind="snapshot", as_of=self.case["as_of"],
                       snapshot_documents=[self.doc])["evidence"][0]
        self.assertEqual(item["freshness_status"], "unknown")

    def test_conflicting_sources_preserved_without_latest_winner_or_input_mutation(self):
        other = copy.deepcopy(self.doc)
        other["body"] = self.case["conflicting_body"]
        other["metadata"]["observed_at"] = "2026-11-01T00:00:00Z"
        self.rehash(other)
        before = copy.deepcopy([self.doc, other])
        result = self.run_preview(requested_kind="all_offline", snapshot_documents=[self.doc], user_documents=[other])
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual({i["evidence_kind"] for i in result["evidence"]}, {"snapshot", "user_provided"})
        self.assertTrue(all(i["freshness_status"] == "conflicting" for i in result["evidence"]))
        self.assertEqual([self.doc, other], before)

    def test_same_text_different_dates_conflicts_but_other_article_does_not(self):
        other = copy.deepcopy(self.doc)
        other["metadata"]["enforcement_date"] = "2028-01-01"
        result = self.run_preview(snapshot_documents=[self.doc, other])
        self.assertTrue(all(i["freshness_status"] == "conflicting" for i in result["evidence"]))
        other["metadata"]["article_no"] = "제2조"
        result = self.run_preview(snapshot_documents=[self.doc, other])
        self.assertTrue(all(i["freshness_status"] == "unknown" for i in result["evidence"]))

    def test_malformed_dates_hash_and_policy_fail_closed(self):
        for key, value in (("observed_at", "2026-11-01"), ("observed_at", "2026-11-01+09:00"),
                           ("promulgation_date", "2026-02-30")):
            doc = copy.deepcopy(self.doc)
            doc["metadata"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_preview(snapshot_documents=[doc])
        for policy in (-1, True, "30"):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                preview(requested_kind="snapshot", as_of=self.case["as_of"], stale_after_days=policy)
        self.doc["body"] += " changed"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.run_preview(snapshot_documents=[self.doc])

    def test_preview_has_no_io_and_explicit_empty_and_kind_selection(self):
        with patch("builtins.open", side_effect=AssertionError("file IO")), \
             patch("os.open", side_effect=AssertionError("file IO")), \
             patch("socket.socket", side_effect=AssertionError("network IO")), \
             patch("subprocess.run", side_effect=AssertionError("subprocess IO")):
            result = self.run_preview(snapshot_documents=[self.doc])
            self.assertFalse(any(result["capabilities"].values()))
            self.assertEqual(self.run_preview(requested_kind="user_provided", snapshot_documents=[self.doc])["status"],
                             "no_evidence")
            self.assertEqual(self.run_preview()["status"], "no_evidence")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.run_preview(requested_kind="automatic_live_fallback")


if __name__ == "__main__":
    unittest.main()
