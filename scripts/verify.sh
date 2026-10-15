#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
PYTHON="${PYTHON:-python3}"
"$PYTHON" -m unittest discover -s tests -v
CACHE="$(mktemp -d)"
trap 'rm -r "$CACHE"' EXIT
PYTHONPYCACHEPREFIX="$CACHE" "$PYTHON" -m compileall -q scripts tests
"$PYTHON" - "$ROOT" <<'PY'
import json, tempfile, sys
from pathlib import Path
from scripts.export_fordongdorrong_backend import export_backend, verify_published
from scripts.reconcile_knowledge_contract import reconcile, CONTRACT
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    source = root / 'kr' / 'synthetic'
    source.mkdir(parents=True)
    (source / '법률.md').write_text('---\n제목: 합성법\n법령ID: 000001\n법령구분: 법률\n---\n##### 제1조 (예시)\n합성 텍스트.\n', encoding='utf-8')
    paths = [root / name for name in ('out.jsonl', 'out.db', 'manifest.json')]
    export_backend(root=root, source_dir=source.parent, jsonl_path=paths[0], sqlite_path=paths[1], manifest_path=paths[2])
    assert verify_published(*paths)
    report = reconcile(paths[0], json.loads(CONTRACT.read_text(encoding='utf-8')))
    assert not report['compatible'] and all(v['code'] == 'SOURCE_ID_NOT_ALLOWED' for v in report['violations'])
    print('synthetic export: validated; central source_id gate: blocked as expected')
PY
