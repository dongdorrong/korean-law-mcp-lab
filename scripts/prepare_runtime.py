#!/usr/bin/env python3
"""Export the immutable upstream and apply the reviewed dependency-only patch.

Creates a new destination, never edits the upstream or an existing runtime.
Dependency installation and build are explicit separate commands.
"""
import argparse
import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(upstream: Path, destination: Path, root: Path = ROOT) -> dict:
    manifest = json.loads((root / "runtime.lock.json").read_text())
    spec = next(item for item in json.loads((root / "upstreams.lock.json").read_text())["upstreams"]
                if item["name"] == manifest["upstream_name"])
    if manifest["upstream_commit"] != spec["commit"]:
        raise ValueError("runtime lineage differs from upstream lock")
    patch = root / manifest["patch"]
    if sha256(patch) != manifest["patch_sha256"]:
        raise ValueError("reviewed patch hash mismatch")
    def git(*args: str) -> bytes:
        return subprocess.run(["git", "-C", str(upstream), *args], check=True,
                              capture_output=True).stdout
    if git("rev-parse", "HEAD").decode().strip() != spec["commit"]:
        raise ValueError("upstream is not the immutable locked commit")
    if git("status", "--porcelain").strip():
        raise ValueError("upstream checkout is dirty")
    if sha256(upstream / "package-lock.json") != manifest["original_package_lock_sha256"]:
        raise ValueError("original dependency lock hash mismatch")
    if destination.exists():
        raise ValueError("destination already exists; use a new generation")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".law-runtime-", dir=destination.parent) as temporary:
        exported = Path(temporary) / "source"
        exported.mkdir()
        with tarfile.open(fileobj=io.BytesIO(git("archive", "HEAD"))) as archive:
            archive.extractall(exported, filter="data")
        expected_source = {path.relative_to(exported): path.read_bytes()
                           for path in exported.rglob("*") if path.is_file()
                           and path.relative_to(exported).as_posix() != "package-lock.json"}
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=exported, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=exported, check=True)
        if sha256(exported / "package-lock.json") != manifest["runtime_package_lock_sha256"]:
            raise ValueError("patched dependency lock hash mismatch")
        patched_source = {path.relative_to(exported): path.read_bytes()
                          for path in exported.rglob("*") if path.is_file()
                          and path.relative_to(exported).as_posix() != "package-lock.json"}
        if expected_source != patched_source:
            raise ValueError("patch changed application source")
        (exported / "runtime-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
        exported.rename(destination)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT / "upstreams/korean-law-mcp")
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.upstream.resolve(), args.destination.resolve())
    print(json.dumps({"status": "PREPARED_NOT_BUILT", "name": result["name"],
                      "lock_sha256": result["runtime_package_lock_sha256"]}))


if __name__ == "__main__":
    main()
