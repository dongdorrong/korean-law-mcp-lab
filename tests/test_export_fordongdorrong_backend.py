from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.export_fordongdorrong_backend import export_backend, split_articles, split_frontmatter


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
    def test_frontmatter_and_article_split(self) -> None:
        metadata, body = split_frontmatter(SAMPLE_LAW)
        articles = split_articles(body)

        self.assertEqual("테스트법", metadata["제목"])
        self.assertEqual(["테스트부"], metadata["소관부처"])
        self.assertEqual(2, len(articles))
        self.assertEqual("제1조", articles[0].article_no)
        self.assertEqual("목적", articles[0].article_title)

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
            self.assertEqual(2, result["documents"])

            lines = (root / "exports" / "knowledge" / "korean-law.jsonl").read_text(encoding="utf-8").splitlines()
            docs = [json.loads(line) for line in lines]
            self.assertEqual("korean-law-mcp-lab", docs[0]["source_id"])
            self.assertEqual("local_official_text_snapshot", docs[0]["metadata"]["verification_status"])
            self.assertFalse(docs[0]["metadata"]["legal_advice"])
            self.assertIn("테스트법", docs[0]["body"])

            with sqlite3.connect(root / "exports" / "sqlite" / "korean-law.db") as conn:
                count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                row = conn.execute("SELECT title, metadata_json FROM documents ORDER BY document_id LIMIT 1").fetchone()
            self.assertEqual(2, count)
            self.assertIn("테스트법", row[0])
            self.assertIn("local_official_text_snapshot", row[1])

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
