#!/usr/bin/env python3
"""Build structured Russian articles and media assets from the Haynes scan.

Unlike the PDF-overlay pipeline, this builder treats Windows OCR as the primary
source, separates prose from illustrations, translates the prose, and emits
article JSON plus standalone WebP images for the Android application.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from reference_terminology import enhance_translation

from translate_haynes import (
    DEFAULT_CACHE,
    DEFAULT_INPUT,
    DEFAULT_MODEL,
    QuickMTTranslator,
    TranslationCache,
    clean_ocr_text,
    split_translation_units,
)


ROOT = Path(__file__).resolve().parent
OCR_CACHE = ROOT / ".work" / "ocr_cache"
WORK_ROOT = ROOT / ".work" / "native_content"
ANDROID_ASSETS = ROOT / "android-manual" / "app" / "src" / "main" / "assets"
ARTICLES_DIR = ANDROID_ASSETS / "articles"
MEDIA_DIR = ANDROID_ASSETS / "media"
SCALE = 1.5
FONT_PATH = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD_PATH = Path(r"C:\Windows\Fonts\arialbd.ttf")


SECTION_DEFS: tuple[tuple[str, str, str, str, int, int], ...] = (
    ("00", "about", "О книге", "Обзор моделей и введение", 3, 8),
    ("0.1", "roadside", "В дороге", "Ремонт в пути", 9, 12),
    ("0.2", "weekly", "В дороге", "Еженедельные проверки", 13, 19),
    ("1A", "maintenance_petrol", "Обслуживание", "Бензиновые модели", 21, 40),
    ("1B", "maintenance_diesel", "Обслуживание", "Дизельные модели", 41, 58),
    ("2A", "engine_sohc", "Двигатель", "Бензиновый двигатель SOHC", 59, 78),
    ("2B", "engine_dohc", "Двигатель", "Бензиновый двигатель DOHC", 79, 110),
    ("2C", "engine_diesel", "Двигатель", "Дизельный двигатель", 111, 132),
    ("2D", "engine_overhaul", "Двигатель", "Снятие и капитальный ремонт двигателя", 133, 160),
    ("3", "cooling", "Системы двигателя", "Охлаждение, отопление и кондиционер", 161, 172),
    ("4A", "fuel_petrol", "Питание и выпуск", "Топливная система бензиновых двигателей", 173, 190),
    ("4B", "fuel_diesel", "Питание и выпуск", "Топливная система дизельных двигателей", 191, 204),
    ("4C", "emissions_petrol", "Питание и выпуск", "Снижение токсичности и выпуск — бензин", 205, 218),
    ("4D", "emissions_diesel", "Питание и выпуск", "Снижение токсичности и выпуск — дизель", 219, 226),
    ("5A", "starting", "Электрооборудование", "Системы запуска и зарядки", 227, 232),
    ("5B", "ignition", "Электрооборудование", "Зажигание бензиновых двигателей", 233, 236),
    ("5C", "preheating", "Электрооборудование", "Предпусковой подогрев дизеля", 237, 238),
    ("6", "clutch", "Трансмиссия", "Сцепление", 239, 246),
    ("7A", "manual_transmission", "Трансмиссия", "Механическая коробка передач", 247, 252),
    ("7B", "automatic_transmission", "Трансмиссия", "Автоматическая коробка передач", 253, 256),
    ("8", "driveshafts", "Трансмиссия", "Приводные валы и ШРУСы", 257, 264),
    ("9", "brakes", "Ходовая часть", "Тормозная система", 265, 278),
    ("10", "suspension", "Ходовая часть", "Подвеска и рулевое управление", 279, 302),
    ("11", "bodywork", "Кузов", "Кузов и наружное оборудование", 303, 328),
    ("12", "body_electrical", "Кузов", "Электрооборудование кузова", 329, 347),
    ("12W", "wiring", "Схемы", "Электрические схемы", 348, 356),
    ("REF", "reference", "Справочник", "Данные, инструмент и общие приёмы", 357, 363),
    ("MOT", "inspection", "Справочник", "Проверка технического состояния", 364, 367),
    ("DIAG", "diagnostics", "Справочник", "Поиск неисправностей", 368, 374),
    ("GLO", "glossary", "Справочник", "Словарь технических терминов", 375, 379),
    ("IDX", "index", "Справочник", "Предметный указатель", 380, 383),
)


OCR_REPAIRS: tuple[tuple[str, str], ...] = (
    (r"\bretitt(?:ing|ed)\b", "refitting"),
    (r"\bretit\b", "refit"),
    (r"\brefining\b", "refitting"),
    (r"\bramova[l']\b", "removal"),
    (r"\bremova'\b", "removal"),
    (r"\binsg[»p]ction\b", "inspection"),
    (r"\btransmtss(?:ion|•on)\b", "transmission"),
    (r"\bciutch\b", "clutch"),
    (r"\bs'ave\b", "slave"),
    (r"\bot the\b", "of the"),
    (r"\bail\b", "all"),
    (r"\btlat\b", "flat"),
    (r"\bcor{1,2}wt\b", "correct"),
    (r"\bc»sition\b", "position"),
    (r"\bsphng\b", "spring"),
    (r"\bcornvessor\b", "compressor"),
    (r"\bcouets\b", "collets"),
    (r"\bcoaets\b", "collets"),
    (r"\btorce\b", "force"),
    (r"\bw'thdraw\b", "withdraw"),
    (r"\bcab'e\b", "cable"),
    (r"\bdiM:onnected\b", "disconnected"),
    (r"\btransmtss•on\b", "transmission"),
    (r"\bIcnzation\b", "location"),
    (r"\bStarter\b", "starter"),
    (r"\bfaun\b", "fault"),
    (r"\bitseM\b", "itself"),
    (r"\bdrivee\b", "drive"),
    (r"\bmcmng\b", "moving"),
    (r"\bparl\b", "part"),
    (r"\bOtl\b", "off"),
    (r"\bTum\b", "Turn"),
    (r"\b[O0]t\b", "of"),
    (r"\bo'(?=\s)", "of"),
    (r"['*]ur-?np\b", "jump"),
    (r"['*]ump\b", "jump"),
    (r"(?<!\w)[*]ill\b", "will"),
    (r"\bflat battery\b", "discharged battery"),
    (r"\bpositive \(4\) terminal\b", "positive (+) terminal"),
)


PARAGRAPH_REPAIRS: tuple[tuple[str, str], ...] = (
    (
        r"\bConnect the other end of the red lead to the positive \(\+\) terminal of the battery\.?$",
        "Connect the other end of the red lead to the positive (+) terminal of the booster battery.",
    ),
    (
        r"\bConnect one end of the black jump lead to the negative \(-\) terminal of the battery\.?$",
        "Connect one end of the black jump lead to the negative (-) terminal of the booster battery.",
    ),
    (
        r"Connect the other end of the black jump lead to a suitable metal part of the engine On the vehicle to$",
        "Connect the other end of the black jump lead to a suitable metal part of the engine on the vehicle to be started.",
    ),
    (
        r"Start the engine using the battery and run it at idle Switch on the lights\. rear window demister and heater blower motor, then the jump leads in the reverse order of connection\. Turn off the lights etc\.?$",
        "Start the engine using the booster battery and run it at idle speed. Switch on the lights, rear window demister and heater blower motor, then disconnect the jump leads in the reverse order of connection. Turn off the lights etc.",
    ),
)


@dataclass(frozen=True)
class OcrLine:
    index: int
    text: str
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def rect(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.right, self.bottom


@dataclass(frozen=True)
class MediaBox:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        return self.width * self.height

    def intersection_ratio(self, line: OcrLine) -> float:
        x0 = max(self.x0, line.x)
        y0 = max(self.y0, line.y)
        x1 = min(self.x1, line.right)
        y1 = min(self.y1, line.bottom)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        return ((x1 - x0) * (y1 - y0)) / max(1.0, line.width * line.height)


@dataclass
class DraftBlock:
    kind: str
    page: int
    source: str = ""
    asset: str = ""
    translated: str = ""


@dataclass
class SectionDraft:
    code: str
    slug: str
    category: str
    title: str
    start_page: int
    end_page: int
    blocks: list[DraftBlock]


def repair_ocr(text: str) -> str:
    result = clean_ocr_text(text)
    result = result.replace("•", ".").replace("ﬁ", "fi").replace("ﬂ", "fl")
    for pattern, replacement in OCR_REPAIRS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    result = re.sub(r"\s{2,}", " ", result).strip(" _")
    return result


def load_ocr_lines(page_number: int) -> list[OcrLine]:
    path = OCR_CACHE / f"page_{page_number:04d}.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    output: list[OcrLine] = []
    for index, row in enumerate(rows):
        text = repair_ocr(str(row.get("text", "")))
        if not text:
            continue
        output.append(
            OcrLine(
                index=index,
                text=text,
                x=float(row["x"]),
                y=float(row["y"]),
                width=float(row["width"]),
                height=float(row["height"]),
            )
        )
    return output


def render_page(page: pymupdf.Page) -> Image.Image:
    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(SCALE, SCALE),
        colorspace=pymupdf.csRGB,
        alpha=False,
    )
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _connected_components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=np.uint8)
    components: list[tuple[int, int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or visited[y, x]:
                continue
            stack = [(x, y)]
            visited[y, x] = 1
            min_x = max_x = x
            min_y = max_y = y
            count = 0
            while stack:
                px, py = stack.pop()
                count += 1
                min_x = min(min_x, px)
                max_x = max(max_x, px)
                min_y = min(min_y, py)
                max_y = max(max_y, py)
                for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                    if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = 1
                        stack.append((nx, ny))
            components.append((min_x, min_y, max_x + 1, max_y + 1, count))
    return components


def _merge_boxes(boxes: Sequence[MediaBox], page_width: int, page_height: int) -> list[MediaBox]:
    # Adjacent photo panels must stay separate: joining them recreates a full
    # printed page inside the app.  Only discard near-duplicates produced by
    # overlapping texture components.
    deduplicated: list[MediaBox] = []
    for box in sorted(boxes, key=lambda item: item.area, reverse=True):
        if any(
            max(0, min(box.x1, kept.x1) - max(box.x0, kept.x0))
            * max(0, min(box.y1, kept.y1) - max(box.y0, kept.y0))
            >= box.area * 0.82
            for kept in deduplicated
        ):
            continue
        deduplicated.append(box)
    return sorted(deduplicated, key=lambda item: (item.y0, item.x0))


def _gap_runs(values: np.ndarray, maximum: float) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value <= maximum:
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(values)))
    return runs


def _split_texture_region(
    mask: np.ndarray,
    bounds: tuple[int, int, int, int],
    *,
    depth: int = 0,
) -> list[tuple[int, int, int, int]]:
    """Split a linked page-sized component at genuine white gutters.

    Arrows and panel borders often connect otherwise independent Haynes
    illustrations.  Connected components therefore need a second pass based
    on the *unexpanded* texture grid.  A cut is only made when both resulting
    sides contain enough visual information to stand on their own.
    """

    x0, y0, x1, y1 = bounds
    region = mask[y0:y1, x0:x1]
    occupied_rows = np.flatnonzero(region.any(axis=1))
    occupied_cols = np.flatnonzero(region.any(axis=0))
    if not len(occupied_rows) or not len(occupied_cols):
        return []
    y0 += int(occupied_rows[0])
    y1 = y0 + int(occupied_rows[-1] - occupied_rows[0] + 1)
    x0 += int(occupied_cols[0])
    x1 = x0 + int(occupied_cols[-1] - occupied_cols[0] + 1)
    region = mask[y0:y1, x0:x1]
    height, width = region.shape
    if depth >= 7 or width < 12 or height < 10:
        return [(x0, y0, x1, y1)]

    candidates: list[tuple[float, str, int, int]] = []
    row_fraction = region.mean(axis=1)
    col_fraction = region.mean(axis=0)
    for start, end in _gap_runs(row_fraction, 0.06):
        if end - start < 1 or start < 6 or height - end < 6:
            continue
        before = int(region[:start].sum())
        after = int(region[end:].sum())
        if min(before, after) < 18:
            continue
        balance = min(start, height - end) / max(start, height - end)
        candidates.append(((end - start) * 5.0 + balance, "row", start, end))
    for start, end in _gap_runs(col_fraction, 0.06):
        if end - start < 1 or start < 7 or width - end < 7:
            continue
        before = int(region[:, :start].sum())
        after = int(region[:, end:].sum())
        if min(before, after) < 18:
            continue
        balance = min(start, width - end) / max(start, width - end)
        candidates.append(((end - start) * 5.0 + balance, "col", start, end))
    if not candidates:
        return [(x0, y0, x1, y1)]

    _, axis, start, end = max(candidates, key=lambda item: item[0])
    if axis == "row":
        return _split_texture_region(mask, (x0, y0, x1, y0 + start), depth=depth + 1) + _split_texture_region(
            mask, (x0, y0 + end, x1, y1), depth=depth + 1
        )
    return _split_texture_region(mask, (x0, y0, x0 + start, y1), depth=depth + 1) + _split_texture_region(
        mask, (x0 + end, y0, x1, y1), depth=depth + 1
    )


def detect_media(
    image: Image.Image,
    lines: Sequence[OcrLine],
    *,
    verbose: bool = False,
) -> list[MediaBox]:
    gray = np.asarray(image.convert("L")).copy()
    height, width = gray.shape
    text_free = gray.copy()
    for line in lines:
        pad_x = 7
        pad_y = 5
        x0 = max(0, int(line.x) - pad_x)
        y0 = max(0, int(line.y) - pad_y)
        x1 = min(width, int(math.ceil(line.right)) + pad_x)
        y1 = min(height, int(math.ceil(line.bottom)) + pad_y)
        # Removing the complete OCR rectangle, rather than just recognised
        # glyphs, stops columns of prose and captions becoming "pictures".
        fill = int(np.median(gray[max(0, y0 - 3) : min(height, y1 + 3), x0:x1]))
        text_free[y0:y1, x0:x1] = max(235, fill)

    # Work on a coarse texture grid.  Photographs occupy many textured cells;
    # line drawings occupy fewer, but their local contrast remains high.  Long
    # rules and panel borders alone never fill enough neighbouring cells.
    cell = 10
    grid_width = math.ceil(width / cell)
    grid_height = math.ceil(height / cell)
    padded = np.full((grid_height * cell, grid_width * cell), 245, dtype=np.uint8)
    padded[:height, :width] = text_free
    blocks = padded.reshape(grid_height, cell, grid_width, cell).transpose(0, 2, 1, 3)
    block_median = np.median(blocks, axis=(2, 3), keepdims=True)
    density = (blocks < (block_median - 14)).mean(axis=(2, 3))
    low = np.percentile(blocks, 10, axis=(2, 3))
    high = np.percentile(blocks, 90, axis=(2, 3))
    spread = high - low
    # Relative contrast is essential on these scans: the paper itself ranges
    # from near-white to grey from page to page, so a fixed darkness threshold
    # incorrectly marks an entire sheet as an illustration.
    active = ((density >= 0.055) & (spread >= 18.0)) | (spread >= 42.0)
    active[:2, :] = False
    active[-2:, :] = False
    active[:, :2] = False
    active[:, -2:] = False

    grid_image = Image.fromarray(active.astype(np.uint8) * 255, mode="L")
    # Bridge the narrow gaps left where OCR labels were removed, then discard
    # isolated one-cell noise.  The filters operate in grid-cell units.
    grid_image = grid_image.filter(ImageFilter.MaxFilter(5))
    grid_image = grid_image.filter(ImageFilter.MinFilter(3))
    small_mask = np.asarray(grid_image) >= 128

    grid_regions: list[tuple[int, int, int, int, int]] = []
    for sx0, sy0, sx1, sy1, component_area in _connected_components(small_mask):
        if component_area < 10:
            continue
        split_regions = _split_texture_region(active, (sx0, sy0, sx1, sy1))
        for rx0, ry0, rx1, ry1 in split_regions:
            grid_regions.append((rx0, ry0, rx1, ry1, int(active[ry0:ry1, rx0:rx1].sum())))

    boxes: list[MediaBox] = []
    for sx0, sy0, sx1, sy1, component_area in grid_regions:
        x0 = max(0, sx0 * cell - 10)
        y0 = max(0, sy0 * cell - 10)
        x1 = min(width, sx1 * cell + 10)
        y1 = min(height, sy1 * cell + 10)
        box = MediaBox(x0, y0, x1, y1)
        reason = "accepted"
        if box.width < 105 or box.height < 65:
            reason = "small"
            if verbose and component_area >= 12:
                print(f"  texture {box}: cells={component_area} {reason}", flush=True)
            continue
        if box.area > width * height * 0.62:
            reason = "too-large"
            if verbose:
                print(f"  texture {box}: cells={component_area} {reason}", flush=True)
            continue
        if box.width / max(1, box.height) > 6.5 or box.height / max(1, box.width) > 5.5:
            reason = "aspect"
            if verbose:
                print(f"  texture {box}: cells={component_area} {reason}", flush=True)
            continue
        crop_gray = text_free[y0:y1, x0:x1]
        crop_median = float(np.median(crop_gray))
        dark_fraction = float((crop_gray < crop_median - 14).mean())
        contrast = float(crop_gray.std())
        ocr_area = sum(
            max(0.0, min(x1, line.right) - max(x0, line.x))
            * max(0.0, min(y1, line.bottom) - max(y0, line.y))
            for line in lines
        )
        ocr_fraction = ocr_area / max(1, box.area)
        if dark_fraction < 0.028 or contrast < 8:
            reason = f"weak dark={dark_fraction:.3f} std={contrast:.1f}"
            if verbose:
                print(f"  texture {box}: cells={component_area} {reason}", flush=True)
            continue
        if ocr_fraction > 0.24 or (ocr_fraction > 0.15 and dark_fraction < 0.11):
            reason = f"mostly-text ocr={ocr_fraction:.3f}"
            if verbose:
                print(f"  texture {box}: cells={component_area} {reason}", flush=True)
            continue
        if y0 < 70 and box.height < 105:
            reason = "header"
            if verbose:
                print(f"  texture {box}: cells={component_area} {reason}", flush=True)
            continue
        if verbose:
            print(
                f"  texture {box}: cells={component_area} dark={dark_fraction:.3f} "
                f"std={contrast:.1f} ocr={ocr_fraction:.3f} {reason}",
                flush=True,
            )
        boxes.append(box)
    return _merge_boxes(boxes, width, height)[:12]


def debug_pages(pdf: pymupdf.Document, page_numbers: Sequence[int], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for page_number in page_numbers:
        lines = load_ocr_lines(page_number)
        image = render_page(pdf[page_number - 1])
        boxes = detect_media(image, lines, verbose=True)
        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)
        for index, box in enumerate(boxes, 1):
            draw.rectangle((box.x0, box.y0, box.x1, box.y1), outline=(220, 35, 35), width=4)
            draw.text((box.x0 + 5, box.y0 + 5), str(index), fill=(220, 35, 35))
            crop = image.crop((box.x0, box.y0, box.x1, box.y1))
            crop.save(output_dir / f"page_{page_number:04d}_media_{index:02d}.webp", "WEBP", quality=82, method=6)
        annotated.save(output_dir / f"page_{page_number:04d}_annotated.jpg", quality=90)
        print(f"debug page {page_number}: {len(boxes)} media boxes", flush=True)


def _latin_letters(text: str) -> int:
    return len(re.findall(r"[A-Za-z]", text))


def useful_line(line: OcrLine) -> bool:
    text = line.text.strip()
    if not text or text.upper() in {"HAYNES", "HAYNES HINT"}:
        return False
    if len(text) == 1 and not text.isdigit():
        return False
    if re.fullmatch(r"[\W_]+", text, flags=re.UNICODE):
        return False
    if line.y < 70 and line.x > 690 and re.fullmatch(r"[A-Z0-9.·•-]{2,12}", text):
        return False
    visible = len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]", text))
    if visible < 2 or visible / max(1, len(text)) < 0.35:
        return False
    # Reject OCR fragments that contain no plausible word, number or workshop
    # code.  Legitimate units and engine codes are intentionally retained.
    if not re.search(r"[A-Za-zА-Яа-яЁё]{2}|\d{2}|\d+[.,]\d+", text):
        return False
    return True


def line_kind(line: OcrLine, media_boxes: Sequence[MediaBox]) -> str:
    text = line.text.strip()
    lower = text.lower()
    near_media = any(
        box.x0 - 12 <= line.x <= box.x1 + 12
        and box.y0 - 12 <= line.y <= box.y1 + 36
        for box in media_boxes
    )
    if re.match(r"^(warning|caution|note|haynes hint)\b", lower):
        return "note"
    if near_media and re.match(r"^\d{1,2}[.·]\d{1,2}[a-z]?\b", lower):
        return "caption"
    if line.height >= 18:
        return "heading"
    if len(text) <= 72 and (
        re.match(r"^(chapter|contents|specifications|general(?: continued)?|torque wrench settings)\b", lower)
        or (text[:1].isupper() and not re.search(r"[.!?]$", text) and line.height >= 16)
    ):
        return "heading"
    return "text"


def group_page_lines(lines: Sequence[OcrLine], media_boxes: Sequence[MediaBox]) -> list[DraftBlock]:
    prepared = [line for line in lines if useful_line(line)]
    grouped: list[tuple[str, list[OcrLine]]] = []
    current_kind = ""
    current: list[OcrLine] = []

    def flush() -> None:
        nonlocal current, current_kind
        if current:
            grouped.append((current_kind, current))
        current = []
        current_kind = ""

    for line in prepared:
        kind = line_kind(line, media_boxes)
        if kind == "heading":
            flush()
            grouped.append((kind, [line]))
            continue
        if not current:
            current_kind = kind
            current = [line]
            continue
        previous = current[-1]
        vertical_gap = line.y - previous.bottom
        horizontal_overlap = max(0.0, min(line.right, previous.right) - max(line.x, previous.x))
        same_column = (
            abs(line.x - previous.x) <= 58
            or horizontal_overlap >= min(line.width, previous.width) * 0.45
        )
        numbered_start = bool(re.match(r"^\d{1,2}\s+[A-Z]", line.text))
        can_join = (
            kind == current_kind
            and same_column
            and -2 <= vertical_gap <= max(21, previous.height * 1.15)
            and not (numbered_start and re.search(r"[.!?]$", previous.text))
            and sum(len(item.text) for item in current) + len(line.text) <= 430
        )
        if can_join:
            current.append(line)
        else:
            flush()
            current_kind = kind
            current = [line]
    flush()

    blocks: list[DraftBlock] = []
    for kind, group in grouped:
        source = " ".join(item.text.strip() for item in group)
        source = repair_ocr(source)
        for pattern, replacement in PARAGRAPH_REPAIRS:
            source = re.sub(pattern, replacement, source, flags=re.IGNORECASE)
        source = re.sub(r"\s+", " ", source).strip()
        if len(source) >= 2:
            blocks.append(DraftBlock(kind=kind, page=0, source=source))
    return blocks


def _sample_fill(image: Image.Image, rect: tuple[int, int, int, int]) -> tuple[int, int, int]:
    array = np.asarray(image)
    height, width, _ = array.shape
    x0, y0, x1, y1 = rect
    pad = 4
    outer_x0 = max(0, x0 - pad)
    outer_y0 = max(0, y0 - pad)
    outer_x1 = min(width, x1 + pad)
    outer_y1 = min(height, y1 + pad)
    samples: list[np.ndarray] = []
    if outer_y0 < y0:
        samples.append(array[outer_y0:y0, outer_x0:outer_x1].reshape(-1, 3))
    if y1 < outer_y1:
        samples.append(array[y1:outer_y1, outer_x0:outer_x1].reshape(-1, 3))
    if outer_x0 < x0:
        samples.append(array[y0:y1, outer_x0:x0].reshape(-1, 3))
    if x1 < outer_x1:
        samples.append(array[y0:y1, x1:outer_x1].reshape(-1, 3))
    usable = [sample for sample in samples if sample.size]
    if not usable:
        return (240, 240, 236)
    pixels = np.concatenate(usable, axis=0)
    median = np.median(pixels, axis=0)
    return tuple(int(value) for value in median)


def redact_media_crop(image: Image.Image, box: MediaBox, lines: Sequence[OcrLine]) -> Image.Image:
    crop = image.crop((box.x0, box.y0, box.x1, box.y1)).convert("RGB")
    draw = ImageDraw.Draw(crop)
    for line in lines:
        if box.intersection_ratio(line) < 0.18 or _latin_letters(line.text) < 2:
            continue
        x0 = max(0, int(line.x - box.x0) - 3)
        y0 = max(0, int(line.y - box.y0) - 2)
        x1 = min(crop.width, int(math.ceil(line.right - box.x0)) + 3)
        y1 = min(crop.height, int(math.ceil(line.bottom - box.y0)) + 2)
        if x1 <= x0 or y1 <= y0:
            continue
        fill = _sample_fill(crop, (x0, y0, x1, y1))
        row = np.asarray(crop)[y0:y1]
        bright_fraction = float((row.mean(axis=2) >= 178).mean()) if row.size else 0.0
        if bright_fraction >= 0.58:
            # Captions often contain an OCR-missed final word.  Clearing the
            # whole light caption band guarantees that no English fragment is
            # left inside the illustration; its translated wording is emitted
            # as a native caption block next to the image.
            draw.rectangle((0, max(0, y0 - 2), crop.width, min(crop.height, y1 + 2)), fill=fill)
        else:
            draw.rectangle((x0, y0, x1, y1), fill=fill)
    return crop


def has_visual_content(image: Image.Image) -> bool:
    gray = np.asarray(image.convert("L"))
    median = float(np.median(gray))
    relative_dark = float((gray < median - 14).mean())
    deviation = float(gray.std())
    # Text-only false positives become almost uniform after their English OCR
    # rows are cleared.  Real photographs and line drawings retain either a
    # substantial tonal spread or enough dark visual structure.
    if deviation < 7.5 or (relative_dark < 0.014 and deviation < 16.0):
        return False
    if image.width / max(1, image.height) > 2.5 and relative_dark < 0.055:
        # After OCR removal, contents/specification tables often leave only a
        # few long horizontal rules.  They are layout residue, not a useful
        # illustration.
        return False
    return True


def prune_generated_media(output_root: Path) -> tuple[int, int]:
    media_dir = output_root / "media"
    articles_dir = output_root / "articles"
    removed_assets: set[str] = set()
    for path in media_dir.glob("*.webp"):
        if path.stat().st_size < 1100:
            keep = False
        else:
            try:
                with Image.open(path) as image:
                    keep = has_visual_content(image.convert("RGB"))
            except Exception:
                keep = False
        if not keep:
            removed_assets.add(f"media/{path.name}")
            path.unlink()

    changed_articles = 0
    article_counts: dict[str, tuple[int, int]] = {}
    for path in articles_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        blocks = payload.get("blocks", [])
        filtered = [block for block in blocks if block.get("asset") not in removed_assets]
        if len(filtered) != len(blocks):
            payload["blocks"] = filtered
            path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            changed_articles += 1
        article_counts[path.stem] = (
            len(filtered),
            sum(block.get("type") == "image" for block in filtered),
        )
    index_path = output_root / "content_index.json"
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for section in index.get("sections", []):
            counts = article_counts.get(str(section.get("slug", "")))
            if counts is not None:
                section["blockCount"], section["imageCount"] = counts
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return len(removed_assets), changed_articles


def translate_drafts(
    sections: Sequence[SectionDraft],
    engine: QuickMTTranslator,
    cache: TranslationCache,
    batch_size: int = 64,
) -> None:
    text_blocks = [block for section in sections for block in section.blocks if block.source]
    units_by_block = [split_translation_units(block.source) for block in text_blocks]
    unique_units: list[str] = []
    seen: set[str] = set()
    for units in units_by_block:
        for unit in units:
            if unit and unit not in seen:
                seen.add(unit)
                unique_units.append(unit)

    translated: dict[str, str] = {}
    missing: list[str] = []
    for unit in unique_units:
        if _latin_letters(unit) < 2:
            translated[unit] = unit
            continue
        cached = cache.get(unit, engine.model_id)
        if cached is None:
            missing.append(unit)
        else:
            translated[unit] = cached

    print(
        f"translation units: {len(unique_units)} total, {len(missing)} new, "
        f"{len(unique_units) - len(missing)} cached",
        flush=True,
    )
    started = time.monotonic()
    for offset in range(0, len(missing), batch_size):
        batch = missing[offset : offset + batch_size]
        outputs = engine.translate_batch(batch)
        cache.put_many(list(zip(batch, outputs)), engine.model_id)
        translated.update(zip(batch, outputs))
        done = min(offset + len(batch), len(missing))
        elapsed = max(0.001, time.monotonic() - started)
        remaining = (len(missing) - done) / max(0.001, done / elapsed)
        print(
            f"translated {done}/{len(missing)} new units "
            f"(ETA {remaining / 60:.1f} min)",
            flush=True,
        )

    for block, units in zip(text_blocks, units_by_block):
        block.translated = " ".join(translated.get(unit, "") for unit in units).strip()
        block.translated = enhance_translation(block.source, block.translated)
        block.translated = re.sub(r"\s+", " ", block.translated)
        if not block.translated:
            block.translated = "Технические данные: " + block.source


def visible_block(block: DraftBlock) -> dict[str, object]:
    output: dict[str, object] = {"type": block.kind, "page": block.page}
    if block.asset:
        output["asset"] = block.asset
        output["description"] = "Фотография или схема из справочника"
    else:
        output["text"] = block.translated
    return output


def build_native_articles(
    pdf: pymupdf.Document,
    output_root: Path,
    *,
    model_dir: Path,
    cache_path: Path,
    first_page: int | None = None,
    last_page: int | None = None,
) -> None:
    articles_dir = output_root / "articles"
    media_dir = output_root / "media"
    if output_root.exists():
        shutil.rmtree(output_root)
    articles_dir.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)

    sections: list[SectionDraft] = []
    pages_done = 0
    images_done = 0
    started = time.monotonic()
    for code, slug, category, title, section_start, section_end in SECTION_DEFS:
        start_page = max(section_start, first_page or section_start)
        end_page = min(section_end, last_page or section_end, len(pdf))
        if start_page > end_page:
            continue
        section = SectionDraft(code, slug, category, title, start_page, end_page, [])
        sections.append(section)
        for page_number in range(start_page, end_page + 1):
            lines = load_ocr_lines(page_number)
            image = render_page(pdf[page_number - 1])
            media_boxes = detect_media(image, lines)
            page_blocks = group_page_lines(lines, media_boxes)
            for block in page_blocks:
                block.page = page_number
                section.blocks.append(block)

            for media_index, box in enumerate(media_boxes, 1):
                asset_name = f"{slug}_{page_number:04d}_{media_index:02d}.webp"
                crop = redact_media_crop(image, box, lines)
                if not has_visual_content(crop):
                    continue
                if crop.width > 1100:
                    new_height = max(1, round(crop.height * 1100 / crop.width))
                    crop = crop.resize((1100, new_height), Image.Resampling.LANCZOS)
                crop.save(media_dir / asset_name, "WEBP", quality=80, method=6)
                section.blocks.append(
                    DraftBlock(kind="image", page=page_number, asset=f"media/{asset_name}")
                )
                images_done += 1

            pages_done += 1
            if pages_done % 10 == 0:
                elapsed = max(0.001, time.monotonic() - started)
                print(
                    f"analysed {pages_done} pages, extracted {images_done} illustrations "
                    f"({pages_done / elapsed:.2f} pages/s)",
                    flush=True,
                )

    engine = QuickMTTranslator(model_dir)
    cache = TranslationCache(cache_path)
    try:
        translate_drafts(sections, engine, cache)
    finally:
        cache.close()

    index_sections: list[dict[str, object]] = []
    for section in sections:
        payload = {
            "code": section.code,
            "slug": section.slug,
            "category": section.category,
            "title": section.title,
            "startPage": section.start_page,
            "endPage": section.end_page,
            "blocks": [visible_block(block) for block in section.blocks],
        }
        article_path = articles_dir / f"{section.slug}.json"
        article_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        index_sections.append(
            {
                "code": section.code,
                "slug": section.slug,
                "category": section.category,
                "title": section.title,
                "startPage": section.start_page,
                "endPage": section.end_page,
                "blockCount": len(section.blocks),
                "imageCount": sum(block.kind == "image" for block in section.blocks),
            }
        )
    (output_root / "content_index.json").write_text(
        json.dumps({"version": 2, "sections": index_sections}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"native content ready: {len(sections)} sections, {pages_done} pages, "
        f"{images_done} illustrations",
        flush=True,
    )


def parse_page_spec(spec: str) -> list[int]:
    output: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            output.update(range(int(start), int(end) + 1))
        else:
            output.add(int(part))
    return sorted(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--debug-pages", help="detect and export media on selected 1-based pages")
    parser.add_argument("--debug-output", type=Path, default=WORK_ROOT / "media_debug")
    parser.add_argument("--build", action="store_true", help="build all native article assets")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=WORK_ROOT / "generated_assets")
    parser.add_argument("--first-page", type=int)
    parser.add_argument("--last-page", type=int)
    parser.add_argument("--prune-output", action="store_true", help="remove layout-only image fragments")
    args = parser.parse_args()

    if args.prune_output:
        removed, articles = prune_generated_media(args.output)
        print(f"pruned {removed} image fragments from {articles} articles", flush=True)
        return 0

    pdf = pymupdf.open(args.input)
    try:
        if args.debug_pages:
            debug_pages(pdf, parse_page_spec(args.debug_pages), args.debug_output)
            return 0
        if args.build:
            build_native_articles(
                pdf,
                args.output,
                model_dir=args.model,
                cache_path=args.cache,
                first_page=args.first_page,
                last_page=args.last_page,
            )
            return 0
    finally:
        pdf.close()
    parser.error("select --build or --debug-pages")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
