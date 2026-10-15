import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.reconcile_knowledge_contract import CONTRACT, reconcile
from scripts.upstreams import LOCK, prepare


class OfflineContractTests(unittest.TestCase):
    def test_pinned_contract_reports_source_enum_blocker_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docs.jsonl"
            path.write_text(json.dumps({"source_id": "korean-law-mcp-lab", "document_id": "x"}) + "\n")
            result = reconcile(path, json.loads(CONTRACT.read_text(encoding="utf-8")))
            self.assertFalse(result["compatible"])
            self.assertFalse(result["central_writes"])
            self.assertIn("source_id: invalid enum", [v["code"] for v in result["violations"]])

    def test_full_schema_rejects_bad_values_even_with_allowed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docs.jsonl"
            doc = {key: "" for key in json.loads(CONTRACT.read_text(encoding="utf-8"))["required"]}
            doc.update(source_id="velog", title="", body="", uri="", content_hash="bad",
                       created_at="not-a-date", updated_at="not-a-date", visibility="invalid",
                       lifecycle="tombstoned", deleted_at=None, indexable=True, metadata={}, unexpected="x")
            path.write_text(json.dumps(doc) + "\n")
            result = reconcile(path, json.loads(CONTRACT.read_text(encoding="utf-8")))
            self.assertFalse(result["compatible"])
            codes = [v["code"] for v in result["violations"]]
            self.assertIn("content_hash: invalid pattern", codes)
            self.assertIn("updated_at: invalid date-time", codes)
            self.assertIn("visibility: invalid enum", codes)
            self.assertIn("unexpected: additional property", codes)
            self.assertIn("tombstoned: indexable=false and deleted_at required", codes)

    def test_lock_pins_immutable_commit_and_existing_dirty_checkout_is_untouched(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        for spec in lock["upstreams"]:
            self.assertRegex(spec["commit"], r"^[a-f0-9]{40}$")
            self.assertIn("license", spec)
            self.assertIn("snapshot_source", spec)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "upstreams" / "legalize-kr"
            (target / ".git").mkdir(parents=True)
            spec = lock["upstreams"][0]
            with patch("scripts.upstreams.git", side_effect=[spec["url"], " M file.md"]):
                with self.assertRaisesRegex(ValueError, "dirty"):
                    prepare(Path(tmp), spec)
            self.assertTrue(target.exists())

    def test_existing_shallow_checkout_with_missing_sparse_files_rejected(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        spec = lock["upstreams"][0]
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "upstreams" / "legalize-kr"
            (target / ".git").mkdir(parents=True)
            with patch("scripts.upstreams.git", side_effect=[spec["url"], "", spec["commit"], "true"]):
                with self.assertRaisesRegex(ValueError, "pinned sparse path missing"):
                    prepare(Path(tmp), spec)


if __name__ == "__main__":
    unittest.main()
