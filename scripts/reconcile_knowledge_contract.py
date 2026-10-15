#!/usr/bin/env python3
"""Offline validation against a pinned, complete central Knowledge v1 schema."""
import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures"
CONTRACT = FIXTURE / "central-knowledge-v1-contract.json"
SCHEMA = FIXTURE / "knowledge-document.v1.schema.json"


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


def reconcile(jsonl: Path, contract: dict) -> dict:
    payload = SCHEMA.read_bytes()
    if hashlib.sha256(payload).hexdigest() != contract["schema_sha256"]:
        raise ValueError("Pinned central schema checksum mismatch")
    schema = json.loads(payload)
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
            "violations": violations, "central_commit": contract["upstream_commit"],
            "schema_sha256": contract["schema_sha256"], "central_writes": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.jsonl, json.loads(CONTRACT.read_text(encoding="utf-8"))), indent=2))


if __name__ == "__main__":
    main()
