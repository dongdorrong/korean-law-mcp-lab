from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.export_fordongdorrong_backend import export_backend, split_articles, split_frontmatter, verify_published


SAMPLE_LAW = """---
제목: 테스트법
법령MST: 123456
법령ID: '009999'
법령구분: 법률
소관부처:
- 테스트부
공포일자: 2026-01-02
시행일자: 2026-03-04
상태: 시행
출처: https://www.law.go.kr/법령/테스트법
---

# 테스트법

##### 제1조 (목적)

이 법은 테스트 목적을 정한다.

##### 제2조 (정의)

이 법에서 "문서"란 검색 가능한 근거를 말한다.
"""


class ExportFordongdorrongBackendTests(unittest.TestCase):
    def test_manifest_checksum_rejects_interrupted_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            paths = (root / "out.jsonl", root / "out.db", root / "manifest.json")
            export_backend(root=root, source_dir=source.parent, jsonl_path=paths[0],
                           sqlite_path=paths[1], manifest_path=paths[2])
            self.assertTrue(verify_published(*paths))
            paths[0].write_text("{}\n", encoding="utf-8")
            self.assertFalse(verify_published(*paths))

    def test_publish_failure_rejects_mixed_generation(self) -> None:
        from scripts import export_fordongdorrong_backend as exporter
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            path = source / "법률.md"
            path.write_text(SAMPLE_LAW, encoding="utf-8")
            paths = (root / "out.jsonl", root / "out.db", root / "manifest.json")
            args = dict(root=root, source_dir=source.parent, jsonl_path=paths[0],
                        sqlite_path=paths[1], manifest_path=paths[2])
            exporter.export_backend(**args)
            path.write_text(SAMPLE_LAW.replace("검색 가능한 근거", "변경된 근거"), encoding="utf-8")
            original_replace = os.replace
            calls = 0
            def fail_second(src, dst):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected publish interruption")
                return original_replace(src, dst)
            with patch.object(exporter.os, "replace", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "interruption"):
                    exporter.export_backend(**args)
            self.assertFalse(verify_published(*paths))

    def test_limit_is_partial_and_duplicate_source_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            paths = (root / "out.jsonl", root / "out.db", root / "manifest.json")
            export_backend(root=root, source_dir=source.parent, jsonl_path=paths[0],
                           sqlite_path=paths[1], manifest_path=paths[2], limit=1)
            manifest = json.loads(paths[2].read_text(encoding="utf-8"))
            self.assertFalse(manifest["generation"]["complete_snapshot"])
            self.assertEqual("partial_smoke_only", manifest["local_export"]["status"])
            (source / "법률.md").write_text(SAMPLE_LAW.replace("##### 제2조", "##### 제1조"), encoding="utf-8")
            with self.assertRaises(ValueError):
                export_backend(root=root, source_dir=source.parent, jsonl_path=paths[0],
                               sqlite_path=paths[1], manifest_path=paths[2])
            self.assertTrue(verify_published(*paths))

    def test_article_id_survives_insertion_and_sections_do_not_collide(self) -> None:
        from scripts.export_fordongdorrong_backend import knowledge_documents
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "upstreams/legalize-kr/kr/테스트법"
            source.mkdir(parents=True)
            path = source / "법률.md"
            path.write_text(SAMPLE_LAW, encoding="utf-8")
            original = list(knowledge_documents(source.parent, root, "2026-01-01T00:00:00Z", None))
            path.write_text(SAMPLE_LAW.replace("##### 제2조", "##### 제1조의2 (삽입)\n\n삽입 조문.\n\n##### 제2조") + "\n## 부칙 <제2026호>\n##### 제1조 (시행일)\n본문.\n", encoding="utf-8")
            changed = list(knowledge_documents(source.parent, root, "2026-01-01T00:00:00Z", None))
            self.assertEqual(original[1]["document_id"], changed[2]["document_id"])
            self.assertEqual(len(changed), len({doc["document_id"] for doc in changed}))

    def test_repeated_supplemental_article_numbers_have_distinct_ids(self) -> None:
        from scripts.export_fordongdorrong_backend import knowledge_documents
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW + "\n## 부칙 <2026-1>\n##### 제1조 (시행)\nA\n## 부칙 <2026-2>\n##### 제1조 (시행)\nB\n", encoding="utf-8")
            docs = list(knowledge_documents(source.parent, root, "2026-10-15T00:00:00Z", None))
            supplements = [doc for doc in docs if doc["metadata"]["section"] == "부칙"]
            self.assertEqual(2, len(supplements))
            self.assertNotEqual(supplements[0]["document_id"], supplements[1]["document_id"])

    def test_future_date_is_not_law_validity_and_source_conflict_rejected(self) -> None:
        from scripts.export_fordongdorrong_backend import knowledge_documents
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW.replace("2026-03-04", "2027-03-04"), encoding="utf-8")
            doc = next(iter(knowledge_documents(source.parent, root, "2026-10-15T00:00:00Z", None)))
            self.assertEqual("future_enforcement_date", doc["metadata"]["temporal_relation"])
            self.assertEqual("not_determined", doc["metadata"]["legal_effect_status"])
            (source / "시행령.md").write_text(SAMPLE_LAW.replace("법령구분: 법률", "법령구분: 법률"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                export_backend(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                               sqlite_path=root / "out.db", manifest_path=root / "manifest.json")

    def test_missing_source_and_symlink_output_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                export_backend(root=root, source_dir=root / "missing", jsonl_path=root / "out.jsonl",
                               sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            outside = root.parent / (root.name + "-outside")
            (root / "out.jsonl").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symlink"):
                export_backend(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                               sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            self.assertFalse(outside.exists())

    def test_empty_source_preserves_existing_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr"
            source.mkdir()
            jsonl = root / "out.jsonl"
            jsonl.write_text("previous", encoding="utf-8")
            with self.assertRaises(ValueError):
                export_backend(root=root, source_dir=source, jsonl_path=jsonl,
                               sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            self.assertEqual("previous", jsonl.read_text(encoding="utf-8"))

    def test_invalid_date_and_observation_are_distinct(self) -> None:
        from scripts.export_fordongdorrong_backend import knowledge_documents
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW.replace("2026-03-04", "2026-99-99"), encoding="utf-8")
            doc = next(iter(knowledge_documents(source.parent, root, "2026-10-15T00:00:00Z", None)))
            self.assertIsNone(doc["metadata"]["enforcement_date"])
            self.assertEqual("2026-10-15T00:00:00Z", doc["updated_at"])
            self.assertEqual("unverified", doc["metadata"]["verification_status"])
            paths = (root / "out.jsonl", root / "out.db", root / "manifest.json")
            export_backend(root=root, source_dir=source.parent, jsonl_path=paths[0],
                           sqlite_path=paths[1], manifest_path=paths[2])
            self.assertTrue(verify_published(*paths))

    def test_frontmatter_and_article_split(self) -> None:
        metadata, body = split_frontmatter(SAMPLE_LAW)
        articles = split_articles(body)

        self.assertEqual("테스트법", metadata["제목"])
        self.assertEqual(["테스트부"], metadata["소관부처"])
        self.assertEqual(3, len(articles))  # preamble is retained separately
        self.assertEqual("제1조", articles[0].article_no)
        self.assertEqual("목적", articles[0].article_title)

    def test_crlf_malformed_frontmatter_and_annex_preservation(self) -> None:
        metadata, body = split_frontmatter(SAMPLE_LAW.replace("\n", "\r\n"))
        self.assertEqual("테스트법", metadata["제목"])
        self.assertIn("제1조", body)
        with self.assertRaisesRegex(ValueError, "Malformed"):
            split_frontmatter("---\n제목: 미완료\n##### 제1조 본문")
        articles = split_articles("##### 제1조 (목적)\n본문\n## 별표 <별표1>\n표 내용")
        self.assertEqual("##### 제1조 (목적)\n본문", articles[0].body)
        self.assertTrue(any("표 내용" in article.body for article in articles))

    def test_dry_run_id_mapping_preserves_original_ordinal(self) -> None:
        from scripts.export_fordongdorrong_backend import migration_report
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "upstreams/legalize-kr/kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            report = migration_report(source.parent, root)
            self.assertTrue(report["dry_run"])
            self.assertIn("#제1조-0001", report["mappings"][0]["old_id"])
            self.assertIn("id/009999", report["mappings"][0]["new_id"])

    def test_export_writes_jsonl_sqlite_manifest_without_law_oc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "upstreams" / "legalize-kr" / "kr"
            law_dir = source_dir / "테스트법"
            law_dir.mkdir(parents=True)
            (law_dir / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            (root / "upstreams" / "korean-law-mcp" / "build").mkdir(parents=True)
            (root / "upstreams" / "korean-law-mcp" / "build" / "index.js").write_text("", encoding="utf-8")
            (root / "upstreams" / "korean-law-mcp" / "build" / "cli.js").write_text("", encoding="utf-8")

            old_law_oc = os.environ.pop("LAW_OC", None)
            try:
                result = export_backend(
                    root=root,
                    source_dir=source_dir,
                    jsonl_path=root / "exports" / "knowledge" / "korean-law.jsonl",
                    sqlite_path=root / "exports" / "sqlite" / "korean-law.db",
                    manifest_path=root / "exports" / "integration" / "manifest.json",
                )
            finally:
                if old_law_oc is not None:
                    os.environ["LAW_OC"] = old_law_oc

            self.assertTrue(result["ok"])
            self.assertFalse(result["law_oc_configured"])
            self.assertEqual(3, result["documents"])

            lines = (root / "exports" / "knowledge" / "korean-law.jsonl").read_text(encoding="utf-8").splitlines()
            docs = [json.loads(line) for line in lines]
            self.assertEqual("korean-law-mcp-lab", docs[0]["source_id"])
            self.assertEqual("unverified", docs[0]["metadata"]["verification_status"])
            self.assertFalse(docs[0]["metadata"]["legal_advice"])
            self.assertIn("테스트법", docs[0]["body"])

            with sqlite3.connect(root / "exports" / "sqlite" / "korean-law.db") as conn:
                count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                row = conn.execute("SELECT title, metadata_json FROM documents ORDER BY document_id LIMIT 1").fetchone()
            self.assertEqual(3, count)
            self.assertIn("테스트법", row[0])
            self.assertIn("unverified", row[1])

            manifest = json.loads((root / "exports" / "integration" / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["local_export"]["requires_api_key"])
            self.assertTrue(manifest["live_mcp"]["requires_api_key"])
            self.assertFalse(manifest["live_mcp"]["api_key_configured"])
            self.assertEqual("Use local_export JSONL/SQLite for retrieval and display LAW_OC-required live MCP features as unavailable.", manifest["fallback_policy"]["if_law_oc_missing"])

    def test_manifest_detects_law_oc_without_persisting_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "upstreams" / "legalize-kr" / "kr"
            law_dir = source_dir / "테스트법"
            law_dir.mkdir(parents=True)
            (law_dir / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")

            old_law_oc = os.environ.get("LAW_OC")
            os.environ["LAW_OC"] = "dummy-law-oc-value"
            try:
                export_backend(
                    root=root,
                    source_dir=source_dir,
                    jsonl_path=root / "out.jsonl",
                    sqlite_path=root / "out.db",
                    manifest_path=root / "manifest.json",
                )
            finally:
                if old_law_oc is None:
                    os.environ.pop("LAW_OC", None)
                else:
                    os.environ["LAW_OC"] = old_law_oc

            manifest_text = (root / "manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertTrue(manifest["live_mcp"]["api_key_configured"])
            self.assertNotIn("dummy-law-oc-value", manifest_text)


if __name__ == "__main__":
    unittest.main()
