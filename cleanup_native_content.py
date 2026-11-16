#!/usr/bin/env python3
"""Remove untranslated OCR debris while preserving meaningful Russian text."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from audit_native_content import is_allowed_token


ROOT = Path(__file__).resolve().parent
DEFAULT_ASSETS = ROOT / ".work" / "native_content" / "generated_assets"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]{1,}")

KNOWN_TERMS = {
    "hatchback": "хэтчбек",
    "estate": "универсал",
    "saloon": "седан",
    "underbonnet": "подкапотное пространство",
    "underbonner": "подкапотное пространство",
    "wiper": "стеклоочиститель",
    "wipers": "стеклоочистители",
    "maintenance": "техническое обслуживание",
    "gearbox": "коробка передач",
    "engine": "двигатель",
    "engines": "двигатели",
    "wheel": "колесо",
    "wheels": "колёса",
    "front": "передний",
    "rear": "задний",
    "left": "левый",
    "right": "правый",
    "body": "кузов",
    "fuel": "топливо",
    "diesel": "дизель",
    "petrol": "бензин",
    "oil": "масло",
    "level": "уровень",
    "warning": "предупреждение",
    "caution": "внимание",
    "note": "примечание",
    "general": "общие сведения",
    "contents": "содержание",
    "index": "указатель",
    "open": "открыть",
    "close": "закрыть",
    "before": "перед",
    "after": "после",
    "remove": "снимите",
    "refit": "установите",
    "removal": "снятие",
    "refitting": "установка",
    "setting": "регулировка",
    "settings": "параметры",
    "checking": "проверка",
    "automatic": "автоматическая",
    "manual": "механическая",
    "transmission": "коробка передач",
    "models": "модели",
    "model": "модель",
    "part": "часть",
    "continued": "продолжение",
    "service": "обслуживание",
    "repair": "ремонт",
    "safety": "безопасность",
    "advanced": "расширенный",
    "driver": "водитель",
    "road": "дорога",
    "high": "высокий",
    "low": "низкий",
    "on": "вкл.",
    "off": "выкл.",
}


def clean_text(text: str) -> tuple[str, int, int]:
    text = html.unescape(text).replace("\u00ad", "")
    replaced = 0
    removed = 0

    def substitute(match: re.Match[str]) -> str:
        nonlocal replaced, removed
        token = match.group(0)
        if is_allowed_token(token):
            return token
        known = KNOWN_TERMS.get(token.casefold())
        if known is not None:
            replaced += 1
            return known
        removed += 1
        return ""

    text = TOKEN_RE.sub(substitute, text)
    # Remove OCR punctuation left behind by deleted fragments without touching
    # workshop notation such as (+), (-), 10.5:1 or 90°.
    text = re.sub(r"\b[А-Яа-яЁё]\.(?=[А-Яа-яЁё])", "", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?:\s*[,.!?]){1,}", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\[\s*\]", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" .,_-/")
    if text:
        text = text[0].upper() + text[1:]
    return text, replaced, removed


def cleanup(assets: Path) -> dict[str, int]:
    stats = {
        "known_terms_replaced": 0,
        "ocr_fragments_removed": 0,
        "blocks_removed": 0,
        "frontmatter_blocks_removed": 0,
        "articles_changed": 0,
    }
    counts: dict[str, tuple[int, int]] = {}
    for path in sorted((assets / "articles").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        output: list[dict[str, object]] = []
        changed = False
        for block in payload.get("blocks", []):
            page = int(block.get("page", 0))
            if path.stem == "about" and page <= 7:
                stats["frontmatter_blocks_removed"] += 1
                changed = True
                continue
            if block.get("type") == "image":
                output.append(block)
                continue
            original = str(block.get("text", ""))
            cleaned, replaced, removed = clean_text(original)
            stats["known_terms_replaced"] += replaced
            stats["ocr_fragments_removed"] += removed
            had_cleanup = replaced > 0 or removed > 0 or cleaned != original
            cyrillic = len(re.findall(r"[А-Яа-яЁё]", cleaned))
            meaningful = len(re.findall(r"[А-Яа-яЁёA-Za-z0-9]", cleaned))
            if not cleaned or meaningful < 2 or (had_cleanup and cyrillic < 3 and not re.search(r"\d", cleaned)):
                stats["blocks_removed"] += 1
                changed = True
                continue
            if cleaned != original:
                block["text"] = cleaned
                changed = True
            output.append(block)
        payload["blocks"] = output
        counts[path.stem] = (
            len(output),
            sum(block.get("type") == "image" for block in output),
        )
        if changed:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            stats["articles_changed"] += 1

    index_path = assets / "content_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for section in index.get("sections", []):
        count = counts.get(str(section.get("slug", "")))
        if count is not None:
            section["blockCount"], section["imageCount"] = count
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    args = parser.parse_args()
    print(json.dumps(cleanup(args.assets), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
