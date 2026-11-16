#!/usr/bin/env python3
"""Find Russian wording in app articles that is absent from the reference manual.

This is a heuristic editorial report rather than a pass/fail validator.  A word
missing from the reference is not automatically wrong, but frequent outliers
are a useful way to expose literal machine translations and OCR inventions.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_ASSETS = ROOT / ".work" / "native_content" / "polished_assets"
DEFAULT_REFERENCE = ROOT / ".work" / "ru_reference_corpus.txt"
WORD_RE = re.compile(r"[А-Яа-яЁё]{4,}")


def words(text: str) -> list[str]:
    return [value.casefold().replace("ё", "е") for value in WORD_RE.findall(text)]


def article_text(assets: Path) -> str:
    parts: list[str] = []
    for path in sorted((assets / "articles").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        parts.extend(
            str(block.get("text", ""))
            for block in payload.get("blocks", [])
            if block.get("type") != "image"
        )
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--minimum", type=int, default=3)
    parser.add_argument("--show", type=int, default=180)
    parser.add_argument("--word", action="append", default=[], help="show block contexts for this word or phrase")
    args = parser.parse_args()

    if args.word:
        remaining = args.show
        for path in sorted((args.assets / "articles").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for block in payload.get("blocks", []):
                if block.get("type") == "image":
                    continue
                text = str(block.get("text", ""))
                if any(value.casefold() in text.casefold() for value in args.word):
                    print(f"{path.stem}:p{block.get('page', 0)}: {text[:520]}")
                    remaining -= 1
                    if remaining <= 0:
                        return 0
        return 0

    reference = set(words(args.reference.read_text(encoding="utf-8")))
    app_counts = Counter(words(article_text(args.assets)))
    outliers = [
        (word, count)
        for word, count in app_counts.most_common()
        if count >= args.minimum and word not in reference
    ]
    print(
        json.dumps(
            {
                "app_word_forms": len(app_counts),
                "reference_word_forms": len(reference),
                "frequent_outliers": len(outliers),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    for word, count in outliers[: args.show]:
        print(f"{count:5}  {word}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
