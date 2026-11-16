"""Source-aware repair of running headers, numbering and missing pages."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pymupdf

from rebuild_native_text import extract_pdf_lines, normalise_source
from reviewed_automatic_transmission import blocks as automatic_blocks
from reviewed_missing_pages import blocks as missing_blocks
from restore_manual_images import MANUAL, BFQ
from translate_haynes import DEFAULT_INPUT

ROOT = Path(__file__).resolve().parent
PAGE_CODE = r"\d{1,2}[ABCD]?[e•·]\d{1,2}"
EMISSION_HEADER = re.compile(
    rf"(?:{PAGE_CODE}\s+)?Emission control and exhaust systems [—–-] "
    rf"(?:diesel|petrol) engines(?:\s+{PAGE_CODE})?", re.I)
EMISSION_RU = re.compile(
    r"(?:[Сс]истем\w* контроля выбросов и (?:выхлоп\w*|выпускн\w*)(?: систем\w*)?|"
    r"[Кк]онтроль выбросов и выхлопные системы) [—–-] (?:дизельные|бензиновые) двигатели")
NUMBER = re.compile(r"^(\d{1,3})(?:[.)])?\s+")
FIGURE = re.compile(r"^(\d{1,2}\.\d{1,2}[a-z]?)(?=\s)")


def strip_header(block: dict, headers: list[str]) -> dict | None:
    source = block.get("source", "")
    if not source:
        return block
    original = source
    for header in sorted(headers, key=len, reverse=True):
        if len(header) < 7:
            continue
        source = re.sub(re.escape(header), "", source, flags=re.I).strip()
    source = EMISSION_HEADER.sub("", source).strip()
    if source == original:
        return block
    # Noise left by the scan's page rule is not article content.
    if not source or re.fullmatch(r"[A-Z a-z_—-]{0,12}", source) and source.lower() in {"oo errr", ""}:
        return None
    result = dict(block)
    result["source"] = source
    if EMISSION_HEADER.search(original):
        result["text"] = EMISSION_RU.sub("", result.get("text", "")).strip()
        result["text"] = re.sub(r"\s+([,.])", r"\1", result["text"])
    return result


def repair_number(block: dict) -> dict:
    result = dict(block)
    if block.get("translationPart", 0):
        return result
    source, text = str(block.get("source", "")), str(block.get("text", ""))
    # Two scan artifacts: the leading mark is not a hundreds digit.
    for wrong, right in (("413.30", "13.30"), ("418.26", "18.26")):
        if source.startswith(wrong + " "):
            source = right + source[len(wrong):]
            text = re.sub(r"^" + re.escape(wrong), right, text)
            result["source"] = source
    fig = FIGURE.match(source)
    if fig and not re.match(r"^\d+\.\d+\s+(?:litre|mm|to|and|&|bar|V|kW|amps)", source, re.I):
        # Treat decimal engine sizes and measured values as quantities.
        if block.get("type") == "caption" or re.search(r"\b(?:arrowed|Removing|Remove|Undo|Disconnect|location|Securing)\b", source):
            label = fig[1]
            prefix = re.match(r"^\d+(?:[.,]\d+)?[a-zа-я]?[.)]?\s+", text)
            if prefix:
                text = label + " " + text[prefix.end():]
            elif not re.search(r"\b" + re.escape(label) + r"\b", text):
                text = label + " " + text
    elif re.match(r"^\d{1,3}\s+[A-Z]", source):
        source_number = NUMBER.match(source)
        translated_number = NUMBER.match(text)
        if source_number and (not translated_number or source_number[1] != translated_number[1]):
            text = source_number[1] + " " + (text[translated_number.end():] if translated_number else text)
    result["text"] = re.sub(r"\b([А-Яа-яЁё]{3,})/\1\b", r"\1", text, flags=re.I)
    return result


def split_steps(block: dict) -> list[dict]:
    """Split only matching sequential numbered sentences in source and text.

    A figure legend, a measurement, or a translated fragment is left intact.
    Original numbers are never replaced with an invented continuous sequence.
    """
    if block.get("type") != "text" or block.get("translationPart") or block.get("curated"):
        return [block]
    source = block.get("source", "")
    text = block.get("text", "")
    pattern = r"(?:^|(?<=[.!?])\s+)(\d{1,3})[.)]?\s+(?=[A-ZА-ЯЁ])"
    sm, tm = list(re.finditer(pattern, source)), list(re.finditer(pattern, text))
    nums = [int(m[1]) for m in sm]
    if len(nums) < 2 or not sm[0].start() == 0 or nums != [int(m[1]) for m in tm]:
        return [block]
    if nums != list(range(nums[0], nums[0] + len(nums))):
        return [block]
    result = []
    for i in range(len(nums)):
        item = dict(block)
        item["source"] = source[sm[i].start(): sm[i + 1].start() if i + 1 < len(sm) else None].strip()
        item["text"] = text[tm[i].start(): tm[i + 1].start() if i + 1 < len(tm) else None].strip()
        result.append(item)
    return result


def repair() -> dict:
    stats = Counter()
    details = []
    headers, headings = {}, {}
    recovered_blocks = missing_blocks()
    number_fixes = json.loads((ROOT / "reviewed_numbering.json").read_text(encoding="utf-8"))
    with pymupdf.open(DEFAULT_INPUT) as pdf:
        for number in range(1, len(pdf) + 1):
            if 348 <= number <= 356:
                # Wiring sheets use a separate Russian source and have no
                # prose headers to repair (their OCR contains thousands of labels).
                continue
            page = pdf[number - 1]
            header_lines = []
            raw = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
            for b in raw["blocks"]:
                for line in b.get("lines", []):
                    if line["bbox"][3] <= 32:
                        header_lines.append(normalise_source(" ".join(s["text"] for s in line["spans"])))
            headers[number] = header_lines
            headings[number] = [l.text for l in extract_pdf_lines(page)
                                if re.match(r"^\d{1,2} [A-Z]", l.text) and l.font_size >= 8.1]
        for root in (MANUAL, BFQ):
            index = json.loads((root / "content_index.json").read_text(encoding="utf-8"))
            for section in index["sections"]:
                path = root / "articles" / f"{section['slug']}.json"
                article = json.loads(path.read_text(encoding="utf-8"))
                original = article["blocks"]
                result = []
                for b in original:
                    for correction in number_fixes:
                        if (article["slug"], b.get("page"), b.get("source")) == (correction["slug"], correction["page"], correction["source"]):
                            b = dict(b)
                            b["sourceOcr"] = b["source"]
                            b["source"] = re.sub(r"^\d+", str(correction["number"]), b["source"])
                            b["text"] = re.sub(r"^\d+", str(correction["number"]), b["text"])
                            b["curated"] = True
                            stats["source_paragraph_numbers_reviewed"] += 1
                    if article["slug"] == "engine_dohc" and b.get("page") == 98:
                        if b.get("source") == "12 Rockers and tappets (1.4 and":
                            b = dict(b, type="heading", curated=True,
                                     text="12 Коромысла и толкатели (двигатели 1,4 и 1,6 л) — снятие, проверка и установка")
                        elif b.get("source") == "1.6 litre engines) - removal, inspection and refitting Removal":
                            b = dict(b, type="heading", curated=True, text="Снятие")
                    if b["type"] == "image" or b.get("curated"):
                        result.append(b)
                        continue
                    page = b.get("page", 0)
                    cleaned = strip_header(b, headers.get(page, []))
                    if cleaned != b:
                        stats["running_headers_removed"] += 1
                        details.append({"article": section["slug"], "page": page, "headerSource": b.get("source", "")})
                    if cleaned is None:
                        continue
                    fixed = repair_number(cleaned)
                    if fixed != cleaned:
                        stats["number_or_repetition_repairs"] += 1
                    source = fixed.get("source", "")
                    if any(source.startswith(h) for h in headings.get(page, [])) and len(source) < 220:
                        if fixed["type"] != "heading":
                            stats["procedure_headings_restored"] += 1
                        fixed["type"] = "heading"
                    parts = split_steps(fixed)
                    stats["paragraphs_separated"] += len(parts) - 1
                    result.extend(parts)
                if root == MANUAL and article["slug"] == "automatic_transmission":
                    result = [b for b in original if b.get("page", 0) == 0]
                    result.extend(automatic_blocks())
                    for number in (253, 255):
                        result.append({"type": "image", "page": number, "curated": True,
                                       "asset": f"media/source/haynes_{number:04d}.webp",
                                       "description": f"Полная страница {number} оригинала (на английском языке)"})
                    for number in (254, 256):
                        for b in original:
                            if b["type"] == "image" and b.get("page") == number:
                                result.append(b)
                    # Put figures after their source-page prose, retaining all
                    # original figure IDs and translated legends below.
                    result.sort(key=lambda b: b.get("page", 0))
                    for b in result:
                        if b.get("asset", "").endswith("0254_01.webp"):
                            b["description"] = "Рисунок 2.8. Разъёмы АКПП: 1 — электромагнитные клапаны; 2 — датчик скорости автомобиля; 3 — многофункциональный выключатель; 4 — датчик частоты вращения АКПП."
                        elif b.get("asset", "").endswith("0254_03.webp"):
                            b["description"] = "Рисунок 2.11. Трос селектора: 1 — трос; 2 — гайка; 3 — стопорное кольцо; 4 — рычаг селектора."
                        elif b.get("page") == 256 and b["type"] == "image":
                            b["description"] = "Рисунок 4.7. Механизм рычага селектора и тросы. Полная схема с позициями 1–45."
                    stats["automatic_transmission_reviewed_blocks"] = len(result)
                if root == MANUAL and article["slug"] not in {"about", "wiring", "index"}:
                    for number in range(article["startPage"], article["endPage"] + 1):
                        if any(b.get("page") == number and b["type"] != "image" for b in result):
                            continue
                        additions = [b for b in recovered_blocks if b["page"] == number]
                        if additions:
                            result.extend(additions)
                            stats["procedure_pages_recovered"] += 1
                            stats["procedure_blocks_recovered"] += len(additions)
                        source_asset = f"media/source/haynes_{number:04d}.webp"
                        if (root / source_asset).exists():
                            result.extend([
                                {"type": "note", "page": number, "curated": True,
                                 "text": f"Страница {number} оригинала: таблицы, технические данные и исходная нумерация. Текст изображения — на английском языке."},
                                {"type": "image", "page": number, "asset": source_asset,
                                 "curated": True, "description": f"Полная страница {number} оригинального руководства"},
                            ])
                            stats["omitted_source_pages_restored"] += 1
                    result.sort(key=lambda b: b.get("page", 0))
                article["blocks"] = result
                path.write_text(json.dumps(article, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                section["blockCount"] = len(result)
                section["imageCount"] = sum(b["type"] == "image" for b in result)
            (root / "content_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = ROOT / "content_integrity_report.json"
    if report_path.exists():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        for key, count in previous.get("stats", {}).items():
            if key == "automatic_transmission_reviewed_blocks":
                continue
            stats[key] += count
        details = previous.get("headerRepairs", []) + details
    report = {"stats": dict(stats), "headerRepairs": details}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report["stats"]


if __name__ == "__main__":
    print(json.dumps(repair(), ensure_ascii=False, indent=2))
