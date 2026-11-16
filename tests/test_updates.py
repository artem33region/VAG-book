import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import prepare_updates

ROOT = Path(__file__).resolve().parents[1]


class UpdateTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("javac") and shutil.which("java"), "Java JDK is required")
    def test_android_update_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = ROOT / "android-manual/app/src/main/java/ru/vagguides/golf4manual/UpdateInfo.java"
            subprocess.run(["javac", "-encoding", "UTF-8", "-d", directory, str(source),
                            str(ROOT / "tests/java/UpdateInfoTest.java")], check=True, capture_output=True)
            result = subprocess.run(["java", "-cp", directory, "ru.vagguides.golf4manual.UpdateInfoTest"],
                                    check=True, capture_output=True, text=True)
            self.assertIn("23 update policy checks passed", result.stdout)

    def test_shared_update_code_is_identical(self):
        for filename in ["UpdateInfo.java", "UpdateActivity.java", "UpdateClient.java", "AutoUpdateChecker.java", "AutoUpdatePolicy.java"]:
            suffix = Path("app/src/main/java/ru/vagguides/golf4manual") / filename
            self.assertEqual((ROOT / "android-manual" / suffix).read_bytes(), (ROOT / "android-bfq" / suffix).read_bytes())

    @unittest.skipUnless(shutil.which("javac") and shutil.which("java"), "Java JDK is required")
    def test_automatic_update_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            source = ROOT / "android-manual/app/src/main/java/ru/vagguides/golf4manual/AutoUpdatePolicy.java"
            subprocess.run(["javac", "-encoding", "UTF-8", "-d", directory, str(source),
                            str(ROOT / "tests/java/AutoUpdatePolicyTest.java")], check=True, capture_output=True)
            result = subprocess.run(["java", "-cp", directory, "ru.vagguides.golf4manual.AutoUpdatePolicyTest"],
                                    check=True, capture_output=True, text=True)
            self.assertIn("12 automatic update checks passed", result.stdout)

    def test_published_versions_are_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / "source.apk", Path(directory) / "release.apk"
            source.write_bytes(b"first")
            prepare_updates.stage_apk(source, destination)
            prepare_updates.stage_apk(source, destination)
            source.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                prepare_updates.stage_apk(source, destination)
            self.assertEqual(destination.read_bytes(), b"first")

    def test_manifest_rejects_downgrade_or_same_version_different_apk(self):
        previous = {"apps": {"app": {"versionCode": 5, "sha256": "abc"}}}
        prepare_updates.validate_progression(previous, previous)
        newer = copy.deepcopy(previous)
        newer["apps"]["app"]["versionCode"] = 6
        prepare_updates.validate_progression(previous, newer)
        for invalid in [{"apps": {}}, {"apps": {"app": {"versionCode": 4, "sha256": "abc"}}},
                        {"apps": {"app": {"versionCode": 5, "sha256": "different"}}}]:
            with self.assertRaises(ValueError):
                prepare_updates.validate_progression(previous, invalid)

    def test_published_apks_match_manifest(self):
        manifest_path = ROOT / "updates.json"
        if not manifest_path.exists():
            self.skipTest("Run prepare_updates.py first")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schemaVersion"], 1)
        for package, entry in manifest["apps"].items():
            path = ROOT / "releases" / entry["url"].rsplit("/", 1)[-1]
            self.assertEqual(package, entry["packageName"])
            self.assertEqual(entry["size"], path.stat().st_size)
            self.assertEqual(entry["sha256"], prepare_updates.sha256(path))
