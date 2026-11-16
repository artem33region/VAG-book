#!/usr/bin/env python3
"""Translate the Haynes scan to Russian while keeping the original page artwork.

The source PDF contains full-page scans plus an OCR text layer.  This script uses
the OCR coordinates to cover English text areas and typeset Russian text in the
same rectangles.  Translations are cached in SQLite, so a stopped run resumes
without retranslating completed fragments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import ctranslate2
import numpy as np
import pymupdf
import sentencepiece as spm

from reference_terminology import enhance_translation


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "Haynes_VW_Golf_&_Bora_Service_and_Repair_Manual_A_K_Legg,_Peter.pdf"
DEFAULT_MODEL = ROOT / ".models" / "quickmt-en-ru"
DEFAULT_CACHE = ROOT / ".work" / "translations.sqlite3"
FONT_REGULAR = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")
FONT_ITALIC = Path(r"C:\Windows\Fonts\ariali.ttf")
WINDOWS_OCR_SCRIPT = ROOT / "windows_ocr.ps1"


# Reword British workshop-manual idioms before translation.  The substitutions
# deliberately stay in English so that the translation model can inflect the
# Russian sentence instead of copying rigid glossary placeholders.
SOURCE_REWRITES: tuple[tuple[str, str], ...] = (
    (r"\bbleed the\b", "remove air from the"),
    (r"\bbolts securing\b", "bolts used to fasten"),
    (r"\bin-car repair procedures\b", "repair procedures with the engine installed in the car"),
    (r"\bdiesel engine fuel system\b", "fuel system of the diesel engine"),
    (r"\bpetrol engine fuel system\b", "fuel system of the petrol engine"),
    (r"\bslacken\b", "loosen"),
    (r"\bwithdraw\b", "remove"),
    (r"\brenewal\b", "replacement"),
    (r"\brenew\b", "replace"),
    (r"\brefitting\b", "reinstallation"),
    (r"\brefit\b", "reinstall"),
    (r"\broadwheels?\b", "wheels"),
    (r"\bworm-drive (?:hose )?(?:clips?|clamps?)\b", "worm screw clamps"),
    (r"\bfiller neck\b", "fuel tank filling pipe"),
    (r"\binjection pump\b", "high-pressure fuel pump"),
    (r"\btrack rod end\b", "steering rod end"),
    (r"\btrack rod\b", "steering rod"),
    (r"\binner wing\b", "inner fender"),
    (r"\bballjoint\b", "ball joint"),
    (r"\bwishbone\b", "suspension control arm"),
    (r"\bdriveshaft\b", "drive shaft"),
    (r"\bsump\b", "engine oil pan"),
    (r"\bearth lead\b", "electrical ground wire"),
    (r"\bearth point\b", "electrical ground point"),
    (r"\bengine speed\b", "engine rpm"),
    (r"\bcranking\b", "starter operation"),
)


# Deterministic post-editing for recurring automotive mistranslations observed
# on representative pages.  Keep these rules conservative: a wrong replacement
# in a repair instruction is worse than slightly wooden Russian.
POST_EDITS: tuple[tuple[str, str], ...] = (
    (r"\bDOHC процедур\w* ремонта бензинового двигателя в автомобиле\b", "DOHC: ремонт бензинового двигателя без снятия с автомобиля"),
    (r"\bSOHC процедур\w* ремонта бензинового двигателя в автомобиле\b", "SOHC: ремонт бензинового двигателя без снятия с автомобиля"),
    (r"\bдиаграмм(?:ы|а) проводки\b", "электрические схемы"),
    (r"\bуглы выравнивания колес и поворота руля\s*[-—]\s*общая информация\b", "углы установки колёс и рулевого управления — общие сведения"),
    (r"\bручн(?:ой|ого|ому|ым|ом) тормоз(?:а|у|ом|е)?\b", "стояночный тормоз"),
    (r"\bпарковочн(?:ый|ого|ому|ым|ом) тормоз(?:а|у|ом|е)?\b", "стояночный тормоз"),
    (r"\b(?:нанесите|приложите) стояночный тормоз\b", "включите стояночный тормоз"),
    (r"\b(?:расслабьте|освободите)\b", "ослабьте"),
    (r"\bи удалите (?=(?:\w+\s+){0,3}болт)", "и снимите "),
    (r"\bболт(ы|а|ов),? используем\w* для крепления\b", r"болт\1 крепления"),
    (r"\b(?:стойках оси|стендах оси|защитных стендах|стойках поддержки безопасности)\b", "страховочных опорах"),
    (r"\bзащитн(?:ые|ых|ым|ыми) стойк(?:и|ах|ам|ами)\b", "страховочные опоры"),
    (r"\b(?:насос(?:а|у|ом|е)? для впрыска|насос(?:а|у|ом|е)? впрыска|впрыскивающ\w* насос(?:а|у|ом|е)?|насос(?:а|у|ом|е)? дизельного впрыска|топливн\w* насос(?:а|у|ом|е)? высокого давления)\b", "ТНВД"),
    (r"\bвалов(?:ая|ой|ую|ою) ос[ьи]\b", "распределительный вал"),
    (r"\b(?:переменн\w* времен\w* клапан\w*|изменяем\w* срок\w* подачи клапан\w*)\b", "изменяемыми фазами газораспределения"),
    (r"\bпеременн\w* времен\w* распределения газа\b", "изменяемыми фазами газораспределения"),
    (r"\bпеременн\w* фаз\w* клапан\w*\b", "изменяемыми фазами газораспределения"),
    (r"\bизменяем\w* времен\w* клапан\w*\b", "изменяемыми фазами газораспределения"),
    (r"\bше(?:я|ю|е|и) (?:топливного )?наполнителя(?: топливного бака)?\b", "заливная горловина топливного бака"),
    (r"\bтрубу (?:наполнения|заправки) топливного бака\b", "заливную горловину топливного бака"),
    (r"\bтруба (?:наполнения|заправки) топливного бака\b", "заливная горловина топливного бака"),
    (r"\bтрубы (?:наполнения|заправки) топливного бака\b", "заливной горловины топливного бака"),
    (r"\bтрубе (?:наполнения|заправки) топливного бака\b", "заливной горловине топливного бака"),
    (r"\bчервячн\w* зажим(?:ы|ов|ами)?\b", "червячные хомуты"),
    (r"\bшлангов(?:ые|ых|ыми) зажим(?:ы|ов|ами)?\b", "хомуты шлангов"),
    (r"\bобрезанн(?:ые|ых|ыми) лини(?:и|й|ями)\b", "перегнутые трубопроводы"),
    (r"\bвентиляционн(?:ые|ых|ыми) труб(?:ы|ок|ами)\b", "вентиляционные трубки"),
    (r"\b(?:шея|шею|шее) и бак наполнителя топливного бака\b", "заливная горловина и топливный бак"),
    (r"\bрулев(?:ая|ой|ую) арк(?:а|и|у|ой)\b", "колёсная арка"),
    (r"\bбензинов(?:ый|ого|ому|ым|ом) резервуар(?:а|у|ом|е)?\b", "топливный бак"),
    (r"\bтопливн(?:ый|ого|ому|ым|ом) резервуар(?:а|у|ом|е)?\b", "топливный бак"),
    (r"\bхолодильник(?:а|у|ом|е)? автоматической передачи\b", "радиатор охлаждения автоматической коробки передач"),
    (r"\bавтоматическ(?:ая|ой|ую) передач(?:а|и|у|ей)\b", "автоматическая коробка передач"),
    (r"\bнедействительн(?:ом|ое|ого) состояни(?:и|е|я)\b", "на холостом ходу"),
    (r"\bзапустите и запустите двигатель\b", "запустите двигатель"),
    (r"\bпереустановите\b", "установите обратно"),
    (r"\bпереустановка\b", "установка"),
    (r"\bвозобновление топливного фильтра\b", "замена топливного фильтра"),
    (r"\bобновляйте компонент\b", "замените компонент"),
    (r"\bотверсти(?:е|я) закрепления\b", "крепёжный винт"),
    (r"\bподъемн\w* стойк\w* закрепления\b", "крепёжный кронштейн"),
    (r"\bуправляющ(?:ий|его|ему|им|ем) клапан(?:а|у|ом|е)?\b", "регулирующий клапан"),
    (r"\bконтрольн(?:ый|ого|ому|ым|ом) клапан(?:а|у|ом|е)?\b", "регулирующий клапан"),
    (r"\bремонтируйте регулирующий клапан\b", "установите регулирующий клапан"),
    (r"\bотпустите клип\b", "снимите фиксатор"),
    (r"\bверхн(?:ей|юю) част(?:и|ь) фильтровочн(?:ого|ый) блок(?:а|)\b", "верхнюю часть корпуса фильтра"),
    (r"\bшланги подачи и доставки топлива\b", "подающий и отводящий топливные шланги"),
    (r"\bкровотечение гидравлической системы рулевого управления\b", "удалите воздух из гидросистемы усилителя рулевого управления"),
    (r"\bTrack rod end\b", "наконечник рулевой тяги"),
    (r"\btie-rod конец\b", "наконечник рулевой тяги"),
    (r"\bкон(?:ец|ца|цу|цом|це) рулевого стержня\b", "наконечник рулевой тяги"),
    (r"\bнаконечник рулевой тяги от рулевого колеса\b", "наконечник рулевой тяги от рулевой тяги"),
    (r"\bкон(?:ец|ца|цу|цом|це) поворота рулевого шнура\b", "наконечник рулевой тяги"),
    (r"\bкон(?:ец|ца|цу|цом|це) стержня трека\b", "наконечник рулевой тяги"),
    (r"\bкон(?:ец|ца|цу|цом|це) трекового стержня\b", "наконечник рулевой тяги"),
    (r"\b(?:путев(?:ой|ого|ому|ым|ом)|рулев(?:ой|ого|ому|ым|ом)) стержн(?:я|ю|ем|е)?\b", "рулевая тяга"),
    (r"\bстерж(?:ень|ня|ню|нем|не) трека\b", "рулевая тяга"),
    (r"\bтреков(?:ый|ого|ому|ым|ом) стерж(?:ень|ня|ню|нем|не)\b", "рулевая тяга"),
    (r"\b(?:путев(?:ая|ой|ую)|рулев(?:ая|ой|ую)) штанг(?:а|и|у|ой)\b", "рулевая тяга"),
    (r"\bрулев(?:ой|ого|ому|ым|ом) шнур(?:а|у|ом|е)?\b", "рулевая тяга"),
    (r"\bзамков(?:ый|ого|ому|ым|ом) орех(?:а|у|ом|е)?\b", "контргайка"),
    (r"\bшаров(?:ой|ого|ому|ым|ом) сустав(?:а|у|ом|е)?\b", "шаровой шарнир"),
    (r"\bшаров(?:ой|ого|ому|ым|ом) шов(?:а|у|ом|е)?\b", "шаровой шарнир"),
    (r"\bсепаратор(?:а|у|ом|е)? шарового соединения\b", "съёмник шаровых шарниров"),
    (r"\bключ(?:ом|а|у|е)? Аллена\b", "шестигранный ключ"),
    (r"\bСплит коллеты\b", "сухари клапана"),
    (r"\bраздельн(?:ые|ых|ыми) коллет(?:ы|ов|ами)\b", "сухари клапана"),
    (r"\bгидравлическ(?:ие|их|ими) толкател(?:и|ей|ями)\b", "гидрокомпенсаторы"),
    (r"\bToe\b", "схождение"),
    (r"\bКамбер\b", "развал"),
    (r"\bкамбер\b", "развал"),
    (r"\bкастор\b", "продольный наклон оси поворота"),
    (r"\bтранспортн(?:ое|ого|ому|ым|ом) средств(?:о|а|у|ом|е)\b", "автомобиль"),
    (r"\bподдержите (?:его|её) на страховочных опорах\b", "установите автомобиль на страховочные опоры"),
    (r"\bподнимите переднюю часть автомобиля и установите автомобиль\b", "поднимите переднюю часть автомобиля и установите его"),
    (r"\bоткрутите наконечник рулевой тяги\b", "отверните наконечник рулевой тяги"),
)


EXACT_TRANSLATIONS: dict[str, str] = {
    "Definitions": "Определения",
    "Removal": "Снятие",
    "Refitting": "Установка",
    "Reinstallation": "Установка",
    "Replacement": "Замена",
    "Dismantling": "Разборка",
    "Reassembly": "Сборка",
    "General information": "Общие сведения",
    "Wire colours": "Цвета проводов",
    "Key to items": "Обозначения элементов",
    "Wiring diagrams": "Электрические схемы",
}


OCR_FIXES: tuple[tuple[str, str], ...] = (
    (r"\bconferming\b", "conforming"),
    (r"\bUk\b", "UK"),
    (r"(?<!\w)/t\b", "It"),
    (r"\bO00\b", "000"),
    (r"\s+\b(?:WHC|WHY)\b\s*$", ""),
)


@dataclass(frozen=True)
class TextBlock:
    page_index: int
    rect: pymupdf.Rect
    source: str
    font_size: float
    bold: bool
    italic: bool


def clean_ocr_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"([A-Za-z])-\s*\n\s*([a-z])", r"\1\2", text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    for pattern, replacement in OCR_FIXES:
        text = re.sub(pattern, replacement, text)
    return text


def rewrite_source(text: str) -> str:
    result = text
    for pattern, replacement in SOURCE_REWRITES:
        def preserve_initial_case(match: re.Match[str]) -> str:
            if match.group(0)[:1].isupper():
                return replacement[:1].upper() + replacement[1:]
            return replacement

        result = re.sub(pattern, preserve_initial_case, result, flags=re.IGNORECASE)
    return result


def post_edit(text: str) -> str:
    result = text.strip()
    for pattern, replacement in POST_EDITS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    result = re.sub(r"\s{2,}", " ", result)
    if result:
        result = result[0].upper() + result[1:]
    return result


def split_translation_units(text: str, max_chars: int = 320) -> list[str]:
    """Split OCR blocks into short, sentence-like translation units."""
    text = clean_ocr_text(text)
    # Boundaries before numbered workshop steps are as important as punctuation.
    pieces = re.split(
        r"(?<=[.!?])\s+(?=(?:\d+\s+)?[A-Z])|(?<=\.)\s+(?=\d+\s+[A-Z])|\s+(?=\d{1,2}\s+[A-Z][a-z])",
        text,
    )
    pieces = [piece.strip() for piece in pieces if piece.strip()]

    output: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current} {piece}".strip()
        if current and len(candidate) > max_chars:
            output.append(current)
            current = piece
        else:
            current = candidate
    if current:
        output.append(current)

    # OCR occasionally produces a paragraph with no punctuation.  Split such a
    # run at the nearest comma or word boundary rather than truncating it.
    final: list[str] = []
    for unit in output:
        while len(unit) > max_chars:
            cut = unit.rfind(", ", 0, max_chars)
            if cut < max_chars // 2:
                cut = unit.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            final.append(unit[:cut].strip())
            unit = unit[cut:].lstrip(" ,")
        if unit:
            final.append(unit)
    return final


def block_is_meaningful(text: str, rect: pymupdf.Rect, page_index: int) -> bool:
    letters = re.findall(r"[A-Za-z]", text)
    words = re.findall(r"[A-Za-z]+", text)
    if len(letters) < 3 or rect.height < 5.5:
        return False
    if text.strip().upper() in {"HAYNES", "HAYNES HINT", "NOTES"}:
        return False
    if len(words) >= 2 and all(len(word) <= 3 for word in words) and not re.search(r"\d", text):
        return False
    # Wiring-diagram OCR contains hundreds of tiny false-positive fragments.
    # Preserve the actual diagrams and translate only substantial legends/titles.
    if page_index >= 332 and not (rect.y1 < 45 or (len(text) >= 45 and rect.height >= 11)):
        return False
    return True


def extract_blocks(page: pymupdf.Page, page_index: int) -> list[TextBlock]:
    # Only OCR text is needed here; encoding full-page scans is very expensive.
    data = page.get_text("dict", sort=False,
                         flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    blocks: list[TextBlock] = []
    for raw in data.get("blocks", []):
        if raw.get("type") != 0:
            continue
        lines = raw.get("lines", [])
        spans = [span for line in lines for span in line.get("spans", []) if span.get("text")]
        if not spans:
            continue
        raw_source = " ".join(span["text"] for span in spans)
        source = clean_ocr_text(raw_source)
        rect = pymupdf.Rect(raw["bbox"])
        if re.search(r"\b(?:WHC|WHY)\b\s*$", raw_source):
            if rect.x0 < page.rect.width / 3:
                rect.x1 = min(rect.x1, page.rect.width * 0.36)
            elif rect.x0 < page.rect.width * 2 / 3:
                rect.x1 = min(rect.x1, page.rect.width * 0.69)
        if not block_is_meaningful(source, rect, page_index):
            continue
        sizes = sorted(float(span.get("size", 7.0)) for span in spans)
        font_size = sizes[len(sizes) // 2]
        lower = source.lower()
        bold = font_size >= 7.8 or len(source) < 90 and bool(
            re.match(r"^(?:\d+[A-Za-z.]*\s+)?(?:caution|warning|removal|refitting|reinstallation|replacement|note)\b", lower)
        )
        italic = lower.startswith(("note:", "caution:", "warning:"))
        blocks.append(TextBlock(page_index, rect, source, font_size, bold, italic))

    # Archive OCR sometimes emits one wide duplicate over several genuine
    # column blocks.  Keeping both causes translated lists to print on top of
    # one another.  Prefer the smaller column-aware blocks in that situation;
    # supplemental OCR will recover any line present only in the wide block.
    filtered: list[TextBlock] = []
    for block in blocks:
        if block.rect.width >= page.rect.width * 0.72 and block.font_size < 8.5:
            overlapping = 0
            for other in blocks:
                if other is block or other.rect.width >= block.rect.width * 0.75:
                    continue
                vertical = max(0.0, min(block.rect.y1, other.rect.y1) - max(block.rect.y0, other.rect.y0))
                if vertical / max(1.0, other.rect.height) >= 0.5 and _intersection_ratio(other.rect, block.rect) >= 0.7:
                    overlapping += 1
            if overlapping >= 2:
                continue
        filtered.append(block)
    return filtered


def _intersection_ratio(inner: pymupdf.Rect, outer: pymupdf.Rect) -> float:
    intersection = inner & outer
    if intersection.is_empty or inner.get_area() <= 0:
        return 0.0
    return intersection.get_area() / inner.get_area()


def windows_ocr_lines(
    page: pymupdf.Page,
    page_index: int,
    cache_dir: Path,
    scale: float = 1.5,
) -> list[dict[str, float | str]]:
    """Return Windows OCR lines, caching only compact JSON (not page images)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"page_{page_index + 1:04d}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    image_path = cache_dir / f"page_{page_index + 1:04d}.jpg"
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
    pix.save(image_path, jpg_quality=92)
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(WINDOWS_OCR_SCRIPT),
                str(image_path),
            ],
            check=True,
            capture_output=True,
        )
        raw = completed.stdout.decode("utf-8-sig")
        lines = json.loads(raw)
        if isinstance(lines, dict):
            lines = [lines]
        cache_path.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
        return lines
    except (subprocess.CalledProcessError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"warning: supplemental OCR failed on page {page_index + 1}: {exc}", file=sys.stderr)
        return []
    finally:
        image_path.unlink(missing_ok=True)


def supplement_with_windows_ocr(
    page: pymupdf.Page,
    page_index: int,
    existing: Sequence[TextBlock],
    cache_dir: Path,
    scale: float = 1.5,
) -> list[TextBlock]:
    """Add OCR lines that are spatially absent from the Archive.org text layer."""
    candidates: list[TextBlock] = []
    for line in windows_ocr_lines(page, page_index, cache_dir, scale=scale):
        text = clean_ocr_text(str(line.get("text", "")))
        if not text:
            continue
        rect = pymupdf.Rect(
            float(line["x"]) / scale,
            float(line["y"]) / scale,
            (float(line["x"]) + float(line["width"])) / scale,
            (float(line["y"]) + float(line["height"])) / scale,
        )
        if any(_intersection_ratio(rect, block.rect + (-1.0, -1.0, 1.0, 1.0)) >= 0.45 for block in existing):
            continue
        if not block_is_meaningful(text, rect, page_index):
            continue
        font_size = max(4.2, min(12.0, rect.height * 0.78))
        lower = text.lower()
        candidates.append(
            TextBlock(
                page_index,
                rect,
                text,
                font_size,
                bold=font_size >= 7.8 or bool(re.match(r"^\d+[A-Za-z.]*\s+", text)),
                italic=lower.startswith(("note:", "caution:", "warning:")),
            )
        )

    # Join adjacent missing OCR lines into caption-sized blocks.  This preserves
    # sentence context without accidentally merging neighbouring columns.
    candidates.sort(key=lambda block: (block.rect.y0, block.rect.x0))
    merged: list[TextBlock] = []
    for block in candidates:
        match_index: int | None = None
        best_gap = float("inf")
        for index, prior in enumerate(merged):
            vertical_gap = block.rect.y0 - prior.rect.y1
            horizontal_overlap = max(
                0.0,
                min(block.rect.x1, prior.rect.x1) - max(block.rect.x0, prior.rect.x0),
            )
            overlap_ratio = horizontal_overlap / max(1.0, min(block.rect.width, prior.rect.width))
            if -1.0 <= vertical_gap <= max(4.0, prior.rect.height * 0.8) and overlap_ratio >= 0.45:
                if vertical_gap < best_gap:
                    best_gap = vertical_gap
                    match_index = index
        if match_index is None:
            merged.append(block)
            continue
        prior = merged[match_index]
        merged[match_index] = TextBlock(
            page_index,
            prior.rect | block.rect,
            f"{prior.source} {block.source}",
            min(prior.font_size, block.font_size),
            prior.bold,
            prior.italic,
        )
    return merged


class TranslationCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS translations (
                source_hash TEXT PRIMARY KEY,
                source_text TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                model_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.commit()

    @staticmethod
    def key(text: str, model_id: str) -> str:
        return hashlib.sha256(f"{model_id}\0{text}".encode("utf-8")).hexdigest()

    def get(self, text: str, model_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT translated_text FROM translations WHERE source_hash = ?",
            (self.key(text, model_id),),
        ).fetchone()
        return row[0] if row else None

    def put_many(self, rows: Sequence[tuple[str, str]], model_id: str) -> None:
        self.connection.executemany(
            "INSERT OR REPLACE INTO translations(source_hash, source_text, translated_text, model_id) VALUES(?,?,?,?)",
            [(self.key(src, model_id), src, dst, model_id) for src, dst in rows],
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


class QuickMTTranslator:
    model_id = "quickmt-en-ru+haynes-reference-v5"

    def __init__(self, model_dir: Path) -> None:
        self.source_sp = spm.SentencePieceProcessor(model_file=str(model_dir / "src.spm.model"))
        self.target_sp = spm.SentencePieceProcessor(model_file=str(model_dir / "tgt.spm.model"))
        threads = max(2, min(12, (os.cpu_count() or 8) - 2))
        self.translator = ctranslate2.Translator(
            str(model_dir),
            device="cpu",
            compute_type="int8",
            inter_threads=2,
            intra_threads=max(2, threads // 2),
        )

    def translate_batch(self, texts: Sequence[str]) -> list[str]:
        outputs: list[str | None] = [None] * len(texts)
        pending_indices: list[int] = []
        pending_sources: list[str] = []
        for index, text in enumerate(texts):
            exact = EXACT_TRANSLATIONS.get(text.strip())
            if exact is not None:
                outputs[index] = exact
            else:
                pending_indices.append(index)
                pending_sources.append(text)

        if pending_sources:
            rewritten = [rewrite_source(text) for text in pending_sources]
            tokenized = [self.source_sp.encode(text, out_type=str) for text in rewritten]
            results = self.translator.translate_batch(
                tokenized,
                beam_size=5,
                max_decoding_length=384,
                no_repeat_ngram_size=3,
                repetition_penalty=1.1,
            )
            candidates = [self.target_sp.decode(result.hypotheses[0]) for result in results]

            # A rewrite occasionally makes the model copy a long English term.
            # Retry the original wording and keep whichever result contains less
            # untranslated Latin script.
            retry_positions = [
                position
                for position, candidate in enumerate(candidates)
                if len(re.findall(r"[A-Za-z]", candidate)) >= 8
                and len(re.findall(r"[A-Za-z]", candidate))
                > len(re.findall(r"[А-Яа-яЁё]", candidate)) * 0.18
            ]
            if retry_positions:
                retry_tokens = [
                    self.source_sp.encode(pending_sources[position], out_type=str)
                    for position in retry_positions
                ]
                retry_results = self.translator.translate_batch(
                    retry_tokens,
                    beam_size=5,
                    max_decoding_length=384,
                    no_repeat_ngram_size=3,
                    repetition_penalty=1.1,
                )
                for position, retry in zip(retry_positions, retry_results):
                    retry_text = self.target_sp.decode(retry.hypotheses[0])
                    if len(re.findall(r"[A-Za-z]", retry_text)) < len(re.findall(r"[A-Za-z]", candidates[position])):
                        candidates[position] = retry_text

            for index, candidate in zip(pending_indices, candidates):
                outputs[index] = post_edit(candidate)

        return [
            enhance_translation(source, output or "")
            for source, output in zip(texts, outputs)
        ]


def translate_blocks(
    blocks: Sequence[TextBlock],
    engine: QuickMTTranslator,
    cache: TranslationCache,
    batch_size: int = 24,
) -> dict[tuple[int, float, float, float, float], str]:
    block_units: list[list[str]] = [split_translation_units(block.source) for block in blocks]
    unique_units: list[str] = []
    seen: set[str] = set()
    for units in block_units:
        for unit in units:
            if unit and unit not in seen:
                seen.add(unit)
                unique_units.append(unit)

    translations: dict[str, str] = {}
    missing: list[str] = []
    for unit in unique_units:
        cached = cache.get(unit, engine.model_id)
        if cached is None:
            missing.append(unit)
        else:
            translations[unit] = cached

    started = time.monotonic()
    for offset in range(0, len(missing), batch_size):
        batch = missing[offset : offset + batch_size]
        outputs = engine.translate_batch(batch)
        cache.put_many(list(zip(batch, outputs)), engine.model_id)
        translations.update(zip(batch, outputs))
        done = min(offset + len(batch), len(missing))
        elapsed = max(0.001, time.monotonic() - started)
        rate = done / elapsed
        remaining = (len(missing) - done) / rate if rate else 0
        print(
            f"translated {done}/{len(missing)} new units "
            f"({rate:.1f}/s, ETA {remaining/60:.1f} min)",
            flush=True,
        )

    result: dict[tuple[int, float, float, float, float], str] = {}
    for block, units in zip(blocks, block_units):
        key = (block.page_index, block.rect.x0, block.rect.y0, block.rect.x1, block.rect.y1)
        result[key] = " ".join(translations[unit] for unit in units if unit in translations)
    return result


def pixmap_array(page: pymupdf.Page, scale: float = 1.5) -> np.ndarray:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3]


def sample_background(image: np.ndarray, rect: pymupdf.Rect, scale: float = 1.5) -> tuple[tuple[float, float, float], bool]:
    height, width, _ = image.shape
    x0 = max(0, min(width - 1, int(rect.x0 * scale)))
    y0 = max(0, min(height - 1, int(rect.y0 * scale)))
    x1 = max(x0 + 1, min(width, int(rect.x1 * scale) + 1))
    y1 = max(y0 + 1, min(height, int(rect.y1 * scale) + 1))
    crop = image[y0:y1, x0:x1].reshape(-1, 3)
    luminance = crop.mean(axis=1)
    bright_fraction = float(np.mean(luminance >= 175))
    median_luminance = float(np.median(luminance))
    # Text over photographs or diagrams is left intact to avoid destroying art.
    safe = median_luminance >= 190 and bright_fraction >= 0.50
    candidates = crop[luminance >= max(160, np.percentile(luminance, 60))]
    if len(candidates) < 8:
        candidates = crop
    rgb = np.median(candidates, axis=0) / 255.0
    return (float(rgb[0]), float(rgb[1]), float(rgb[2])), safe


def fit_textbox(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    text: str,
    font_name: str,
    original_size: float,
    *,
    commit: bool = True,
) -> tuple[bool, float]:
    start = min(max(original_size, 5.0), 18.0)
    minimum = 4.2 if rect.height >= 12 else 3.8
    size = start
    while size >= minimum:
        shape = page.new_shape()
        result = shape.insert_textbox(
            rect,
            text,
            fontsize=size,
            fontname=font_name,
            color=(0.04, 0.04, 0.04),
            align=pymupdf.TEXT_ALIGN_LEFT,
            lineheight=1.08,
        )
        if result >= 0:
            if commit:
                shape.commit(overlay=True)
            return True, size
        size -= 0.35
    return False, size


def build_pdf(
    source: pymupdf.Document,
    page_indices: Sequence[int],
    blocks: Sequence[TextBlock],
    translations: dict[tuple[int, float, float, float, float], str],
    output: Path,
) -> tuple[int, int, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    by_page: dict[int, list[TextBlock]] = {}
    for block in blocks:
        by_page.setdefault(block.page_index, []).append(block)

    result = pymupdf.open()
    inserted = skipped_images = failed_fit = 0
    for out_index, page_index in enumerate(page_indices):
        source_page = source[page_index]
        background = pixmap_array(source_page)
        result.insert_pdf(source, from_page=page_index, to_page=page_index)
        page = result[-1]
        page.insert_font(fontname="ArialRU", fontfile=str(FONT_REGULAR))
        page.insert_font(fontname="ArialRUBold", fontfile=str(FONT_BOLD))
        page.insert_font(fontname="ArialRUItalic", fontfile=str(FONT_ITALIC))

        prepared: list[tuple[TextBlock, pymupdf.Rect, str, tuple[float, float, float], str]] = []
        for block in by_page.get(page_index, []):
            key = (block.page_index, block.rect.x0, block.rect.y0, block.rect.x1, block.rect.y1)
            translated = translations.get(key, "").strip()
            if not translated:
                continue
            fill, safe = sample_background(background, block.rect)
            if not safe:
                skipped_images += 1
                continue
            pad_x = 1.15
            pad_y = 0.8
            mask = pymupdf.Rect(
                max(0, block.rect.x0 - pad_x),
                max(0, block.rect.y0 - pad_y),
                min(page.rect.width, block.rect.x1 + pad_x),
                min(page.rect.height, block.rect.y1 + pad_y),
            )
            font_name = "ArialRUItalic" if block.italic else ("ArialRUBold" if block.bold else "ArialRU")
            text_rect = pymupdf.Rect(mask.x0 + 0.6, mask.y0 + 0.2, mask.x1 - 0.4, mask.y1 - 0.1)
            fits, _ = fit_textbox(page, text_rect, translated, font_name, block.font_size, commit=False)
            if not fits:
                # Never erase the original until the entire translation fits.
                failed_fit += 1
                continue
            prepared.append((block, mask, translated, fill, font_name))

        # Erase all English regions first so later masks cannot cover Russian text
        # from a neighbouring OCR block.
        for _block, mask, _translated, fill, _font_name in prepared:
            page.draw_rect(mask, color=fill, fill=fill, width=0, overlay=True)

        for block, mask, translated, _fill, font_name in prepared:
            text_rect = pymupdf.Rect(mask.x0 + 0.6, mask.y0 + 0.2, mask.x1 - 0.4, mask.y1 - 0.1)
            ok, _used_size = fit_textbox(page, text_rect, translated, font_name, block.font_size)
            if ok:
                inserted += 1
            else:
                raise RuntimeError(f"Text no longer fits after preflight on page {page_index + 1}")

        print(f"assembled page {page_index + 1} ({out_index + 1}/{len(page_indices)})", flush=True)

    result.set_metadata(
        {
            **source.metadata,
            "title": "VW Golf & Bora — руководство по обслуживанию и ремонту (машинный перевод на русский)",
            "subject": "Русский машинный перевод с сохранением оригинальных иллюстраций",
            "producer": "PyMuPDF + QuickMT; generated by translate_haynes.py",
        }
    )
    result.save(output, garbage=3, deflate=True, clean=True)
    result.close()
    return inserted, skipped_images, failed_fit


def parse_pages(spec: str | None, page_count: int) -> list[int]:
    if not spec:
        return list(range(page_count))
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"reversed page range: {part}")
            pages.update(range(start - 1, end))
        else:
            pages.add(int(part) - 1)
    invalid = [page + 1 for page in pages if page < 0 or page >= page_count]
    if invalid:
        raise ValueError(f"page numbers out of range: {invalid}")
    return sorted(pages)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=ROOT / "Haynes_VW_Golf_Bora_RU.pdf")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--ocr-cache", type=Path, default=ROOT / ".work" / "ocr_cache")
    parser.add_argument("--no-supplemental-ocr", action="store_true")
    parser.add_argument("--pages", help="1-based pages, e.g. 3,50-52; default: all")
    args = parser.parse_args(argv)

    for required in (
        args.input,
        args.model / "model.bin",
        FONT_REGULAR,
        FONT_BOLD,
        FONT_ITALIC,
        WINDOWS_OCR_SCRIPT,
    ):
        if not required.exists():
            parser.error(f"required file not found: {required}")

    source = pymupdf.open(args.input)
    page_indices = parse_pages(args.pages, source.page_count)
    blocks: list[TextBlock] = []
    for page_index in page_indices:
        page_blocks = extract_blocks(source[page_index], page_index)
        supplemental: list[TextBlock] = []
        if not args.no_supplemental_ocr:
            supplemental = supplement_with_windows_ocr(
                source[page_index], page_index, page_blocks, args.ocr_cache
            )
            page_blocks.extend(supplemental)
        blocks.extend(page_blocks)
        print(
            f"extracted page {page_index + 1}: {len(page_blocks)} blocks "
            f"({len(supplemental)} supplemental)",
            flush=True,
        )

    cache = TranslationCache(args.cache)
    try:
        engine = QuickMTTranslator(args.model)
        translations = translate_blocks(blocks, engine, cache)
    finally:
        cache.close()

    inserted, skipped_images, failed_fit = build_pdf(source, page_indices, blocks, translations, args.output)
    source.close()
    print(
        f"saved {args.output} | inserted={inserted}, image_regions_skipped={skipped_images}, "
        f"unfitted_blocks_kept_in_original={failed_fit}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
