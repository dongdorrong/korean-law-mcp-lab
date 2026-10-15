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
            self.assertIn("SOURCE_ID_NOT_ALLOWED", [v["code"] for v in result["violations"]])

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


if __name__ == "__main__":
    unittest.main()
