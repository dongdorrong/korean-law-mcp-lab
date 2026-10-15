from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
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
    def test_journal_publish_does_not_replace_raced_owner(self) -> None:
        from scripts import export_fordongdorrong_backend as exporter
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / ".law-first-publish.journal.json"
            other = b'{"owner":"other publisher"}'
            original_link = os.link
            def race(src, dst, **kwargs):
                journal.write_bytes(other)
                return original_link(src, dst, **kwargs)
            with patch.object(exporter.os, "link", side_effect=race):
                with self.assertRaises(FileExistsError):
                    exporter.safe_create_json(journal, {"owner": "this publisher"}, root)
            self.assertEqual(other, journal.read_bytes())

    def test_concurrent_journal_publish_has_one_owner(self) -> None:
        from scripts import export_fordongdorrong_backend as exporter
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / ".law-first-publish.journal.json"
            gate = Barrier(2)
            original_link = os.link
            def at_publication(src, dst, **kwargs):
                gate.wait(timeout=5)
                return original_link(src, dst, **kwargs)
            def publish(owner):
                try:
                    exporter.safe_create_json(journal, {"owner": owner}, root)
                    return "published"
                except FileExistsError:
                    return "existing"
            with patch.object(exporter.os, "link", side_effect=at_publication):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(publish, ("a", "b")))
            self.assertCountEqual(["published", "existing"], results)
            self.assertIn(json.loads(journal.read_text())["owner"], ("a", "b"))

    def test_crash_during_journal_write_leaves_no_final_journal(self) -> None:
        from scripts import export_fordongdorrong_backend as exporter
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = """import os, pathlib
from scripts import export_fordongdorrong_backend as e
def die(value, handle, *args, **kwargs):
    handle.write('{'); handle.flush(); os.fsync(handle.fileno()); os._exit(17)
e.json.dump = die
e.safe_create_json(pathlib.Path(os.environ['JOURNAL']), {'schema': 1}, pathlib.Path(os.environ['ROOT']))
"""
            journal = root / ".law-first-publish.journal.json"
            result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                                    env={**os.environ, "ROOT": str(root), "JOURNAL": str(journal)})
            self.assertEqual(17, result.returncode)
            self.assertFalse(journal.exists())
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            exporter.export_backend(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                                    sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            self.assertTrue(verify_published(root / "out.jsonl", root / "out.db", root / "manifest.json"))

    def test_malformed_zero_output_journal_can_be_quarantined(self) -> None:
        from scripts import export_fordongdorrong_backend as exporter
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / ".law-first-publish.journal.json"
            journal.write_text("{", encoding="utf-8")
            args = (root, root, root / "out.jsonl", root / "out.db", root / "manifest.json")
            self.assertTrue(exporter.recover_first_publish(*args)["recoverable"])
            self.assertTrue(exporter.recover_first_publish(*args, apply=True)["recoverable"])
            self.assertFalse(journal.exists())
            self.assertEqual("{", next(root.glob(".law-recovery-*.journal.json")).read_text())

    def test_recovery_preserves_swapped_unknown_file(self) -> None:
        from scripts import export_fordongdorrong_backend as exporter
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            args = dict(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                        sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            original = os.replace
            count = 0
            def interrupt(src, dst, **kwargs):
                nonlocal count
                count += 1
                if count == 3:
                    raise OSError("partial")
                return original(src, dst, **kwargs)
            with patch.object(exporter.os, "replace", side_effect=interrupt):
                with self.assertRaises(OSError):
                    exporter.export_backend(**args)
            self.assertTrue((root / "out.jsonl").exists())
            original_safe_replace = exporter.safe_replace
            def swap_before_move(src, dst, anchor):
                if src == root / "out.jsonl":
                    src.write_text("unknown-new-content", encoding="utf-8")
                return original_safe_replace(src, dst, anchor)
            with patch.object(exporter, "safe_replace", side_effect=swap_before_move):
                report = exporter.recover_first_publish(*args.values(), apply=True)
            self.assertFalse(report["recoverable"])
            self.assertEqual("unknown-new-content", (root / "out.jsonl").read_text())
            self.assertTrue((root / ".law-first-publish.journal.json").exists())

    def test_verify_missing_sqlite_does_not_create_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.db"
            self.assertFalse(verify_published(root / "out.jsonl", missing, root / "manifest.json"))
            self.assertFalse(missing.exists())

    def test_first_publish_interruption_has_dry_run_recovery(self) -> None:
        from scripts import export_fordongdorrong_backend as exporter
        for fail_at in (1, 2, 3):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "kr/테스트법"
                source.mkdir(parents=True)
                (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
                args = dict(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                            sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
                original = os.replace
                calls = 0
                def interrupt(src, dst, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == fail_at:
                        raise OSError("injected first publish interruption")
                    return original(src, dst, **kwargs)
                with patch.object(exporter.os, "replace", side_effect=interrupt):
                    with self.assertRaises(OSError):
                        exporter.export_backend(**args)
                report = exporter.recover_first_publish(*args.values(), apply=False)
                self.assertTrue(report["recoverable"])
                exporter.recover_first_publish(*args.values(), apply=True)
                self.assertFalse((root / "out.jsonl").exists())
                exporter.export_backend(**args)
                self.assertTrue(verify_published(root / "out.jsonl", root / "out.db", root / "manifest.json"))

    def test_corrupt_existing_baseline_is_rejected_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            path = source / "법률.md"
            path.write_text(SAMPLE_LAW, encoding="utf-8")
            args = dict(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                        sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            export_backend(**args)
            legacy_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            legacy_manifest.pop("generation")
            (root / "manifest.json").write_text(json.dumps(legacy_manifest), encoding="utf-8")
            (root / "out.db").write_bytes(b"corrupt")
            path.write_text(SAMPLE_LAW + "changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                export_backend(**args)
            self.assertEqual(b"corrupt", (root / "out.db").read_bytes())

    def test_valid_legacy_baseline_without_checksum_is_parity_checked(self) -> None:
        from scripts.export_fordongdorrong_backend import verify_fixed_baseline
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            paths = (root / "out.jsonl", root / "out.db", root / "manifest.json")
            args = dict(root=root, source_dir=source.parent, jsonl_path=paths[0],
                        sqlite_path=paths[1], manifest_path=paths[2])
            export_backend(**args)
            legacy = json.loads(paths[2].read_text(encoding="utf-8"))
            legacy.pop("generation")
            paths[2].write_text(json.dumps(legacy), encoding="utf-8")
            self.assertTrue(verify_fixed_baseline(*paths))
            result = export_backend(**args)
            self.assertNotEqual(paths[2], Path(result["manifest"]))

    def test_first_limit_export_does_not_freeze_partial_fixed_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            args = dict(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                        sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            result = export_backend(**args, limit=1)
            self.assertFalse((root / "out.jsonl").exists())
            self.assertTrue(verify_published(Path(result["jsonl"]), Path(result["sqlite"]), Path(result["manifest"])))
            export_backend(**args)
            self.assertTrue((root / "out.jsonl").exists())

    def test_manifest_configuration_changes_generation_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            args = dict(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                        sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            with patch("scripts.export_fordongdorrong_backend.utc_now", return_value="2026-10-15T00:00:00Z"):
                with patch.dict(os.environ, {"LAW_OC": ""}):
                    export_backend(**args)
                with patch.dict(os.environ, {"LAW_OC": "synthetic"}):
                    result = export_backend(**args)
            initial = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["generation"]["id"]
            updated = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))["generation"]["id"]
            self.assertNotEqual(initial, updated)

    def test_cli_rejects_symlink_before_resolve(self) -> None:
        from scripts.export_fordongdorrong_backend import main
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            outside = root / "existing.txt"
            outside.write_text("do not replace", encoding="utf-8")
            link = root / "out.jsonl"
            link.symlink_to(outside)
            argv = ["export", "--root", str(root), "--source-dir", str(source.parent),
                    "--jsonl", str(link), "--sqlite", str(root / "out.db"),
                    "--manifest", str(root / "manifest.json")]
            with patch.object(sys, "argv", argv):
                with self.assertRaises(ValueError):
                    main()
            self.assertEqual("do not replace", outside.read_text(encoding="utf-8"))

    def test_output_alias_is_rejected_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            alias = root / "out"
            with self.assertRaisesRegex(ValueError, "distinct"):
                export_backend(root=root, source_dir=source.parent, jsonl_path=alias,
                               sqlite_path=root / "out.db", manifest_path=alias)
            self.assertFalse(alias.exists())

    def test_parent_directory_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            (root / "actual").mkdir()
            (root / "alias").symlink_to(root / "actual", target_is_directory=True)
            with self.assertRaises(ValueError):
                export_backend(root=root, source_dir=source.parent, jsonl_path=root / "alias/out.jsonl",
                               sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            self.assertEqual([], list((root / "actual").iterdir()))

    def test_parent_symlink_swap_during_replace_cannot_write_outside_root(self) -> None:
        from scripts import export_fordongdorrong_backend as exporter
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root, outside = Path(tmp), Path(outside_tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            alias = root / "target"
            alias.mkdir()
            original = os.replace
            swapped = False
            def swap_then_replace(src, dst, **kwargs):
                nonlocal swapped
                if not swapped:
                    alias.rename(root / "moved_target")
                    alias.symlink_to(outside, target_is_directory=True)
                    swapped = True
                return original(src, dst, **kwargs)
            with patch.object(exporter.os, "replace", side_effect=swap_then_replace):
                with self.assertRaises((ValueError, OSError)):
                    exporter.export_backend(root=root, source_dir=source.parent,
                                            jsonl_path=alias / "out.jsonl", sqlite_path=root / "out.db",
                                            manifest_path=root / "manifest.json")
            self.assertEqual([], list(outside.iterdir()))

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
            def fail_pointer(src, dst, **kwargs):
                if str(dst).endswith(".current.json"):
                    raise OSError("injected publish interruption")
                return original_replace(src, dst, **kwargs)
            with patch.object(exporter.os, "replace", side_effect=fail_pointer):
                with self.assertRaisesRegex(OSError, "interruption"):
                    exporter.export_backend(**args)
            self.assertTrue(verify_published(*paths))

    def test_generation_pointer_reader_sees_one_coherent_version(self) -> None:
        from scripts.export_fordongdorrong_backend import read_current_generation
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            path = source / "법률.md"
            args = dict(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                        sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            for suffix in ("A", "B"):
                path.write_text(SAMPLE_LAW + suffix, encoding="utf-8")
                export_backend(**args)
            pointer = root / "manifest.current.json"
            before = read_current_generation(root, pointer)
            path.write_text(SAMPLE_LAW + "C", encoding="utf-8")
            export_backend(**args)
            after = read_current_generation(root, pointer)
            self.assertNotEqual(before[1]["content_hash"], after[1]["content_hash"])
            self.assertTrue(verify_published(root / "out.jsonl", root / "out.db", root / "manifest.json"))

    def test_concurrent_pointer_reader_never_observes_mixed_generation(self) -> None:
        import threading
        from scripts.export_fordongdorrong_backend import read_current_generation
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            path = source / "법률.md"
            args = dict(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                        sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            path.write_text(SAMPLE_LAW + "A", encoding="utf-8")
            export_backend(**args)
            path.write_text(SAMPLE_LAW + "B", encoding="utf-8")
            export_backend(**args)
            pointer = root / "manifest.current.json"
            errors = []
            started = threading.Event()
            def reader():
                started.set()
                for _ in range(100):
                    try:
                        docs = read_current_generation(root, pointer)
                        if len(docs) != 3:
                            errors.append("unexpected document count")
                    except Exception as exc:
                        errors.append(str(exc))
            thread = threading.Thread(target=reader)
            thread.start()
            started.wait()
            for suffix in ("C", "D", "E"):
                path.write_text(SAMPLE_LAW + suffix, encoding="utf-8")
                export_backend(**args)
            thread.join()
            self.assertEqual([], errors)

    def test_limit_is_partial_and_duplicate_source_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            paths = (root / "out.jsonl", root / "out.db", root / "manifest.json")
            result = export_backend(root=root, source_dir=source.parent, jsonl_path=paths[0],
                                    sqlite_path=paths[1], manifest_path=paths[2], limit=1)
            published = tuple(Path(result[key]) for key in ("jsonl", "sqlite", "manifest"))
            manifest = json.loads(published[2].read_text(encoding="utf-8"))
            self.assertFalse(manifest["generation"]["complete_snapshot"])
            self.assertEqual("partial_unverified_source", manifest["local_export"]["status"])
            (source / "법률.md").write_text(SAMPLE_LAW.replace("##### 제2조", "##### 제1조"), encoding="utf-8")
            with self.assertRaises(ValueError):
                export_backend(root=root, source_dir=source.parent, jsonl_path=paths[0],
                               sqlite_path=paths[1], manifest_path=paths[2])
            self.assertTrue(verify_published(*published))

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
            supplements = [doc for doc in docs if doc["metadata"]["section"] == "부칙" and doc["metadata"]["article_no"] == "제1조"]
            self.assertEqual(2, len(supplements))
            self.assertNotEqual(supplements[0]["document_id"], supplements[1]["document_id"])

    def test_two_nonarticle_annexes_remain_distinct(self) -> None:
        from scripts.export_fordongdorrong_backend import knowledge_documents
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW + "\n## 별표 <1>\n첫째 표\n## 별표 <2>\n둘째 표\n", encoding="utf-8")
            docs = list(knowledge_documents(source.parent, root, "2026-10-15T00:00:00Z", None))
            annexes = [doc for doc in docs if doc["metadata"]["section"] == "별표"]
            self.assertEqual(2, len(annexes))
            self.assertNotEqual(annexes[0]["document_id"], annexes[1]["document_id"])
            self.assertIn("첫째 표", annexes[0]["body"])
            self.assertIn("둘째 표", annexes[1]["body"])

    def test_unlabeled_supplements_stable_under_reorder_but_weak(self) -> None:
        from scripts.export_fordongdorrong_backend import knowledge_documents
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            a, b = "## 부칙\n##### 제1조 (A)\nA text\n", "## 부칙\n##### 제1조 (B)\nB text\n"
            path = source / "법률.md"
            path.write_text(a + b, encoding="utf-8")
            first = {d["metadata"]["article_title"]: d for d in knowledge_documents(source.parent, root, "2026-01-01T00:00:00Z", None) if d["metadata"]["article_no"] == "제1조"}
            path.write_text(b + a, encoding="utf-8")
            second = {d["metadata"]["article_title"]: d for d in knowledge_documents(source.parent, root, "2026-01-01T00:00:00Z", None) if d["metadata"]["article_no"] == "제1조"}
            for key in ("A", "B"):
                self.assertEqual(first[key]["document_id"], second[key]["document_id"])
                self.assertEqual("section_content_weak", second[key]["metadata"]["identity_strength"])

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

    def test_freshness_states_are_explicit_policy_not_legal_effect(self) -> None:
        from scripts.export_fordongdorrong_backend import classify_freshness, knowledge_documents
        observed = "2026-10-15T00:00:00Z"
        modified = "2020-01-01T00:00:00+09:00"
        self.assertEqual("observed_unverified", classify_freshness(observed, modified))
        self.assertEqual("stale_by_explicit_policy", classify_freshness(observed, modified, stale_after_days=365))
        self.assertEqual("conflicting_source", classify_freshness(observed, modified, conflicting=True))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW.replace("상태: 시행", "상태: 폐지\n원본변경일: 2026-02-01"), encoding="utf-8")
            doc = next(iter(knowledge_documents(source.parent, root, observed, None)))
            self.assertEqual("2026-02-01T00:00:00+09:00", doc["metadata"]["source_modified_at"])
            self.assertEqual("not_determined", doc["metadata"]["legal_effect_status"])
            self.assertEqual("active", doc["lifecycle"])  # data lifecycle, not legal effect

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
            with self.assertRaises(ValueError):
                export_backend(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                               sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            self.assertFalse(outside.exists())

    def test_parent_git_repo_is_not_misidentified_as_legalize_source(self) -> None:
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "synthetic"], check=True)
            source = root / "kr/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            result = export_backend(root=root, source_dir=source.parent, jsonl_path=root / "out.jsonl",
                                    sqlite_path=root / "out.db", manifest_path=root / "manifest.json")
            self.assertIsNone(result["legalize_commit"])
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("unverified_source", manifest["local_export"]["status"])
            self.assertIsNone(manifest["local_export"]["source_commit"])

    def test_custom_source_cannot_borrow_verified_upstream_commit(self) -> None:
        from scripts import export_fordongdorrong_backend as exporter
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "custom/테스트법"
            source.mkdir(parents=True)
            (source / "법률.md").write_text(SAMPLE_LAW, encoding="utf-8")
            with patch.object(exporter, "verified_upstream_commit", return_value=("a" * 40, "pinned")):
                result = exporter.export_backend(root=root, source_dir=source.parent,
                                                 jsonl_path=root / "out.jsonl", sqlite_path=root / "out.db",
                                                 manifest_path=root / "manifest.json")
            self.assertIsNone(result["legalize_commit"])

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
        with self.assertRaisesRegex(ValueError, "frontmatter line 2"):
            split_frontmatter("---\n제목: 법\n잘못된 행\n---\n본문")
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
            previous = root / "previous.jsonl"
            previous.write_text(json.dumps({"document_id": "legalize-kr/kr/테스트법/법률.md#제2조-0002",
                                           "metadata": {"article_no": "제2조", "source_path": "upstreams/legalize-kr/kr/테스트법/법률.md"}}) + "\n", encoding="utf-8")
            (source / "법률.md").write_text(SAMPLE_LAW.replace("##### 제2조", "##### 제1조의2 (삽입)\n삽입.\n##### 제2조"), encoding="utf-8")
            report = migration_report(source.parent, root, previous)
            self.assertTrue(report["dry_run"])
            self.assertEqual("legalize-kr/kr/테스트법/법률.md#제2조-0002", report["mappings"][0]["old_id"])
            self.assertIn("id/009999", report["mappings"][0]["new_id"])
            previous.write_text(previous.read_text(encoding="utf-8") + json.dumps({
                "document_id": "legalize-kr/kr/테스트법/법률.md#제9조-0009",
                "metadata": {"article_no": "제9조", "source_path": "upstreams/legalize-kr/kr/테스트법/법률.md"}}) + "\n", encoding="utf-8")
            report = migration_report(source.parent, root, previous)
            self.assertEqual(1, len(report["unresolved"]))
            self.assertFalse(report["safe_to_apply_automatically"])

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
            self.assertIsInstance(manifest["sqlite_schema"]["fts_available"], bool)
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
