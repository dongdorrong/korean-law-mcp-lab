#!/usr/bin/env python3
"""Prepare immutable upstream snapshots; candidate updates are read-only proposals."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

LOCK = Path(__file__).resolve().parents[1] / "upstreams.lock.json"


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def prepare(root: Path, spec: dict) -> None:
    target = root / "upstreams" / spec["name"]
    if target.exists():
        if not (target / ".git").exists():
            raise ValueError(f"{spec['name']}: existing path is not a checkout")
        if git("-C", str(target), "remote", "get-url", "origin") != spec["url"]:
            raise ValueError(f"{spec['name']}: remote mismatch")
        if git("-C", str(target), "status", "--porcelain"):
            raise ValueError(f"{spec['name']}: dirty checkout")
        if git("-C", str(target), "rev-parse", "HEAD") != spec["commit"]:
            raise ValueError(f"{spec['name']}: checkout differs from lock; no automatic update")
        shallow = git("-C", str(target), "rev-parse", "--is-shallow-repository")
        if shallow not in {"true", "false"}:
            raise ValueError(f"{spec['name']}: shallow state could not be determined")
        for pattern in spec["sparse"]:
            if not any(path.is_file() for path in target.glob(pattern)):
                raise ValueError(f"{spec['name']}: pinned sparse path missing: {pattern}; use isolated fresh preparation")
        return
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{spec['name']}-", dir=parent) as temporary:
        checkout = Path(temporary) / "repo"
        git("clone", "--no-checkout", "--depth", "1", "--filter=blob:none", spec["url"], str(checkout))
        try:
            git("-C", str(checkout), "fetch", "--depth", "1", "origin", spec["commit"])
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"{spec['name']}: pinned commit unavailable; lock unchanged") from exc
        if git("-C", str(checkout), "rev-parse", "FETCH_HEAD") != spec["commit"]:
            raise ValueError(f"{spec['name']}: fetched unexpected commit")
        if spec["sparse"]:
            git("-C", str(checkout), "sparse-checkout", "set", "--no-cone", *spec["sparse"])
        git("-C", str(checkout), "checkout", "--detach", spec["commit"])
        for pattern in spec["sparse"]:
            if not any(path.is_file() for path in checkout.glob(pattern)):
                raise ValueError(f"{spec['name']}: pinned sparse path missing: {pattern}")
        checkout.rename(target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=LOCK.parent)
    parser.add_argument("--propose-update", action="store_true", help="Print candidate heads; do not change lock or checkouts")
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if args.propose_update:
        for spec in lock["upstreams"]:
            head = git("ls-remote", spec["url"], "HEAD").split()[0]
            print(json.dumps({"name": spec["name"], "locked": spec["commit"], "candidate": head,
                              "license_review_required": True}))
    else:
        for spec in lock["upstreams"]:
            prepare(args.root.resolve(), spec)


if __name__ == "__main__":
    main()
