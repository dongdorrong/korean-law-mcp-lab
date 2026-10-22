#!/usr/bin/env python3
"""Offline pinned-v1 validation, with an explicit checksum-bound local v2 opt-in."""
import argparse
import copy
import hashlib
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures"
CONTRACT = FIXTURE / "central-knowledge-v1-contract.json"
SCHEMA = FIXTURE / "knowledge-document.v1.schema.json"
MAX_SCHEMA_BYTES = 1024 * 1024
V2_SOURCES = ["velog", "thing", "onenote", "github-stars", "korean-law-mcp-lab",
              "invest-machine", "tax-machine", "youtube-archive"]


def explicit_schema(path: Path, expected_sha256: str, historical: dict) -> tuple[dict, str]:
    """Read one regular local file; no schema fetching or implicit pin replacement."""
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("Expected schema SHA-256 must be 64 lowercase hex characters")
    path = Path(path)
    if ".." in path.parts:
        raise ValueError("Schema path traversal is not allowed")
    absolute = path.absolute()
    if any(part.is_symlink() for part in [absolute, *absolute.parents]):
        raise ValueError("Schema path must not contain symlinks")
    descriptor = os.open(absolute, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SCHEMA_BYTES:
            raise ValueError("Schema must be a bounded regular local file")
        raw = handle.read(MAX_SCHEMA_BYTES + 1)
    if len(raw) > MAX_SCHEMA_BYTES or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Explicit central schema checksum mismatch")
    schema = json.loads(raw)
    if not isinstance(schema, dict):
        raise ValueError("Unsupported explicit central schema")
    # This checker implements v1's exact constraints. Accept only the reviewed
    # v2 source extension; an unknown keyword must not silently bypass validation.
    candidate = copy.deepcopy(schema)
    properties = schema.get("properties")
    source = properties.get("source_id") if isinstance(properties, dict) else None
    if (schema.get("$id") != "https://fordongdorrong.local/schemas/knowledge-document.v2.schema.json"
            or not isinstance(source, dict) or source.get("enum") != V2_SOURCES):
        raise ValueError("Unsupported explicit central schema")
    for key in ("$id", "title", "description"):
        candidate[key] = historical[key]
    candidate["properties"]["source_id"]["enum"] = historical["properties"]["source_id"]["enum"]
    if candidate != historical:
        raise ValueError("Explicit schema changes unsupported constraints")
    return schema, expected_sha256


def validate_document(doc: dict, schema: dict) -> list[str]:
    errors = []
    if not isinstance(doc, dict):
        return ["document: expected object"]
    for key in schema["required"]:
        if key not in doc:
            errors.append(f"{key}: required")
    for key in doc.keys() - schema["properties"].keys():
        errors.append(f"{key}: additional property")
    for key, value in doc.items():
        rule = schema["properties"].get(key)
        if not rule:
            continue
        types = rule.get("type", [])
        if isinstance(types, str):
            types = [types]
        correct = any((kind == "null" and value is None) or
                      (kind == "string" and isinstance(value, str)) or
                      (kind == "boolean" and isinstance(value, bool)) or
                      (kind == "object" and isinstance(value, dict)) for kind in types)
        if not correct:
            errors.append(f"{key}: invalid type")
            continue
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{key}: invalid enum")
        if isinstance(value, str):
            if len(value) < rule.get("minLength", 0):
                errors.append(f"{key}: too short")
            if "pattern" in rule and not re.fullmatch(rule["pattern"], value):
                errors.append(f"{key}: invalid pattern")
            if rule.get("format") == "date-time":
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if not re.search(r"(Z|[+-]\d{2}:\d{2})$", value):
                        raise ValueError("timezone required")
                except ValueError:
                    errors.append(f"{key}: invalid date-time")
    if doc.get("lifecycle") == "tombstoned":
        if doc.get("indexable") is not False or not isinstance(doc.get("deleted_at"), str):
            errors.append("tombstoned: indexable=false and deleted_at required")
    if doc.get("indexable") is True and doc.get("lifecycle") in {"active", "stale"} and not doc.get("body"):
        errors.append("body: indexable document must have content")
    return errors


def reconcile(jsonl: Path, contract: dict, *, schema_path: Path | None = None,
              expected_schema_sha256: str | None = None) -> dict:
    if (schema_path is None) != (expected_schema_sha256 is None):
        raise ValueError("Explicit schema path and expected SHA-256 must be supplied together")
    payload = SCHEMA.read_bytes()
    if hashlib.sha256(payload).hexdigest() != contract["schema_sha256"]:
        raise ValueError("Pinned central schema checksum mismatch")
    schema = json.loads(payload)
    digest = contract["schema_sha256"]
    if schema_path is not None:
        schema, digest = explicit_schema(schema_path, expected_schema_sha256, schema)
    violations = []
    count = 0
    for count, line in enumerate(jsonl.read_text(encoding="utf-8").splitlines(), 1):
        try:
            doc = json.loads(line)
            errors = validate_document(doc, schema)
        except json.JSONDecodeError:
            errors = ["document: invalid JSON"]
        violations.extend({"line": count, "code": error} for error in errors)
    return {"dry_run": True, "documents": count, "compatible": not violations,
            "violations": violations,
            "central_commit": contract["upstream_commit"] if schema_path is None else None,
            "schema_sha256": digest, "schema_id": schema["$id"],
            "contract_selection": "historical_pinned_v1" if schema_path is None else "explicit_local_v2",
            "central_writes": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--expected-schema-sha256")
    args = parser.parse_args()
    if (args.schema is None) != (args.expected_schema_sha256 is None):
        parser.error("--schema and --expected-schema-sha256 must be supplied together")
    print(json.dumps(reconcile(args.jsonl, json.loads(CONTRACT.read_text(encoding="utf-8")),
                               schema_path=args.schema,
                               expected_schema_sha256=args.expected_schema_sha256), indent=2))


if __name__ == "__main__":
    main()
