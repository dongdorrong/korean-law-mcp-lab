import copy
import hashlib
import json
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from law_adapter.dry_run import preview
from scripts.export_fordongdorrong_backend import split_articles

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

    def test_missing_official_id_compares_only_same_kind_and_document_id(self):
        for law_id in (None, ""):
            for case in self.case["missing_law_id_cases"]:
                with self.subTest(law_id=law_id, case=case):
                    first = copy.deepcopy(self.doc)
                    first["metadata"]["law_id"] = law_id
                    other = copy.deepcopy(first)
                    other["document_id"] = case["other_document_id"]
                    other["body"] = self.case["conflicting_body"]
                    self.rehash(other)
                    snapshots, users = [first], []
                    (snapshots if case["other_kind"] == "snapshot" else users).append(other)
                    result = self.run_preview(requested_kind="all_offline",
                                              snapshot_documents=snapshots, user_documents=users)
                    self.assertEqual(len(result["evidence"]), 2)
                    self.assertEqual({i["freshness_status"] for i in result["evidence"]}, {case["expected"]})

    def test_weak_section_identity_is_visible_even_when_content_changes_key(self):
        documents = []
        for text in ("이전 합성 근거.", "변경된 합성 근거."):
            body = f"## 부칙\n##### 제1조 (시행일)\n{text}\n"
            article = next(a for a in split_articles(body) if a.article_no == "제1조")
            doc = copy.deepcopy(self.doc)
            doc["body"] = article.body
            doc["metadata"].update(section_identity=article.section_key,
                                    identity_strength="section_content_weak")
            self.rehash(doc)
            documents.append(doc)
        self.assertNotEqual(documents[0]["metadata"]["section_identity"],
                            documents[1]["metadata"]["section_identity"])
        result = self.run_preview(snapshot_documents=documents)
        self.assertEqual(len(result["evidence"]), 2)
        for item in result["evidence"]:
            self.assertEqual(item["citation"]["identity_strength"], "section_content_weak")
            self.assertEqual(item["freshness_status"], "unknown")
        del self.doc["metadata"]["identity_strength"]
        self.assertIsNone(self.run_preview(snapshot_documents=[self.doc])["evidence"][0]
                          ["citation"]["identity_strength"])

    def test_source_modified_at_requires_timezone_timestamp_or_null(self):
        for value in ("어제", {}, "2026-11-01T00:00:00", "2026-02-30T00:00:00Z",
                      "2026-11-01T00:00:00+24:00"):
            for kind in ("snapshot", "user_provided"):
                with self.subTest(value=value, kind=kind), self.assertRaises(ValueError):
                    self.doc["metadata"]["source_modified_at"] = value
                    self.run_preview(requested_kind=kind, **{
                        "snapshot_documents" if kind == "snapshot" else "user_documents": [self.doc]})
        for value in (None, "2026-10-01T12:00:00+09:00"):
            self.doc["metadata"]["source_modified_at"] = value
            self.assertEqual(self.run_preview(snapshot_documents=[self.doc])["evidence"][0]
                             ["source_modified_at"], value)

    def test_snapshot_commit_requires_full_hex_without_promoting_user_claims(self):
        for value in ("claimed", "a" * 39, "g" * 40, "a" * 41, {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "upstream_commit"):
                self.doc["metadata"]["upstream_commit"] = value
                self.run_preview(snapshot_documents=[self.doc])
        for value in (None, "abcdef0123" * 4, "ABCDEF0123" * 4):
            self.doc["metadata"]["upstream_commit"] = value
            self.assertEqual(self.run_preview(snapshot_documents=[self.doc])["evidence"][0]
                             ["source"]["upstream_commit"], value)

    def test_observation_policy_bounds_raise_valueerror_before_processing_evidence(self):
        for value in (timedelta.max.days + 1, 10**10):
            for documents in ([], [self.doc]):
                with self.subTest(value=value, documents=bool(documents)), self.assertRaises(ValueError):
                    preview(requested_kind="snapshot", as_of=self.case["as_of"],
                            snapshot_documents=documents, stale_after_days=value)
        for value in (0, timedelta.max.days):
            result = preview(requested_kind="snapshot", as_of=self.case["as_of"],
                             snapshot_documents=[self.doc], stale_after_days=value)
            self.assertEqual(result["evidence"][0]["freshness_status"], "stale" if value == 0 else "unknown")

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
