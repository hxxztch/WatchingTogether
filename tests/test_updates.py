"""Release selection and file-level update checks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from app.updates import find_update


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_delta", ROOT / "packaging/make_delta.py")
make_delta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_delta)


def release(tag, assets):
    base = "https://github.com/hxxztch/WatchingTogether/releases"
    return {"tag_name": tag, "html_url": base + "/tag/" + tag,
            "assets": [{"name": name, "browser_download_url": base + "/download/" + tag + "/" + name,
                        "digest": "sha256:" + "0" * 64} for name in assets]}


class UpdateTests(unittest.TestCase):
    def test_selects_latest_beta_with_matching_delta(self):
        releases = [
            release("server1.2.0", ["server1.2.0.zip"]),
            release("beta0.1.1", ["beta0.1.1.zip", "beta0.1.0-to-beta0.1.1.delta.zip"]),
            release("beta0.1.2", ["beta0.1.2.zip", "beta0.1.0-to-beta0.1.2.delta.zip",
                                    "beta0.1.0-to-beta0.1.2.delta.json"]),
            release("v1.4.0", ["v1.4.0.zip"]),
        ]
        selected = find_update(releases, "beta0.1.0")
        self.assertEqual(selected.tag, "beta0.1.2")
        self.assertEqual(selected.delta_name, "beta0.1.0-to-beta0.1.2.delta.zip")
        self.assertTrue(selected.manifest_url.endswith(".delta.json"))
        self.assertIsNone(find_update(releases, "beta0.1.2"))

    def test_delta_lists_only_changed_and_deleted_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_zip = root / "old.zip"
            new_zip = root / "new.zip"
            delta_zip = root / "beta0.1.0-to-beta0.1.1.delta.zip"
            with zipfile.ZipFile(old_zip, "w") as archive:
                archive.writestr("client-beta0.1.0/same.txt", "same")
                archive.writestr("client-beta0.1.0/change.txt", "old")
                archive.writestr("client-beta0.1.0/remove.txt", "remove")
            with zipfile.ZipFile(new_zip, "w") as archive:
                archive.writestr("client-beta0.1.1/same.txt", "same")
                archive.writestr("client-beta0.1.1/change.txt", "new")
                archive.writestr("client-beta0.1.1/add.txt", "add")
            manifest = make_delta.create_delta(old_zip, new_zip, "beta0.1.0", "beta0.1.1", delta_zip)
            self.assertEqual([item["path"] for item in manifest["files"]], ["add.txt", "change.txt"])
            self.assertEqual([item["path"] for item in manifest["removed"]], ["remove.txt"])
            with zipfile.ZipFile(delta_zip) as archive:
                self.assertEqual(set(archive.namelist()),
                                 {"manifest.json", "files/add.txt", "files/change.txt"})
            self.assertEqual(json.loads(delta_zip.with_suffix(".json").read_text(encoding="utf-8")), manifest)
            if os.name == "nt":
                install = root / "installed"
                install.mkdir()
                (install / "same.txt").write_text("same")
                (install / "change.txt").write_text("old")
                (install / "remove.txt").write_text("remove")
                result = subprocess.run([
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ROOT / "packaging/apply_update.ps1"), "-InstallDir", str(install),
                    "-DeltaZip", str(delta_zip), "-FromVersion", "beta0.1.0",
                    "-ToVersion", "beta0.1.1", "-NoRestart",
                ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((install / "change.txt").read_text(), "new")
                self.assertEqual((install / "add.txt").read_text(), "add")
                self.assertFalse((install / "remove.txt").exists())
                self.assertEqual((install / "same.txt").read_text(), "same")
                tampered = root / "tampered"
                tampered.mkdir()
                (tampered / "change.txt").write_text("user edit")
                (tampered / "remove.txt").write_text("remove")
                rejected = subprocess.run([
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ROOT / "packaging/apply_update.ps1"), "-InstallDir", str(tampered),
                    "-DeltaZip", str(delta_zip), "-FromVersion", "beta0.1.0",
                    "-ToVersion", "beta0.1.1", "-NoRestart",
                ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
                self.assertNotEqual(rejected.returncode, 0)
                self.assertEqual((tampered / "change.txt").read_text(), "user edit")
                self.assertFalse((tampered / "add.txt").exists())


if __name__ == "__main__":
    unittest.main()
