import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_runtime import prepare


class RuntimePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.upstream = self.root / "upstream"
        self.upstream.mkdir()
        (self.upstream / "package-lock.json").write_text("old\n")
        (self.upstream / "application.js").write_text("application unchanged\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        commit = self.git("rev-parse", "HEAD").strip()
        patch = self.root / "dependencies.patch"
        patch.write_text("--- a/package-lock.json\n+++ b/package-lock.json\n@@ -1 +1 @@\n-old\n+new\n")
        digest = lambda value: hashlib.sha256(value).hexdigest()
        self.manifest = {"upstream_name": "fixture", "upstream_commit": commit,
                         "original_package_lock_sha256": digest(b"old\n"),
                         "runtime_package_lock_sha256": digest(b"new\n"),
                         "patch": patch.name, "patch_sha256": digest(patch.read_bytes())}
        self.write_manifest()
        (self.root / "upstreams.lock.json").write_text(json.dumps({"upstreams": [{"name": "fixture", "commit": commit}]}))
        self.destination = self.root / "runtime"

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.upstream), *args], check=True,
                              capture_output=True, text=True).stdout

    def write_manifest(self):
        (self.root / "runtime.lock.json").write_text(json.dumps(self.manifest))

    def test_exports_patched_runtime_without_changing_upstream(self):
        prepare(self.upstream, self.destination, self.root)
        self.assertEqual((self.destination / "package-lock.json").read_text(), "new\n")
        self.assertEqual((self.upstream / "package-lock.json").read_text(), "old\n")
        self.assertEqual((self.destination / "application.js").read_bytes(), (self.upstream / "application.js").read_bytes())
        self.assertFalse(self.git("status", "--porcelain"))

    def test_rejects_changed_patch(self):
        (self.root / "dependencies.patch").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "patch hash"):
            prepare(self.upstream, self.destination, self.root)
        self.assertFalse(self.destination.exists())

    def test_rejects_dirty_upstream(self):
        (self.upstream / "application.js").write_text("modified")
        with self.assertRaisesRegex(ValueError, "dirty"):
            prepare(self.upstream, self.destination, self.root)

    def test_refuses_existing_runtime(self):
        self.destination.mkdir()
        (self.destination / "preserve").write_text("existing")
        with self.assertRaisesRegex(ValueError, "already exists"):
            prepare(self.upstream, self.destination, self.root)
        self.assertEqual((self.destination / "preserve").read_text(), "existing")

    def test_rejects_changed_application_source(self):
        patch = self.root / "dependencies.patch"
        patch.write_text(patch.read_text() + "--- a/application.js\n+++ b/application.js\n@@ -1 +1 @@\n-application unchanged\n+changed\n")
        self.manifest["patch_sha256"] = hashlib.sha256(patch.read_bytes()).hexdigest()
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "application source"):
            prepare(self.upstream, self.destination, self.root)
        self.assertFalse(self.destination.exists())
