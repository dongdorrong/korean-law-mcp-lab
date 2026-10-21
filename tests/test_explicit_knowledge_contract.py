import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.reconcile_knowledge_contract import CONTRACT, SCHEMA, V2_SOURCES, reconcile


class ExplicitKnowledgeContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.historical = SCHEMA.read_bytes()
        self.schema = json.loads(self.historical)
        self.schema["$id"] = "https://fordongdorrong.local/schemas/knowledge-document.v2.schema.json"
        self.schema["title"] = "Synthetic v2 contract"
        self.schema["description"] = "Synthetic source-extension fixture"
        self.schema["properties"]["source_id"]["enum"] = V2_SOURCES
        self.path = self.root / "schema.json"
        self.digest = self.write_schema(self.schema)
        self.jsonl = self.root / "export.jsonl"
        body = "Synthetic law article."
        self.doc = dict(source_id="korean-law-mcp-lab", document_id="synthetic/1",
                        title="Synthetic", body=body, uri="synthetic/1",
                        content_hash="sha256:" + hashlib.sha256(body.encode()).hexdigest(),
                        created_at=None, updated_at="2026-10-21T00:00:00Z", visibility="private",
                        lifecycle="active", deleted_at=None, indexable=True, metadata={})
        self.write_doc(self.doc)

    def write_schema(self, schema):
        raw = json.dumps(schema).encode()
        self.path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def write_doc(self, doc):
        self.jsonl.write_text(json.dumps(doc) + "\n", encoding="utf-8")

    def opt_in(self, **kwargs):
        return reconcile(self.jsonl, self.contract,
                         schema_path=kwargs.get("path", self.path),
                         expected_schema_sha256=kwargs.get("digest", self.digest))

    def test_opt_in_accepts_law_without_rewriting_default_pin_or_claiming_history(self):
        before = reconcile(self.jsonl, self.contract)
        self.assertFalse(before["compatible"])
        self.assertEqual([v["code"] for v in before["violations"]], ["source_id: invalid enum"])
        result = self.opt_in()
        self.assertTrue(result["compatible"])
        self.assertFalse(result["central_writes"])
        self.assertIsNone(result["central_commit"])
        self.assertEqual(result["schema_sha256"], self.digest)
        self.assertEqual(result["contract_selection"], "explicit_local_v2")
        self.assertEqual(SCHEMA.read_bytes(), self.historical)
        self.assertEqual(reconcile(self.jsonl, self.contract), before)

    def test_path_and_hash_are_a_required_pair(self):
        for args in ({"schema_path": self.path}, {"expected_schema_sha256": self.digest}):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, "together"):
                reconcile(self.jsonl, self.contract, **args)

    def test_bad_hash_and_malformed_digest_fail_closed(self):
        for digest in ("0" * 64, "invalid", "A" * 64):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                self.opt_in(digest=digest)

    def test_symlinks_traversal_special_files_and_oversized_schema_rejected(self):
        symlink = self.root / "schema-link.json"
        symlink.symlink_to(self.path)
        ancestor = self.root / "linked-directory"
        ancestor.symlink_to(self.root, target_is_directory=True)
        fifo = self.root / "schema-fifo"
        os.mkfifo(fifo)
        oversized = self.root / "oversized.json"
        oversized.write_bytes(b" " * (1024 * 1024 + 1))
        for path in (symlink, ancestor / self.path.name, self.root / ".." / self.root.name / self.path.name,
                     self.root, fifo, oversized):
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                self.opt_in(path=path)

    def test_unknown_constraints_or_source_removal_are_not_silently_ignored(self):
        mutations = []
        schema = copy.deepcopy(self.schema)
        schema["properties"]["body"]["maxLength"] = 1
        mutations.append(schema)
        schema = copy.deepcopy(self.schema)
        schema["required"].remove("body")
        mutations.append(schema)
        schema = copy.deepcopy(self.schema)
        schema["properties"]["source_id"]["enum"] = ["korean-law-mcp-lab"]
        mutations.append(schema)
        schema = copy.deepcopy(self.schema)
        schema["properties"] = []
        mutations.append(schema)
        for schema in mutations:
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                self.opt_in(digest=self.write_schema(schema))

    def test_explicit_contract_preserves_document_validation(self):
        doc = dict(self.doc, visibility="unexpected", content_hash="wrong")
        self.write_doc(doc)
        result = self.opt_in()
        self.assertFalse(result["compatible"])
        self.assertIn("visibility: invalid enum", [v["code"] for v in result["violations"]])
        self.assertIn("content_hash: invalid pattern", [v["code"] for v in result["violations"]])

    def test_cli_explicit_selection_and_missing_hash(self):
        script = Path(__file__).resolve().parents[1] / "scripts/reconcile_knowledge_contract.py"
        args = [sys.executable, str(script), str(self.jsonl), "--schema", str(self.path)]
        missing = subprocess.run(args, capture_output=True, text=True, timeout=10)
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(missing.stdout, "")
        valid = subprocess.run(args + ["--expected-schema-sha256", self.digest],
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertTrue(json.loads(valid.stdout)["compatible"])


if __name__ == "__main__":
    unittest.main()
