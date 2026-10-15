#!/usr/bin/env python3
"""Offline pre-import reconciliation; never mutates central Knowledge data."""
import argparse
import json
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[1] / "tests/fixtures/central-knowledge-v1-contract.json"


def reconcile(jsonl: Path, contract: dict) -> dict:
    violations = []
    count = 0
    for count, line in enumerate(jsonl.read_text(encoding="utf-8").splitlines(), 1):
        doc = json.loads(line)
        missing = sorted(set(contract["required"]) - doc.keys())
        if missing:
            violations.append({"line": count, "code": "MISSING_FIELDS", "fields": missing})
        if doc.get("source_id") not in contract["source_id_enum"]:
            violations.append({"line": count, "code": "SOURCE_ID_NOT_ALLOWED"})
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
