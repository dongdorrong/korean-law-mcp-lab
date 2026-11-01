import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from law_adapter.dry_run import preview
from scripts.export_fordongdorrong_backend import export_backend
from scripts.reconcile_knowledge_contract import CONTRACT, reconcile_sqlite

FIXTURES = Path(__file__).parent / "fixtures"


class SQLiteKnowledgeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        source = self.root / "kr/합성법"
        source.mkdir(parents=True)
        (source / "법률.md").write_text(
            "---\n제목: 합성법\n법령ID: 000001\n법령구분: 법률\n공포일자: 2026-01-01\n---\n"
            "##### 제1조 (목적)\n합성 근거.\n", encoding="utf-8")
        self.jsonl, self.db = self.root / "out.jsonl", self.root / "out.db"
        self.manifest = self.root / "manifest.json"
        export_backend(root=self.root, source_dir=source.parent, jsonl_path=self.jsonl,
                       sqlite_path=self.db, manifest_path=self.manifest)
        self.contract = json.loads(CONTRACT.read_text())
        self.v2 = json.loads((FIXTURES / "central-knowledge-v2-contract.json").read_text())
        self.selection = dict(schema_path=FIXTURES / "knowledge-document.v2.schema.json",
                              expected_schema_sha256=self.v2["schema_sha256"])

    def report(self, **kwargs):
        return reconcile_sqlite(self.db, self.jsonl, self.contract, **kwargs)

    def test_new_jsonl_sqlite_full_parity_matches_pinned_actual_central_v2(self):
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir() if p.is_file()}
        report = self.report(**self.selection)
        self.assertTrue(report["compatible"], report)
        self.assertTrue(report["jsonl_sqlite_parity"])
        self.assertEqual(report["sqlite_documents"], report["documents"])
        self.assertFalse(report["central_writes"])
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(before, after)  # Includes absence of new WAL/journal/sidecars.
        doc = json.loads(self.jsonl.read_text().splitlines()[0])
        self.assertTrue(doc["metadata"]["human_review_required"])
        self.assertFalse(doc["metadata"]["live_verified"])
        result = preview(requested_kind="snapshot", as_of=doc["updated_at"], snapshot_documents=[doc])
        self.assertEqual(result["evidence"][0]["citation"]["revision"], doc["content_hash"])
        safety = json.loads(self.manifest.read_text())["safety"]
        self.assertTrue(safety["human_review_required"])
        self.assertFalse(safety["external_writes"])
        http = json.loads(self.manifest.read_text())["live_mcp"]["http"]
        self.assertIn("18765", http["args"])
        self.assertEqual(http["health"], "http://127.0.0.1:18765/health")

    def test_default_v1_still_reports_source_gate_without_relabeling(self):
        report = self.report()
        self.assertFalse(report["compatible"])
        self.assertTrue(report["jsonl_sqlite_parity"])
        self.assertEqual({v["code"] for v in report["violations"]},
                         {"source_id: invalid enum", "sqlite: source_id: invalid enum"})

    def test_body_mutation_is_detected_even_with_unchanged_id_hash_metadata(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE documents SET body='different evidence'")
        report = self.report(**self.selection)
        self.assertFalse(report["compatible"])
        self.assertFalse(report["jsonl_sqlite_parity"])

    def test_legacy_missing_deleted_at_is_explicitly_incompatible(self):
        with sqlite3.connect(self.db) as conn:
            columns = [r[1] for r in conn.execute("PRAGMA table_info(documents)") if r[1] != "deleted_at"]
            conn.execute("CREATE TABLE legacy AS SELECT " + ",".join(columns) + " FROM documents")
            conn.execute("DROP TABLE documents")
            conn.execute("ALTER TABLE legacy RENAME TO documents")
        report = self.report(**self.selection)
        self.assertFalse(report["compatible"])
        self.assertTrue(any("deleted_at" in v["code"] for v in report["violations"]))

    def test_invalid_indexable_and_missing_database_fail_without_creating_files(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE documents SET indexable=2")
        self.assertFalse(self.report(**self.selection)["compatible"])
        missing = self.root / "missing.db"
        report = reconcile_sqlite(missing, self.jsonl, self.contract, **self.selection)
        self.assertFalse(report["compatible"])
        self.assertFalse(missing.exists())

    def test_tombstone_deleted_at_roundtrip_and_constraint(self):
        docs = [json.loads(line) for line in self.jsonl.read_text().splitlines()]
        for doc in docs:
            doc.update(lifecycle="tombstoned", indexable=False, deleted_at="2026-11-01T00:00:00Z")
        self.jsonl.write_text("\n".join(json.dumps(d) for d in docs) + "\n")
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE documents SET lifecycle='tombstoned', indexable=0, deleted_at='2026-11-01T00:00:00Z'")
        self.assertTrue(self.report(**self.selection)["compatible"])
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE documents SET deleted_at=NULL")
        report = self.report(**self.selection)
        self.assertFalse(report["compatible"])
        self.assertTrue(any("tombstoned" in v["code"] for v in report["violations"]))

    def test_cli_exit_status_matches_compatibility_for_jsonl_and_sqlite(self):
        script = Path(__file__).resolve().parents[1] / "scripts/reconcile_knowledge_contract.py"
        base = [sys.executable, str(script), str(self.jsonl)]
        v2 = ["--schema", str(self.selection["schema_path"].resolve()),
              "--expected-schema-sha256", self.v2["schema_sha256"]]

        def check(args, compatible):
            result = subprocess.run(base + args, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0 if compatible else 1, result.stderr)
            self.assertEqual(json.loads(result.stdout)["compatible"], compatible)
            self.assertEqual(result.stderr, "")

        check([], False)  # Historical v1 source gate must also fail in a shell.
        check(v2, True)
        sqlite_args = v2 + ["--sqlite", str(self.db)]
        check(sqlite_args, True)
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE documents SET title='changed title'")
        check(sqlite_args, False)  # Valid schema, broken parity.
        with sqlite3.connect(self.db) as conn:
            conn.execute("ALTER TABLE documents DROP COLUMN deleted_at")
        check(sqlite_args, False)  # Legacy schema cannot silently pass.


if __name__ == "__main__":
    unittest.main()
