"""Validate the native BFQ Android asset corpus."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "android-bfq" / "app" / "src" / "main" / "assets"
ALLOWED_TYPES = {"heading", "text", "note", "caption", "image"}
ENGLISH_WORDS = re.compile(
    r"\b(?:the|and|with|from|remove|removal|refit|refitting|engine|bolt|warning|"
    r"chapter|section|system|general|information|fuel|timing|camshaft|cylinder|"
    r"coolant|pressure|inspection)\b",
    re.IGNORECASE,
)


def main() -> None:
    problems: list[str] = []
    index = json.loads((ASSETS / "content_index.json").read_text(encoding="utf-8"))
    sections = index.get("sections", [])
    referenced: set[str] = set()
    block_count = 0
    image_count = 0
    russian_characters = 0
    suspicious: list[str] = []

    for section in sections:
        slug = str(section.get("slug", ""))
        article_path = ASSETS / "articles" / f"{slug}.json"
        if not article_path.is_file():
            problems.append(f"missing article: {slug}")
            continue
        article = json.loads(article_path.read_text(encoding="utf-8"))
        if article.get("slug") != slug:
            problems.append(f"slug mismatch: {slug}")
        blocks = article.get("blocks", [])
        block_count += len(blocks)
        actual_images = 0
        for position, block in enumerate(blocks):
            block_type = block.get("type")
            if block_type not in ALLOWED_TYPES:
                problems.append(f"{slug}:{position}: invalid type {block_type!r}")
                continue
            if block_type == "image":
                asset = str(block.get("asset", ""))
                actual_images += 1
                image_count += 1
                referenced.add(asset)
                if not (ASSETS / asset).is_file():
                    problems.append(f"{slug}:{position}: missing {asset}")
            else:
                value = str(block.get("text", "")).strip()
                if not value:
                    problems.append(f"{slug}:{position}: empty text")
                    continue
                russian_characters += len(re.findall(r"[А-Яа-яЁё]", value))
                if ENGLISH_WORDS.search(value):
                    suspicious.append(f"{slug}:{position}: {value}")
                if any(marker in value for marker in ("&Апо;", "�", "Ã", "Â")):
                    problems.append(f"{slug}:{position}: encoding/OCR artifact")
        if section.get("blockCount") != len(blocks):
            problems.append(f"{slug}: block count mismatch")
        if section.get("imageCount") != actual_images:
            problems.append(f"{slug}: image count mismatch")

    media = {f"media/{path.name}" for path in (ASSETS / "media").glob("*") if path.is_file()}
    for orphan in sorted(media - referenced):
        problems.append(f"orphan media: {orphan}")
    pdfs = list(ASSETS.rglob("*.pdf"))
    if pdfs:
        problems.extend(f"unexpected PDF: {path}" for path in pdfs)
    if suspicious:
        problems.extend(f"suspicious English: {value}" for value in suspicious)

    summary = {
        "sections": len(sections),
        "blocks": block_count,
        "image_blocks": image_count,
        "unique_media": len(media),
        "russian_characters": russian_characters,
        "suspicious_english": len(suspicious),
        "problems": len(problems),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if problems:
        print("\n".join(problems[:100]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
