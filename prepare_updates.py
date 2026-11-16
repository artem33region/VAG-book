"""Verify built APKs and prepare immutable files plus updates.json for git push."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOWNLOAD_BASE = "https://raw.githubusercontent.com/artem33region/VAG-book/main/releases/"
# Public certificate fingerprint of the existing installed APKs. The private key
# stays on the build machine and must never be committed.
SIGNER_SHA256 = "19fc0d40ae320a85c29c97258d1a798cc5c7e14782ecc2eac4e721f92338714a"
APPS = (
    ("android-manual", "ru.vagguides.golf4manual", "golf4", "VW_Golf4_Bora_Manual_RU.apk"),
    ("android-bfq", "ru.vagguides.bfqmanual", "bfq", "VW_BFQ_1_6_Manual_RU.apk"),
    ("android-bca", "ru.vagguides.bcamanual", "bca", "VW_BCA_1_4_Manual_RU.apk"),
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stage_apk(source: Path, destination: Path) -> None:
    if destination.exists():
        if sha256(destination) != sha256(source):
            raise ValueError(f"Release already exists with different contents: {destination.name}; increase versionCode")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def validate_progression(previous: dict, current: dict) -> None:
    for package, old in previous.get("apps", {}).items():
        if package not in current["apps"]:
            raise ValueError(f"Missing existing app: {package}")
        new = current["apps"][package]
        if new["versionCode"] < old["versionCode"]:
            raise ValueError(f"Version downgrade: {package}")
        if new["versionCode"] == old["versionCode"] and new["sha256"] != old["sha256"]:
            raise ValueError(f"Changed APK without a version increment: {package}")


def prepare(sdk: Path) -> dict:
    tools = sdk / "build-tools" / "34.0.0"
    signer = tools / ("apksigner.bat" if os.name == "nt" else "apksigner")
    aapt = tools / ("aapt.exe" if os.name == "nt" else "aapt")
    manifest = {"schemaVersion": 1, "apps": {}}
    staged = []
    for project, package, prefix, alias in APPS:
        directory = ROOT / project / "app/build/outputs/apk/debug"
        metadata = json.loads((directory / "output-metadata.json").read_text(encoding="utf-8"))
        element, = metadata["elements"]
        apk = directory / element["outputFile"]
        info = subprocess.run([str(aapt), "dump", "badging", str(apk)], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        match = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", info)
        if not match or (match[1], int(match[2]), match[3]) != (package, element["versionCode"], element["versionName"]):
            raise ValueError(f"APK does not match release metadata: {project}")
        signature = subprocess.run([str(signer), "verify", "--print-certs", str(apk)], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        fingerprints = re.findall(r"certificate SHA-256 digest: ([0-9a-f]+)", signature)
        if fingerprints != [SIGNER_SHA256]:
            raise ValueError(f"APK signed by a different key: {project}")
        code = element["versionCode"]
        size = apk.stat().st_size
        if not 0 < code <= 2147483647 or not 0 < size <= 100 * 1024 * 1024:
            raise ValueError(f"Invalid version or APK size: {project}")
        filename = f"{prefix}-{code}.apk"
        manifest["apps"][package] = {
            "packageName": package, "versionCode": code, "versionName": element["versionName"],
            "url": DOWNLOAD_BASE + filename, "sha256": sha256(apk), "size": size,
        }
        staged.append((apk, ROOT / "releases" / filename, ROOT / alias))
    target = ROOT / "updates.json"
    if target.exists():
        validate_progression(json.loads(target.read_text(encoding="utf-8")), manifest)
    for apk, destination, alias in staged:
        stage_apk(apk, destination)
        shutil.copy2(apk, alias)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return manifest


if __name__ == "__main__":
    default_sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if not default_sdk and os.name == "nt":
        default_sdk = str(Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=Path(default_sdk) if default_sdk else None)
    args = parser.parse_args()
    if args.sdk is None:
        parser.error("Pass --sdk or set ANDROID_HOME")
    print(json.dumps(prepare(args.sdk), ensure_ascii=False, indent=2))
