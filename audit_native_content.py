#!/usr/bin/env python3
"""Validate the generated native Android corpus before packaging it."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_ASSETS = ROOT / ".work" / "native_content" / "generated_assets"

ALLOWED_LATIN = {
    "vw", "volkswagen", "golf", "bora", "jetta", "haynes",
    "sohc", "dohc", "abs", "ecu", "egr", "obd", "mot", "tdi", "gti",
    "bosch", "lucas", "girling", "teves", "motronic", "digifant", "simos",
    "pierburg", "monomotronic", "airbag", "torx", "pozi", "philips",
    "longlife", "highline", "climatronic", "mark", "magneti-marelli",
    "molykote", "loctite", "macpherson", "ford", "plastigage", "nox",
    "ppm", "out", "oben", "top", "ptfe", "ron", "ngk", "mpi",
    "nm", "rpm", "lbf", "ft", "mm", "cm", "km", "mph", "psi", "bar",
    "kw", "bhp", "cc", "ah", "v", "ma", "amp", "amps", "dc", "ac",
    "min", "max", "ref", "diag", "api", "sae", "din", "iso", "dot",
}

UPPERCASE_WORDS = {
    "WARNING", "CAUTION", "NOTE", "FUEL", "OIL", "ENGINE", "FRONT", "REAR",
    "LEFT", "RIGHT", "TOP", "BOTTOM", "ON", "OFF", "IN", "OUT", "OPEN",
    "CLOSE", "DO", "NOT", "USE", "ALL", "GENERAL", "CONTENTS", "INDEX",
}

LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]{1,}")


def is_allowed_token(token: str) -> bool:
    if token.casefold() in ALLOWED_LATIN:
        return True
    if token.isupper() and 2 <= len(token) <= 5 and token not in UPPERCASE_WORDS:
        return True
    if re.fullmatch(r"[A-Z]{1,4}\d[A-Z0-9]*", token):
        return True
    return False


def audit(assets: Path) -> tuple[dict[str, int], list[str]]:
    index_path = assets / "content_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    stats = {
        "sections": 0,
        "blocks": 0,
        "text_blocks": 0,
        "image_blocks": 0,
        "russian_characters": 0,
        "suspicious_texts": 0,
    }
    referenced_assets: set[str] = set()

    for section in index.get("sections", []):
        stats["sections"] += 1
        slug = section["slug"]
        article_path = assets / "articles" / f"{slug}.json"
        if not article_path.is_file():
            problems.append(f"missing article: {slug}")
            continue
        article = json.loads(article_path.read_text(encoding="utf-8"))
        for number, block in enumerate(article.get("blocks", []), 1):
            stats["blocks"] += 1
            if block.get("type") == "image":
                stats["image_blocks"] += 1
                asset = block.get("asset", "")
                referenced_assets.add(asset)
                if not (assets / asset).is_file():
                    problems.append(f"missing image: {slug} block {number}: {asset}")
                continue

            stats["text_blocks"] += 1
            text = str(block.get("text", ""))
            stats["russian_characters"] += len(re.findall(r"[А-Яа-яЁё]", text))
            if "�" in text or "вЂ" in text or "п¬" in text or "Рџ" in text:
                problems.append(f"broken encoding: {slug} block {number}: {text[:140]}")
            bad_tokens = [token for token in LATIN_TOKEN_RE.findall(text) if not is_allowed_token(token)]
            if bad_tokens:
                stats["suspicious_texts"] += 1
                problems.append(
                    f"latin text: {slug} block {number} ({', '.join(bad_tokens[:8])}): {text[:180]}"
                )

    actual_assets = {f"media/{path.name}" for path in (assets / "media").glob("*.webp")}
    for asset in sorted(actual_assets - referenced_assets):
        problems.append(f"orphan image: {asset}")
    return stats, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--show", type=int, default=80)
    args = parser.parse_args()

    stats, problems = audit(args.assets)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"problems: {len(problems)}")
    for problem in problems[: args.show]:
        print(f"- {problem}")
    if len(problems) > args.show:
        print(f"... and {len(problems) - args.show} more")
    return 1 if args.strict and problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
