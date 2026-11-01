#!/usr/bin/env python3
"""Export Korean-law lab data as fordongdorrong-ready backend artifacts.

The exporter is deliberately local-first:

* Without LAW_OC it exports checked-out legalize-kr Markdown into Knowledge
  JSONL + SQLite so a RAG/SQLite importer can work offline.
* With LAW_OC it still exports the same local artifacts and only records that
  a key is configured; authentication and live retrieval remain untested.

It never calls the live law API, stores no API key, and does not provide legal
advice. Live API/MCP calls remain an optional runtime integration for the
downstream application.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import shutil
import uuid
from urllib.parse import quote
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable

SOURCE_ID = "korean-law-mcp-lab"
DEFAULT_VISIBILITY = "private"
ARTICLE_HEADING_RE = re.compile(r"^#{3,6}\s+(제\d+조(?:의\d+)?)(?:\s*\(([^)]+)\))?\s*$")
SECTION_RE = re.compile(r"^#{1,3}\s*(부칙|별표)(?:\s*[<[(]([^>)\]]+)[>)\]])?.*$")
SECRET_KEY_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|law_oc|credential)")


@dataclass(frozen=True)
class LawSource:
    path: Path
    relative_path: str
    metadata: dict[str, Any]
    body: str


@dataclass(frozen=True)
class Article:
    article_no: str
    article_title: str
    heading: str
    body: str
    ordinal: int
    section: str = "본문"
    section_key: str = "본문"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="export_fordongdorrong_backend")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root; default: cwd")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="legalize-kr law directory; default: <root>/upstreams/legalize-kr/kr",
    )
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=None,
        help="Knowledge JSONL output; default: <root>/exports/knowledge/korean-law.jsonl",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help="SQLite output; default: <root>/exports/sqlite/korean-law.db",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Integration manifest output; default: <root>/exports/integration/korean-law-backend.manifest.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max document count for smoke tests; 0 means no limit",
    )
    parser.add_argument("--print-summary", action="store_true", help="Print compact JSON summary")
    parser.add_argument("--allow-empty", action="store_true", help="Explicitly publish an empty export")
    parser.add_argument("--migration-report", type=Path, help="Write old ordinal IDs to new logical IDs; dry-run only")
    parser.add_argument("--previous-jsonl", type=Path, help="Required with --migration-report; prior snapshot JSONL")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    source_dir = (args.source_dir or root / "upstreams" / "legalize-kr" / "kr").resolve()
    jsonl_path = args.jsonl or root / "exports" / "knowledge" / "korean-law.jsonl"
    sqlite_path = args.sqlite or root / "exports" / "sqlite" / "korean-law.db"
    manifest_path = (
        args.manifest or root / "exports" / "integration" / "korean-law-backend.manifest.json"
    )

    result = export_backend(
        root=root,
        source_dir=source_dir,
        jsonl_path=jsonl_path,
        sqlite_path=sqlite_path,
        manifest_path=manifest_path,
        limit=args.limit,
        allow_empty=args.allow_empty,
    )
    if args.migration_report:
        if args.previous_jsonl is None:
            raise ValueError("--migration-report requires --previous-jsonl")
        report = migration_report(source_dir, root, args.previous_jsonl)
        write_json(args.migration_report, report)
    if args.print_summary:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def export_backend(
    *,
    root: Path,
    source_dir: Path,
    jsonl_path: Path,
    sqlite_path: Path,
    manifest_path: Path,
    limit: int = 0,
    allow_empty: bool = False,
) -> dict[str, Any]:
    if limit < 0:
        raise ValueError("--limit must be non-negative")
    if not source_dir.is_dir():
        raise FileNotFoundError(
            f"legalize-kr source directory is missing: {source_dir}. Run scripts/bootstrap-upstreams.sh first."
        )
    if not source_dir.resolve().is_relative_to(root.resolve()):
        raise ValueError("Source directory must be inside root")

    generated_at = utc_now()
    legalize_commit, source_diagnostic = verified_upstream_commit(root, "legalize-kr")
    if source_dir.resolve() != (root / "upstreams" / "legalize-kr" / "kr").resolve():
        legalize_commit, source_diagnostic = None, "source directory is not the pinned legalize-kr kr tree"
    mcp_dir = root / "upstreams" / "korean-law-mcp"
    mcp_commit, _ = verified_upstream_commit(root, "korean-law-mcp")
    law_oc_configured = bool(os.environ.get("LAW_OC"))

    documents = list(knowledge_documents(source_dir, root, generated_at, legalize_commit))
    if not documents and not allow_empty:
        raise ValueError("No documents parsed; existing export was not replaced. Use --allow-empty deliberately.")
    if limit > 0:
        documents = documents[:limit]

    ids = [doc["document_id"] for doc in documents]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate document identity; existing export was not replaced")

    assert_no_secret_like_payload(documents)
    paths = (jsonl_path, sqlite_path, manifest_path)
    journal = manifest_path.parent / ".law-first-publish.journal.json"
    reject_output_path(journal, root)
    if journal.exists():
        raise ValueError("Incomplete first publish journal exists; run recover_first_publish dry-run")
    if any(path.exists() for path in paths) and not all(path.exists() for path in paths):
        raise ValueError("Incomplete fixed-path legacy set; existing files were not changed")
    existing_fixed = all(path.exists() for path in paths)
    if existing_fixed and not verify_fixed_baseline(*paths):
        raise ValueError("Existing fixed-path baseline failed consistency validation")
    if len({path.absolute() for path in paths}) != 3 or len({path.resolve() for path in paths}) != 3:
        raise ValueError("JSONL, SQLite and manifest output paths must be distinct")
    for index, path in enumerate(paths):
        if path.exists() and any(other.exists() and os.path.samefile(path, other) for other in paths[:index]):
            raise ValueError("JSONL, SQLite and manifest output paths must be distinct")
    for path in paths:
        reject_output_path(path, root)
        path.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".law-export-", dir=manifest_path.parent))
    staged_jsonl, staged_sqlite, staged_manifest = (stage / name for name in ("out.jsonl", "out.db", "manifest.json"))
    try:
        write_jsonl(staged_jsonl, documents)
        write_sqlite(staged_sqlite, documents)
        manifest = build_manifest(
        root=root,
        source_dir=source_dir,
        jsonl_path=jsonl_path,
        sqlite_path=sqlite_path,
        documents=documents,
        generated_at=generated_at,
        legalize_commit=legalize_commit,
        mcp_dir=mcp_dir,
        mcp_commit=mcp_commit,
        law_oc_configured=law_oc_configured,
        )
        manifest["generation"] = {
            "jsonl_sha256": hashlib.sha256(staged_jsonl.read_bytes()).hexdigest(),
            "sqlite_sha256": hashlib.sha256(staged_sqlite.read_bytes()).hexdigest(),
            "complete_snapshot": limit == 0,
            "empty_explicit": not documents and allow_empty,
        }
        manifest["local_export"]["status"] = "ready" if limit == 0 else "partial_smoke_only"
        if legalize_commit is None:
            manifest["local_export"]["status"] = "unverified_source" if limit == 0 else "partial_unverified_source"
        manifest["local_export"]["source_diagnostic"] = source_diagnostic
        manifest["sqlite_schema"]["fts_available"] = sqlite_fts_available(staged_sqlite)
        manifest["generation"]["id"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        assert_no_secret_like_payload([manifest])
        write_json(staged_manifest, manifest)
        verify_staged(staged_jsonl, staged_sqlite, staged_manifest)
        for staged in (staged_jsonl, staged_sqlite, staged_manifest):
            sync_file(staged)
        sync_dir(stage)
        if existing_fixed or limit > 0 or not documents:
            # Legacy fixed paths are frozen as one complete generation. New writes
            # go to immutable files; only a single pointer is replaced.
            generation_dir = manifest_path.parent / ".law-generations" / manifest["generation"]["id"]
            reject_output_path(generation_dir, root)
            manifest["local_export"]["jsonl"] = relative(generation_dir / "out.jsonl", root)
            manifest["local_export"]["sqlite"] = relative(generation_dir / "out.db", root)
            write_json(staged_manifest, manifest)
            sync_file(staged_manifest)
            sync_dir(stage)
            if generation_dir.exists():
                verify_staged(generation_dir / "out.jsonl", generation_dir / "out.db", generation_dir / "manifest.json")
                if staged_manifest.read_bytes() != (generation_dir / "manifest.json").read_bytes():
                    raise ValueError("Generation identity collision with different manifest")
            else:
                generation_dir.parent.mkdir(parents=True, exist_ok=True)
                safe_replace(stage, generation_dir, root)
                sync_dir(generation_dir.parent)
            if existing_fixed:
                pointer = manifest_path.with_suffix(".current.json")
                reject_output_path(pointer, root)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=pointer.parent,
                                                 prefix=".law-pointer-", delete=False) as handle:
                    json.dump({"generation_manifest": relative(generation_dir / "manifest.json", root),
                               "generation_id": manifest["generation"]["id"]}, handle)
                    pointer_tmp = Path(handle.name)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    reject_output_path(pointer, root)
                    safe_replace(pointer_tmp, pointer, root)
                    sync_dir(pointer.parent)
                finally:
                    pointer_tmp.unlink(missing_ok=True)
            jsonl_path, sqlite_path, manifest_path = (generation_dir / name for name in ("out.jsonl", "out.db", "manifest.json"))
        else:
            # First creation cannot replace a previously complete fixed-path set.
            for path in paths:
                reject_output_path(path, root)
            safe_create_json(journal, {"schema": 1, "paths": [relative(path, root) for path in paths],
                                       "sha256": [hashlib.sha256(path.read_bytes()).hexdigest() for path in
                                                  (staged_jsonl, staged_sqlite, staged_manifest)]}, root)
            sync_dir(journal.parent)
            safe_replace(staged_jsonl, jsonl_path, root)
            safe_replace(staged_sqlite, sqlite_path, root)
            safe_replace(staged_manifest, manifest_path, root)
            for parent in {path.parent for path in paths}:
                sync_dir(parent)
            safe_unlink(journal, root)
            sync_dir(journal.parent)
        if not verify_published(jsonl_path, sqlite_path, manifest_path):
            raise ValueError("Published generation failed validation")
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    return {
        "ok": True,
        "backend_id": SOURCE_ID,
        "documents": len(documents),
        "jsonl": str(jsonl_path),
        "sqlite": str(sqlite_path),
        "manifest": str(manifest_path),
        "law_oc_configured": law_oc_configured,
        "legalize_commit": legalize_commit,
        "korean_law_mcp_commit": mcp_commit,
    }


def knowledge_documents(source_dir: Path, root: Path, generated_at: str, commit: str | None) -> Iterable[dict[str, Any]]:
    for law in iter_law_sources(source_dir, root):
        articles = split_articles(law.body)
        if not articles:
            articles = [Article("문서", "전체", str(law.metadata.get("제목") or law.path.stem), law.body, 1)]
        for article in articles:
            yield knowledge_document(law, article, generated_at, commit)


def iter_law_sources(source_dir: Path, root: Path) -> Iterable[LawSource]:
    for path in sorted(source_dir.glob("*/*.md")):
        if path.is_symlink() or not path.resolve().is_relative_to(source_dir.resolve()):
            raise ValueError("Source symlink/path escapes source directory")
        text = path.read_text(encoding="utf-8")
        try:
            metadata, body = split_frontmatter(text)
        except ValueError as exc:
            raise ValueError(f"Malformed source {relative(path, root)}: {exc}") from exc
        if not body.strip():
            raise ValueError("Empty law document")
        relative_path = relative(path, root)
        yield LawSource(path=path, relative_path=relative_path, metadata=metadata, body=body)


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("Malformed frontmatter")
    raw_meta = text[4:end]
    body = text[end + len("\n---\n") :]
    return parse_simple_yaml(raw_meta), body


def parse_simple_yaml(raw: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    current_key: str | None = None
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        if line.startswith("- ") and current_key:
            metadata.setdefault(current_key, [])
            if isinstance(metadata[current_key], list):
                metadata[current_key].append(clean_scalar(line[2:].strip()))
            else:
                raise ValueError(f"frontmatter line {number}: list under scalar")
            continue
        if line.startswith("  ") and current_key:
            raise ValueError(f"frontmatter line {number}: nested YAML unsupported")
        if ":" not in line:
            raise ValueError(f"frontmatter line {number}: expected key: value")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key or key in metadata:
            raise ValueError(f"frontmatter line {number}: empty or duplicate key")
        value = raw_value.strip()
        current_key = key
        if not value:
            metadata[key] = []
        else:
            metadata[key] = clean_scalar(value)
    return metadata


def clean_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def split_articles(body: str) -> list[Article]:
    lines = body.splitlines()
    starts: list[tuple[int, re.Match[str], str, str]] = []
    section_starts: list[int] = []
    section = section_key = "본문"
    section_at: list[tuple[str, str]] = []
    for index, line in enumerate(lines):
        section_match = SECTION_RE.match(line)
        if section_match:
            section_starts.append(index)
            section = section_match.group(1)
            label = section_match.group(2)
            if label:
                section_key = f"{section}-{label}"
            else:
                end = next((i for i in range(index + 1, len(lines)) if SECTION_RE.match(lines[i])), len(lines))
                fingerprint = hashlib.sha256("\n".join(lines[index:end]).strip().encode("utf-8")).hexdigest()[:16]
                section_key = f"{section}-unlabeled-weak-{fingerprint}"
        section_at.append((section, section_key))
        match = ARTICLE_HEADING_RE.match(line)
        if match:
            starts.append((index, match, section, section_key))

    articles: list[Article] = []
    for ordinal, (start, match, section, section_key) in enumerate(starts, start=1):
        end = starts[ordinal][0] if ordinal < len(starts) else len(lines)
        end = min([i for i in section_starts if start < i < end], default=end)
        chunk = "\n".join(lines[start:end]).strip()
        article_no = match.group(1)
        article_title = match.group(2) or ""
        articles.append(
            Article(
                article_no=article_no,
                article_title=article_title,
                heading=lines[start].strip(),
                body=chunk,
                ordinal=ordinal,
                section=section,
                section_key=section_key,
            )
        )
    # Keep frontmatter-adjacent preamble and non-article annex text as separate evidence.
    covered = set()
    for start, _, _, _ in starts:
        end = next((i for i in sorted([s for s, _, _, _ in starts] + section_starts) if i > start), len(lines))
        covered.update(range(start, end))
    extra_by_section: dict[str, list[str]] = {}
    extra_section_kind: dict[str, str] = {}
    for index, line in enumerate(lines):
        if index not in covered:
            kind, key = section_at[index]
            extra_by_section.setdefault(key, []).append(line)
            extra_section_kind[key] = kind
    for key, extra_lines in extra_by_section.items():
        extras = "\n".join(extra_lines).strip()
        if extras:
            articles.append(Article("문서", "비조문", "비조문 자료", extras, 0,
                                    extra_section_kind[key], f"{key}-비조문"))
    return articles


def knowledge_document(law: LawSource, article: Article, generated_at: str, commit: str | None) -> dict[str, Any]:
    law_title = str(law.metadata.get("제목") or law.path.parent.name)
    law_type = str(law.metadata.get("법령구분") or law.path.stem)
    law_id = str(law.metadata.get("법령ID") or "")
    law_mst = str(law.metadata.get("법령MST") or "")
    source_uri = str(law.metadata.get("출처") or law.relative_path)
    doc_id = stable_document_id(law.relative_path, article, law_id, law_type)
    title = " ".join(part for part in [law_title, law_type, article.article_no, article.article_title] if part)
    body = "\n".join(
        [
            f"법령명: {law_title}",
            f"법령구분: {law_type}",
            f"조문: {article.heading}",
            f"소관부처: {', '.join(as_list(law.metadata.get('소관부처'))) or 'unknown'}",
            f"공포일자: {law.metadata.get('공포일자') or 'unknown'}",
            f"시행일자: {law.metadata.get('시행일자') or 'unknown'}",
            f"출처: {source_uri}",
            "",
            "원문:",
            article.body,
        ]
    ).strip()
    content_hash = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
    promulgation = date_to_iso(str(law.metadata.get("공포일자") or ""))
    enforcement = date_to_iso(str(law.metadata.get("시행일자") or ""))
    source_modified = date_to_iso(str(law.metadata.get("원본변경일") or ""))
    if enforcement is None:
        temporal_relation = "unknown"
    elif enforcement[:10] > datetime.fromisoformat(generated_at.replace("Z", "+00:00")).astimezone(
            timezone(timedelta(hours=9))).date().isoformat():
        temporal_relation = "future_enforcement_date"
    else:
        temporal_relation = "date_not_future"

    return {
        "source_id": SOURCE_ID,
        "document_id": doc_id,
        "title": title,
        "body": body,
        "uri": source_uri,
        "content_hash": content_hash,
        "created_at": promulgation,
        "updated_at": generated_at,
        "visibility": DEFAULT_VISIBILITY,
        "lifecycle": "active",
        "deleted_at": None,
        "indexable": True,
        "metadata": {
            "kind": "law_article",
            "category": "korean_law",
            "source_kind": "legalize_kr_pinned_markdown" if commit else "unverified_local_markdown",
            "law_title": law_title,
            "law_type": law_type,
            "law_id": law_id,
            "law_mst": law_mst,
            "article_no": article.article_no,
            "article_title": article.article_title,
            "article_ordinal": article.ordinal,
            "section": article.section,
            "section_identity": article.section_key,
            "identity_strength": "section_content_weak" if "unlabeled-weak" in article.section_key else (
                "official_law_id" if law_id else "path_fallback_weak"),
            "revision": content_hash,
            "ministry": as_list(law.metadata.get("소관부처")),
            "promulgation_date": promulgation[:10] if promulgation else None,
            "enforcement_date": enforcement[:10] if enforcement else None,
            "observed_at": generated_at,
            "source_modified_at": source_modified,
            "source_modified_origin": "source_frontmatter_unverified" if source_modified else "unknown",
            "live_verified_at": None,
            "status": law.metadata.get("상태"),
            "source_path": law.relative_path,
            "upstream_commit": commit,
            "verification_status": "unverified",
            "evidence_kind": "snapshot",
            "live_verified": False,
            "live_validation_status": "not_tested_owner_key_required",
            "freshness_status": classify_freshness(generated_at, source_modified),
            "temporal_relation": temporal_relation,
            "legal_effect_status": "not_determined",
            "metadata_source": "legalize-kr.git.markdown" if commit else "local_unverified_markdown",
            "legal_advice": False,
            "human_review_required": True,
            "amendment_status": "not_determined",
            "supersession_status": "not_determined",
            "fordongdorrong_use_cases": [
                "legal citation grounding",
                "policy/compliance checklist context",
                "law-aware RAG retrieval",
            ],
            "source_evidence": {
                "source": "legalize-kr verified pinned checkout" if commit else "unverified local markdown",
                "path": law.relative_path,
                "commit": commit,
                "claim_boundary": "법령 원문 snapshot 검색용 근거입니다. 최신성·법률 판단은 법제처 원문/MCP 및 전문가 검토로 확인해야 합니다.",
                "force_push_warning": "legalize-kr upstream may force-push; keep source path and law metadata with commit.",
            },
        },
    }


def stable_document_id(relative_path: str, article: Article, law_id: str = "", law_type: str = "") -> str:
    if relative_path.startswith("upstreams/legalize-kr/"):
        relative_path = relative_path.removeprefix("upstreams/legalize-kr/")
    logical_law = f"id/{law_id}/{law_type}" if law_id else relative_path
    slug = re.sub(r"[^0-9A-Za-z가-힣_.()/-]+", "-", logical_law).strip("-")
    article_slug = re.sub(r"[^0-9A-Za-z가-힣_.()-]+", "-", article.article_no).strip("-")
    section_slug = re.sub(r"[^0-9A-Za-z가-힣_.()-]+", "-", article.section_key).strip("-")
    return f"legalize-kr/{slug}#{section_slug}/{article_slug}"


def migration_report(source_dir: Path, root: Path, previous_jsonl: Path) -> dict[str, Any]:
    """Inventory mapping only; never touches a consumer DB or previous export."""
    commit, _ = verified_upstream_commit(root, "legalize-kr")
    current = list(knowledge_documents(source_dir, root, utc_now(), commit))
    mappings, unresolved = [], []
    for line in previous_jsonl.read_text(encoding="utf-8").splitlines():
        old = json.loads(line)
        meta = old.get("metadata", {})
        candidates = [doc for doc in current if
                      doc["metadata"]["source_path"] == meta.get("source_path") and
                      doc["metadata"]["article_no"] == meta.get("article_no") and
                      (not meta.get("article_title") or doc["metadata"]["article_title"] == meta["article_title"])]
        if len(candidates) == 1:
            mappings.append({"old_id": old["document_id"], "new_id": candidates[0]["document_id"]})
        else:
            unresolved.append({"old_id": old.get("document_id"), "reason": "missing_or_ambiguous_identity",
                               "candidate_count": len(candidates)})
    return {"dry_run": True, "mapping_count": len(mappings), "mappings": mappings,
            "unresolved": unresolved, "safe_to_apply_automatically": False,
            "warning": "Mappings use the supplied prior export, never current ordinal assumptions; review manually."}


def build_manifest(
    *,
    root: Path,
    source_dir: Path,
    jsonl_path: Path,
    sqlite_path: Path,
    documents: list[dict[str, Any]],
    generated_at: str,
    legalize_commit: str | None,
    mcp_dir: Path,
    mcp_commit: str | None,
    law_oc_configured: bool,
) -> dict[str, Any]:
    mcp_build = mcp_dir / "build" / "index.js"
    mcp_cli = mcp_dir / "build" / "cli.js"
    return {
        "backend_id": SOURCE_ID,
        "generated_at": generated_at,
        "purpose": "fordongdorrong backend/RAG/SQLite pre-integration contract for Korean law evidence.",
        "local_export": {
            "status": "ready",
            "requires_api_key": False,
            "source_dir": relative(source_dir, root),
            "jsonl": relative(jsonl_path, root),
            "sqlite": relative(sqlite_path, root),
            "document_count": len(documents),
            "source_commit": legalize_commit,
        },
        "live_mcp": {
            "status": "upstream_built_local_only" if mcp_build.exists() else "upstream_not_built",
            "authentication_status": "not_tested",
            "health_status": "not_tested",
            "law_query_status": "not_tested",
            "live_verified": False,
            "requires_api_key": True,
            "api_key_env": "LAW_OC",
            "api_key_configured": law_oc_configured,
            "upstream_dir": relative(mcp_dir, root),
            "upstream_commit": mcp_commit,
            "stdio": {
                "command": "node",
                "args": [relative(mcp_build, root)],
                "env": {"LAW_OC": "${LAW_OC}"},
            },
            "http": {
                "command": "node",
                "args": [relative(mcp_build, root), "--mode", "http", "--port", "18765"],
                "health": "http://127.0.0.1:18765/health",
                "mcp": "http://127.0.0.1:18765/mcp",
            },
            "cli": {
                "command": "node",
                "args": [relative(mcp_cli, root)],
            },
        },
        "fallback_policy": {
            "if_law_oc_missing": "Use local_export JSONL/SQLite for retrieval and display LAW_OC-required live MCP features as unavailable.",
            "if_law_oc_present": "Use local_export as stable RAG base and optionally call live_mcp for latest search/cases/interpretations.",
            "no_secret_persistence": True,
        },
        "safety": {
            "legal_advice": False,
            "human_review_required": True,
            "filing_enabled": False,
            "submission_enabled": False,
            "account_actions_enabled": False,
            "external_writes": False,
            "must_cite": ["law_title", "law_type", "article_no", "enforcement_date", "source_path"],
            "claim_boundary": "검색/근거 제공용 백엔드입니다. 실제 법률 판단·사건 대응은 최신 원문과 전문가 검토가 필요합니다.",
        },
        "sqlite_schema": {
            "documents": [
                "source_id",
                "document_id",
                "title",
                "body",
                "uri",
                "content_hash",
                "created_at",
                "updated_at",
                "visibility",
                "lifecycle",
                "deleted_at",
                "indexable",
                "metadata_json",
            ],
            "fts": "documents_fts(title, body) when SQLite FTS5 is available",
        },
    }


def write_jsonl(path: Path, documents: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [json.dumps(document, ensure_ascii=False, separators=(",", ":")) for document in documents]
    path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_sqlite(path: Path, documents: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE documents (
              source_id TEXT NOT NULL,
              document_id TEXT NOT NULL,
              title TEXT NOT NULL,
              body TEXT NOT NULL,
              uri TEXT NOT NULL,
              content_hash TEXT NOT NULL,
              created_at TEXT,
              updated_at TEXT NOT NULL,
              visibility TEXT NOT NULL,
              lifecycle TEXT NOT NULL,
              deleted_at TEXT,
              indexable INTEGER NOT NULL,
              metadata_json TEXT NOT NULL,
              PRIMARY KEY (source_id, document_id)
            )
            """
        )
        conn.execute("CREATE INDEX idx_documents_updated_at ON documents(updated_at)")
        conn.execute("CREATE INDEX idx_documents_indexable ON documents(indexable)")
        conn.executemany(
            """
            INSERT INTO documents (
              source_id, document_id, title, body, uri, content_hash, created_at,
              updated_at, visibility, lifecycle, deleted_at, indexable, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    document["source_id"],
                    document["document_id"],
                    document["title"],
                    document["body"],
                    document["uri"],
                    document["content_hash"],
                    document["created_at"],
                    document["updated_at"],
                    document["visibility"],
                    document["lifecycle"],
                    document["deleted_at"],
                    1 if document["indexable"] else 0,
                    json.dumps(document["metadata"], ensure_ascii=False, separators=(",", ":")),
                )
                for document in documents
            ],
        )
        try:
            conn.execute("CREATE VIRTUAL TABLE documents_fts USING fts5(title, body, document_id UNINDEXED)")
            conn.executemany(
                "INSERT INTO documents_fts(title, body, document_id) VALUES (?, ?, ?)",
                [(document["title"], document["body"], document["document_id"]) for document in documents],
            )
        except sqlite3.OperationalError:
            conn.execute("CREATE TABLE documents_fts_unavailable(reason TEXT NOT NULL)")
            conn.execute(
                "INSERT INTO documents_fts_unavailable(reason) VALUES (?)",
                ("SQLite FTS5 extension is not available in this runtime.",),
            )


def git_commit(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def verified_upstream_commit(root: Path, name: str) -> tuple[str | None, str]:
    """Never infer upstream provenance from Git's parent-directory discovery."""
    target = root / "upstreams" / name
    lock_path = Path(__file__).resolve().parents[1] / "upstreams.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    spec = next(item for item in lock["upstreams"] if item["name"] == name)
    if not (target / ".git").exists():
        return None, "pinned upstream checkout absent"
    try:
        top = subprocess.run(["git", "-C", str(target), "rev-parse", "--show-toplevel"],
                             check=True, capture_output=True, text=True).stdout.strip()
        remote = subprocess.run(["git", "-C", str(target), "remote", "get-url", "origin"],
                                check=True, capture_output=True, text=True).stdout.strip()
        commit = git_commit(target)
        dirty = subprocess.run(["git", "-C", str(target), "status", "--porcelain"],
                               check=True, capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError:
        return None, "upstream Git metadata unavailable"
    if Path(top).resolve() != target.resolve() or remote != spec["url"] or commit != spec["commit"] or dirty:
        return None, "upstream checkout differs from pinned provenance"
    return commit, "pinned checkout verified"


def date_to_iso(value: str) -> str | None:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return f"{value}T00:00:00+09:00"


def classify_freshness(observed_at: str, source_modified_at: str | None,
                       *, stale_after_days: int | None = None, conflicting: bool = False) -> str:
    """Data freshness only; never a conclusion about legal validity."""
    if conflicting:
        return "conflicting_source"
    if stale_after_days is not None and source_modified_at is not None:
        from datetime import timedelta
        if datetime.fromisoformat(observed_at.replace("Z", "+00:00")) - datetime.fromisoformat(source_modified_at) > timedelta(days=stale_after_days):
            return "stale_by_explicit_policy"
    return "observed_unverified"


def sqlite_fts_available(path: Path) -> bool:
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE name='documents_fts'").fetchone() is not None


def verify_staged(jsonl: Path, sqlite: Path, manifest: Path) -> bool:
    if not all(path.is_file() for path in (jsonl, sqlite, manifest)):
        raise FileNotFoundError("Export artifact missing")
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    docs = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
    with sqlite3.connect(f"file:{quote(str(sqlite.resolve()))}?mode=ro", uri=True) as conn:
        rows = conn.execute("SELECT document_id, content_hash, metadata_json FROM documents").fetchall()
    if len(docs) != len(rows) or len(docs) != meta["local_export"]["document_count"]:
        raise ValueError("Export artifact counts disagree")
    if {d["document_id"]: (d["content_hash"], d["metadata"]) for d in docs} != {
        doc_id: (digest, json.loads(metadata)) for doc_id, digest, metadata in rows
    }:
        raise ValueError("Export artifact content disagrees")
    for path, field in ((jsonl, "jsonl_sha256"), (sqlite, "sqlite_sha256")):
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta["generation"][field]:
            raise ValueError("Export checksum mismatch")
    return True


def verify_published(jsonl: Path, sqlite: Path, manifest: Path) -> bool:
    """Read-only consumer gate; rejects mixed generations after interrupted publish."""
    try:
        verify_staged(jsonl, sqlite, manifest)
    except (OSError, ValueError, KeyError, sqlite3.DatabaseError, json.JSONDecodeError):
        return False
    return True


def verify_fixed_baseline(jsonl: Path, sqlite: Path, manifest: Path) -> bool:
    """Validate a complete fixed triplet, including older manifests without hashes."""
    if not all(path.is_file() for path in (jsonl, sqlite, manifest)):
        return False
    try:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        local = meta["local_export"]
        if local.get("status") not in {"ready", "unverified_source"}:
            return False
        if "generation" in meta:
            return meta["generation"].get("complete_snapshot") is True and verify_published(jsonl, sqlite, manifest)
        docs = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
        with sqlite3.connect(f"file:{quote(str(sqlite.resolve()))}?mode=ro", uri=True) as conn:
            rows = conn.execute("SELECT document_id, content_hash, metadata_json FROM documents").fetchall()
        return (len(docs) > 0 and len(docs) == len(rows) == local["document_count"] and
                {d["document_id"]: (d["content_hash"], d["metadata"]) for d in docs} ==
                {doc_id: (digest, json.loads(metadata)) for doc_id, digest, metadata in rows})
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError, json.JSONDecodeError):
        return False


def recover_first_publish(root: Path, source_dir: Path, jsonl_path: Path, sqlite_path: Path,
                          manifest_path: Path, *, apply: bool = False) -> dict[str, Any]:
    """Inspect or quarantine journal-proven first-publish partials; never delete old data."""
    del source_dir
    paths = (jsonl_path, sqlite_path, manifest_path)
    journal = manifest_path.parent / ".law-first-publish.journal.json"
    reject_output_path(journal, root)
    if not journal.is_file():
        return {"recoverable": False, "reason": "no first-publish journal", "dry_run": not apply}
    try:
        try:
            record = json.loads(journal.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            if any(path.exists() or path.is_symlink() for path in paths):
                raise ValueError("malformed journal with outputs requires manual review")
            quarantined = None
            if apply:
                quarantined = quarantine_file(journal, root)
            return {"recoverable": True, "complete": False, "malformed_zero_output": True,
                    "quarantine": relative(quarantined, root) if quarantined else None, "dry_run": not apply}
        if (not isinstance(record, dict) or record.get("schema") != 1 or
                record.get("paths") != [relative(path, root) for path in paths] or
                not isinstance(record.get("sha256"), list) or len(record["sha256"]) != 3 or
                any(not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    for digest in record["sha256"])):
            raise ValueError("journal does not match requested output paths")
        existing = []
        for path, digest in zip(paths, record["sha256"], strict=True):
            reject_output_path(path, root)
            if path.exists():
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError("partial output differs from journal; manual review required")
                existing.append(path)
        if len(existing) == 3 and verify_published(*paths):
            if apply:
                safe_unlink(journal, root)
            return {"recoverable": True, "complete": True, "dry_run": not apply}
        if apply:
            for path in existing:
                quarantined = quarantine_file(path, root)
                if hashlib.sha256(quarantined.read_bytes()).hexdigest() != record["sha256"][paths.index(path)]:
                    # Another writer changed the leaf after inspection. Restore only
                    # without replacing anything; retain quarantine for audit.
                    try:
                        safe_link_new(quarantined, path, root)
                    except FileExistsError:
                        pass
                    raise ValueError(f"partial output changed during recovery; preserved {relative(quarantined, root)}")
            if any(path.exists() for path in paths):
                raise ValueError("new output appeared during recovery; journal retained")
            safe_unlink(journal, root)
        return {"recoverable": True, "complete": False, "files": [relative(path, root) for path in existing],
                "dry_run": not apply}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"recoverable": False, "reason": str(exc), "dry_run": not apply}


def reject_output_path(path: Path, root: Path) -> None:
    root = root.resolve()
    absolute = path.absolute()
    if not absolute.is_relative_to(root) or not absolute.resolve().is_relative_to(root):
        raise ValueError("Output must be inside root")
    current = absolute
    while current != root:
        if current.is_symlink():
            raise ValueError("Output symlink component forbidden")
        current = current.parent


def open_parent_dir(path: Path, root: Path) -> int:
    """Anchor publication to no-follow directory descriptors, not a re-resolved path."""
    root = root.resolve()
    absolute = path.absolute()
    if not absolute.is_relative_to(root):
        raise ValueError("Publication path escapes root")
    relative_parts = absolute.relative_to(root).parts[:-1]
    if ".." in relative_parts:
        raise ValueError("Publication path contains parent traversal")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative_parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def safe_replace(source: Path, destination: Path, root: Path) -> None:
    source_fd = open_parent_dir(source, root)
    try:
        destination_fd = open_parent_dir(destination, root)
        try:
            os.replace(source.name, destination.name, src_dir_fd=source_fd, dst_dir_fd=destination_fd)
        finally:
            os.close(destination_fd)
    finally:
        os.close(source_fd)


def safe_create_json(path: Path, value: dict[str, Any], root: Path) -> None:
    """Durably stage JSON, then claim the final journal name without replacement."""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    _safe_create_json_direct(temporary, value, root)
    try:
        # A hard link is atomic and fails with EEXIST if another publisher won.
        # The temp and journal live in the same directory/filesystem.
        safe_link_new(temporary, path, root)
        sync_dir(path.parent)
    finally:
        if temporary.exists():
            safe_unlink(temporary, root)
            sync_dir(path.parent)


def _safe_create_json_direct(path: Path, value: dict[str, Any], root: Path) -> None:
    parent_fd = open_parent_dir(path, root)
    try:
        descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent_fd)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            os.unlink(path.name, dir_fd=parent_fd)
            raise
    finally:
        os.close(parent_fd)


def safe_unlink(path: Path, root: Path) -> None:
    parent_fd = open_parent_dir(path, root)
    try:
        os.unlink(path.name, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)


def quarantine_file(path: Path, root: Path) -> Path:
    """Move a leaf to a unique same-directory audit path; never unlink unknown bytes."""
    destination = path.with_name(f".law-recovery-{uuid.uuid4().hex}-{path.name.lstrip('.')}")
    safe_replace(path, destination, root)
    sync_dir(path.parent)
    return destination


def safe_link_new(source: Path, destination: Path, root: Path) -> None:
    source_fd = open_parent_dir(source, root)
    try:
        destination_fd = open_parent_dir(destination, root)
        try:
            os.link(source.name, destination.name, src_dir_fd=source_fd,
                    dst_dir_fd=destination_fd, follow_symlinks=False)
        finally:
            os.close(destination_fd)
    finally:
        os.close(source_fd)


def sync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def sync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_current_generation(root: Path, pointer: Path) -> list[dict[str, Any]]:
    """Pin one immutable generation before reading; never mix fixed-path opens."""
    pinned = json.loads(pointer.read_text(encoding="utf-8"))
    target = root / pinned["generation_manifest"]
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Generation pointer escapes root")
    jsonl, sqlite = target.parent / "out.jsonl", target.parent / "out.db"
    if not verify_published(jsonl, sqlite, target):
        raise ValueError("Generation verification failed")
    if json.loads(target.read_text(encoding="utf-8"))["generation"]["id"] != pinned["generation_id"]:
        raise ValueError("Generation pointer does not match manifest")
    return [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def assert_no_secret_like_payload(values: Iterable[Any]) -> None:
    serialized = json.dumps(list(values), ensure_ascii=False)
    for match in SECRET_KEY_RE.finditer(serialized):
        # The manifest intentionally names the LAW_OC env var. Reject only
        # common assignment-looking leaks, not the env-var name itself.
        start = max(match.start() - 16, 0)
        end = min(match.end() + 64, len(serialized))
        context = serialized[start:end]
        if re.search(r"(?i)(law_oc|api[_-]?key|token|secret|password)[\"']?\s*[:=]\s*[A-Za-z0-9_\-]{8,}", context):
            raise ValueError("secret-like value detected in export payload")


if __name__ == "__main__":
    main()
