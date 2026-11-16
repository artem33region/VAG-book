#!/usr/bin/env python3
"""Rebuild the native manual text from the clean Archive.org PDF text layer.

The first Android corpus used Windows OCR for both layout and prose.  That OCR
is useful for locating illustrations, but it introduces enough damaged words
to make otherwise good machine translation unreadable.  This pass keeps the
already extracted images and replaces prose with line-aware text taken from
the considerably cleaner text layer embedded in the Haynes PDF.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pymupdf

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
DEFAULT_TEMPLATE = ROOT / "android-manual" / "app" / "src" / "main" / "assets"
DEFAULT_OUTPUT = ROOT / ".work" / "native_content" / "clean_assets"
SOURCE_CACHE = ROOT / ".work" / "native_content" / "source_blocks_v4"

ALLOWED_SHORT_WORDS = {
    "abs", "air", "bar", "dohc", "dot", "ecu", "egr", "golf", "gti",
    "haynes", "max", "min", "mpi", "obd", "off", "on", "psi", "rpm",
    "sae", "sohc", "tdi", "torx", "volkswagen", "vw",
}

COMMON_ENGLISH_WORDS = set(
    """
    about above after again against all also an and any are as at back be bearing
    before below between bolt bolts both brake by can car carefully chapter check
    clean clutch compression condition connect connected connecting connection
    control coolant cover crankshaft cylinder damage damaged details difficult do
    down drive driven engine ensure except fit fitted fitting fluid for from front
    fuel general gently has have head if in information inspection install installed
    into is it left line lower make manual may models motor mounting must new no note
    nut nuts of off oil on one only operation or other out over part parts petrol
    pipe position pressure procedure procedures pump rear refit refitting removal
    remove removed renew renewal replace replacement right screw screws seal securing
    sensor should side slowly so specifications spring starter suitable system than
    that the then this through timing to transmission two until upper use using valve
    vehicle warning when where which while will with without wiring
    """.split()
)

PAGE_HEADER_RE = re.compile(
    r"(?:roadside repairs?|weekly checks?|maintenance procedures?|"
    r"in-car engine repair procedures?|engine removal and overhaul procedures?|"
    r"cooling, heating and ventilation systems?|fuel and exhaust systems?|"
    r"starting and charging systems?|ignition system|preheating system|clutch|"
    r"transmission|driveshafts?|braking system|suspension and steering|bodywork|"
    r"body electrical systems?|wiring diagrams?|reference|fault finding|glossary)"
    r"\s+[0-9A-Z.-]+$",
    re.IGNORECASE,
)

NOISE_RE = re.compile(
    r"^(?:haynes|haynes hint|notes?|contents?)$|"
    r"^(?:[|/\\_~^`'\".,;:!?*+=<>-]\s*)+$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PdfLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float
    bold: bool
    italic: bool

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0


@dataclass
class TextGroup:
    kind: str
    lines: list[PdfLine]

    @property
    def x0(self) -> float:
        return min(line.x0 for line in self.lines)

    @property
    def y0(self) -> float:
        return min(line.y0 for line in self.lines)

    @property
    def x1(self) -> float:
        return max(line.x1 for line in self.lines)

    @property
    def y1(self) -> float:
        return max(line.y1 for line in self.lines)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def text(self) -> str:
        result = ""
        for line in sorted(self.lines, key=lambda item: (item.y0, item.x0)):
            value = line.text.strip()
            if not value:
                continue
            if result.endswith("-") and value[:1].islower():
                result = result[:-1] + value
            else:
                result = f"{result} {value}".strip()
        return normalise_source(result)


@dataclass
class NativeBlock:
    kind: str
    page: int
    source: str
    translated: str = ""


def normalise_source(text: str) -> str:
    text = clean_ocr_text(text)
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl")
    text = text.replace("•", " ")
    text = re.sub(
        r"^(?:(?:\(\]|\[\]|L\]|I\]|1\]|\[|\])|[•*])\s*(?=[A-Z])",
        "",
        text,
    )
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" _")


def collect_word_frequencies(document: pymupdf.Document) -> Counter[str]:
    frequencies: Counter[str] = Counter()
    for page in document:
        frequencies.update(
            word.casefold()
            for word in re.findall(r"[A-Za-z]{3,}", page.get_text())
        )
    return frequencies


def segment_is_noise(text: str, frequencies: Counter[str] | None) -> bool:
    if not text.strip():
        return True
    words = re.findall(r"[A-Za-z]{3,}", text)
    if not words:
        return not bool(re.search(r"\d\s*(?:Nm|mm|cm|bar|rpm|kW|V|A|°C)\b", text, re.IGNORECASE))
    if frequencies is None:
        return False
    candidates = [
        word.casefold()
        for word in words
        if not (word.isupper() and 2 <= len(word) <= 5)
    ]
    if not candidates:
        return False
    known = sum(
        word in COMMON_ENGLISH_WORDS or frequencies[word] >= 3
        for word in candidates
    )
    known_ratio = known / len(candidates)
    odd_case = sum(
        not (word.islower() or word.istitle() or word.isupper())
        for word in words
    )
    if len(candidates) >= 4 and known_ratio < 0.42:
        return True
    if len(candidates) >= 3 and odd_case / len(words) >= 0.45 and known_ratio < 0.70:
        return True
    return False


def clean_source_segments(text: str, frequencies: Counter[str] | None) -> str:
    # Contents and specification pages use dotted leaders.  Treat each leader
    # as a boundary so a damaged OCR tail does not poison a valid operation
    # name on the same physical line.
    pieces = re.split(r"\.{3,}|\s+[|]\s+", text)
    kept: list[str] = []
    for piece in pieces:
        # A minus sign can be a temperature, and final punctuation separates steps.
        value = normalise_source(piece).strip()
        value = re.sub(r"\s+(?:Mit|ws|w~s)$", "", value).strip()
        if not value or segment_is_noise(value, frequencies):
            continue
        kept.append(value)
    return " ".join(kept)


def looks_meaningful(text: str, line: PdfLine, page: pymupdf.Page) -> bool:
    stripped = text.strip()
    if not stripped or NOISE_RE.fullmatch(stripped):
        return False
    if line.font_size < 4.35 or line.height < 4.4:
        return False
    if line.y1 <= 32 and (
        line.x0 >= page.rect.width * 0.42
        or PAGE_HEADER_RE.search(stripped)
        or re.search(r"\brepair procedures\b", stripped, re.IGNORECASE)
    ):
        return False
    if line.y0 >= page.rect.height - 25 and re.fullmatch(r"[0-9A-Z. -]{1,16}", stripped):
        return False
    if PAGE_HEADER_RE.fullmatch(stripped):
        return False
    visible = re.findall(r"[A-Za-z0-9]", stripped)
    if len(visible) < 2:
        return False
    words = re.findall(r"[A-Za-z]+", stripped)
    if len(words) == 1 and len(words[0]) <= 4 and words[0].casefold() not in ALLOWED_SHORT_WORDS:
        return False
    if len(words) >= 2 and all(len(word) <= 3 for word in words) and not re.search(r"\d", stripped):
        return False
    if len(stripped) <= 14 and sum(char in "|/\\_~^`'\"*+=<>" for char in stripped) >= 2:
        return False
    return True


def extract_pdf_lines(page: pymupdf.Page) -> list[PdfLine]:
    data = page.get_text("dict", sort=False,
                         flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    output: list[PdfLine] = []
    seen: set[tuple[int, int, int, int, str]] = set()
    for raw_block in data.get("blocks", []):
        if raw_block.get("type") != 0:
            continue
        for raw_line in raw_block.get("lines", []):
            spans = [span for span in raw_line.get("spans", []) if str(span.get("text", "")).strip()]
            if not spans:
                continue
            text = normalise_source(" ".join(str(span["text"]) for span in spans))
            x0, y0, x1, y1 = (float(value) for value in raw_line["bbox"])
            sizes = sorted(float(span.get("size", 7.0)) for span in spans)
            font_size = sizes[len(sizes) // 2]
            fonts = " ".join(str(span.get("font", "")) for span in spans).casefold()
            flags = 0
            for span in spans:
                flags |= int(span.get("flags", 0))
            line = PdfLine(
                text=text,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                font_size=font_size,
                bold="bold" in fonts or bool(flags & 16),
                italic="italic" in fonts or "oblique" in fonts or bool(flags & 2),
            )
            key = (round(x0), round(y0), round(x1), round(y1), text.casefold())
            if key in seen:
                continue
            seen.add(key)
            output.append(line)

    # The Archive.org layer sometimes splits a visually continuous line into
    # several OCR records (often around italic words).  Merge close fragments
    # on the same baseline before paragraph grouping.  The inter-column gutter
    # is wider than this threshold, so neighbouring newspaper columns remain
    # independent.
    merged: list[PdfLine] = []
    for line in sorted(output, key=lambda item: (item.y0, item.x0)):
        # Other columns may intervene in y-order between fragments of this line.
        for index in range(len(merged) - 1, max(-1, len(merged) - 65), -1):
            previous = merged[index]
            gap = line.x0 - previous.x1
            same_baseline = abs(line.y0 - previous.y0) <= 1.4 and abs(line.y1 - previous.y1) <= 2.2
            if same_baseline and -0.8 <= gap <= 10.5:
                merged[index] = PdfLine(
                    text=normalise_source(f"{previous.text} {line.text}"),
                    x0=previous.x0,
                    y0=min(previous.y0, line.y0),
                    x1=max(previous.x1, line.x1),
                    y1=max(previous.y1, line.y1),
                    font_size=max(previous.font_size, line.font_size),
                    bold=previous.bold or line.bold,
                    italic=previous.italic or line.italic,
                )
                break
        else:
            merged.append(line)
    return [line for line in merged if looks_meaningful(line.text, line, page)]


def line_kind(line: PdfLine) -> str:
    lower = line.text.casefold()
    if re.match(r"^(?:warning|caution|note|haynes hint)\b", lower):
        return "note"
    if re.match(r"^\d{1,2}[.·]\d{1,2}[a-z]?\b", lower):
        return "caption"
    numbered_step = bool(re.match(r"^\d{1,3}\s+[A-Z]", line.text))
    heading_words = bool(
        re.match(
            r"^(?:chapter|contents|specifications|general(?: continued)?|"
            r"torque wrench settings|removal|refitting|reinstallation|"
            r"replacement|checking|inspection|dismantling|reassembly)\b",
            lower,
        )
    )
    if not numbered_step and len(line.text) <= 135 and (
        line.font_size >= 9.0 or (line.bold and line.font_size >= 7.2) or heading_words
    ):
        return "heading"
    return "text"


def horizontal_overlap(first: PdfLine | TextGroup, second: PdfLine) -> float:
    overlap = max(0.0, min(first.x1, second.x1) - max(first.x0, second.x0))
    return overlap / max(1.0, min(first.x1 - first.x0, second.width))


def can_join(group: TextGroup, line: PdfLine) -> tuple[bool, float]:
    if group.kind != line_kind(line):
        return False, float("inf")
    previous = max(group.lines, key=lambda item: item.y1)
    vertical_gap = line.y0 - previous.y1
    if vertical_gap < -1.5 or vertical_gap > max(7.5, previous.font_size * 1.05):
        return False, float("inf")
    aligned = abs(line.x0 - previous.x0) <= 24.0 or horizontal_overlap(previous, line) >= 0.38
    if not aligned:
        return False, float("inf")
    if len(group.text) + len(line.text) > 560:
        return False, float("inf")
    if (
        re.match(r"^\d{1,3}\s+[A-Z]", line.text)
        and re.search(r"[.!?]$", previous.text)
        and re.match(r"^\d{1,3}\s+", group.text)
    ):
        return False, float("inf")
    score = vertical_gap + abs(line.x0 - previous.x0) * 0.04
    return True, score


def group_lines(lines: Sequence[PdfLine]) -> list[TextGroup]:
    groups: list[TextGroup] = []
    active: list[TextGroup] = []
    for line in sorted(lines, key=lambda item: (item.y0, item.x0)):
        # Only groups close to the current baseline can accept this line.
        # Keeping the active window bounded avoids quadratic work on wiring
        # diagrams that contain thousands of tiny OCR fragments.
        active = [group for group in active if line.y0 - group.y1 <= 12.0]
        candidates: list[tuple[float, TextGroup]] = []
        # Normal prose has only a handful of simultaneous columns.  Limiting
        # the candidate tail prevents a dense diagram baseline from creating
        # another quadratic hotspot while retaining all realistic paragraphs.
        for group in active[-64:]:
            allowed, score = can_join(group, line)
            if allowed:
                candidates.append((score, group))
        if candidates:
            min(candidates, key=lambda item: item[0])[1].lines.append(line)
        else:
            group = TextGroup(line_kind(line), [line])
            groups.append(group)
            active.append(group)
    return [group for group in groups if len(group.text) >= 2]


def reading_order(groups: Sequence[TextGroup], page_width: float) -> list[TextGroup]:
    wide = sorted(
        [group for group in groups if group.width >= page_width * 0.56],
        key=lambda item: (item.y0, item.x0),
    )
    wide_ids = {id(group) for group in wide}
    narrow = sorted(
        [group for group in groups if id(group) not in wide_ids],
        key=lambda item: (item.y0, item.x0),
    )
    output: list[TextGroup] = []

    def emit_interval(interval: list[TextGroup]) -> None:
        if not interval:
            return
        thirds = [
            sorted(
                [
                    group
                    for group in interval
                    if int(min(2, group.center_x / max(1.0, page_width) * 3)) == column
                ],
                key=lambda item: (item.y0, item.x0),
            )
            for column in range(3)
        ]
        # Procedure pages commonly use three newspaper-style columns.  Reading
        # them as only left/right interleaves the middle and right procedures.
        if all(len(column) >= 2 for column in thirds):
            for column in thirds:
                output.extend(column)
            return
        left = sorted([group for group in interval if group.center_x < page_width * 0.5], key=lambda item: (item.y0, item.x0))
        right = sorted([group for group in interval if group.center_x >= page_width * 0.5], key=lambda item: (item.y0, item.x0))
        if len(left) >= 2 and len(right) >= 2:
            output.extend(left)
            output.extend(right)
        else:
            output.extend(sorted(interval, key=lambda item: (item.y0, item.x0)))

    cursor = 0
    for group in wide:
        start = cursor
        while cursor < len(narrow) and narrow[cursor].y0 < group.y0:
            cursor += 1
        emit_interval(narrow[start:cursor])
        output.append(group)
    emit_interval(narrow[cursor:])
    return output


def extract_page(
    page: pymupdf.Page,
    page_number: int,
    frequencies: Counter[str] | None = None,
) -> list[NativeBlock]:
    lines = extract_pdf_lines(page)
    groups = reading_order(group_lines(lines), page.rect.width)
    blocks: list[NativeBlock] = []
    for group in groups:
        source = clean_source_segments(group.text, frequencies)
        if len(source) < 2:
            continue
        if segment_is_noise(source, frequencies):
            continue
        words = re.findall(r"[A-Za-z]+", source)
        if group.kind in {"text", "caption"} and len(source) < 22:
            if not re.search(r"\d\s*(?:Nm|mm|cm|bar|rpm|kW|V|A|°C)\b", source, re.IGNORECASE):
                continue
        if not words and not re.search(r"\b(?:Nm|mm|cm|bar|rpm|kW|V|A|°C)\b", source, re.IGNORECASE):
            continue
        blocks.append(NativeBlock(group.kind, page_number, source))

    joined: list[NativeBlock] = []
    for block in blocks:
        if (
            joined
            and block.kind == "heading"
            and joined[-1].kind in {"text", "caption"}
            and not re.search(r"[.!?:]$", joined[-1].source)
        ):
            previous = joined[-1]
            previous.source = normalise_source(f"{previous.source} {block.source}")
            if re.match(r"^\d{1,3}\s+", previous.source) and len(previous.source) <= 150:
                previous.kind = "heading"
            continue
        joined.append(block)

    compacted: list[NativeBlock] = []
    for block in joined:
        if compacted and compacted[-1].kind == "text" and block.kind == "text":
            previous = compacted[-1]
            continues_sentence = (
                bool(block.source[:1].islower())
                or bool(re.search(r"[,;—-]$", previous.source))
                or bool(re.search(r"\b(?:a|an|and|as|at|by|for|from|in|of|on|the|to|with)$", previous.source, re.IGNORECASE))
            )
            if continues_sentence and len(previous.source) + len(block.source) <= 1600:
                previous.source = normalise_source(f"{previous.source} {block.source}")
                continue
        compacted.append(block)
    return compacted


def page_is_layout_table(page: pymupdf.Page) -> bool:
    """Reject contents/specification grids whose OCR columns are unreliable."""
    text = page.get_text()
    lower = text.casefold()
    leaders = len(re.findall(r"\.{4,}", text))
    if "torque wrench settings" in lower:
        return True
    if re.search(r"(?:^|\n)\s*contents\s*(?:\n|$)", text, re.IGNORECASE) and leaders >= 3:
        return True
    if re.search(r"(?:^|\n)\s*specifications\s*(?:\n|$)", text, re.IGNORECASE) and leaders >= 5:
        return True
    return False


def cached_page_blocks(
    page: pymupdf.Page,
    page_number: int,
    frequencies: Counter[str],
) -> list[NativeBlock]:
    SOURCE_CACHE.mkdir(parents=True, exist_ok=True)
    path = SOURCE_CACHE / f"page_{page_number:04d}.json"
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        blocks = [
            NativeBlock(str(block["kind"]), page_number, str(block["source"]))
            for block in payload.get("blocks", [])
        ]
        compacted: list[NativeBlock] = []
        for block in blocks:
            if compacted and compacted[-1].kind == "text" and block.kind == "text":
                previous = compacted[-1]
                continues_sentence = (
                    bool(block.source[:1].islower())
                    or bool(re.search(r"[,;—-]$", previous.source))
                    or bool(re.search(r"\b(?:a|an|and|as|at|by|for|from|in|of|on|the|to|with)$", previous.source, re.IGNORECASE))
                )
                if continues_sentence and len(previous.source) + len(block.source) <= 1600:
                    previous.source = normalise_source(f"{previous.source} {block.source}")
                    continue
            compacted.append(block)
        return compacted
    blocks = [] if page_is_layout_table(page) else extract_page(page, page_number, frequencies)
    path.write_text(
        json.dumps(
            {"blocks": [{"kind": block.kind, "source": block.source} for block in blocks]},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return blocks


def translate_blocks(
    blocks: Sequence[NativeBlock],
    model: Path,
    cache_path: Path,
    batch_size: int,
) -> None:
    block_units = [split_translation_units(block.source) for block in blocks]
    unique_units: list[str] = []
    seen: set[str] = set()
    for units in block_units:
        for unit in units:
            if unit and unit not in seen:
                seen.add(unit)
                unique_units.append(unit)

    engine = QuickMTTranslator(model)
    cache = TranslationCache(cache_path)
    try:
        translated: dict[str, str] = {}
        missing: list[str] = []
        for unit in unique_units:
            if len(re.findall(r"[A-Za-z]", unit)) < 2:
                translated[unit] = unit
                continue
            cached = cache.get(unit, engine.model_id)
            if cached is None:
                missing.append(unit)
            else:
                translated[unit] = enhance_translation(unit, cached)

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
            rate = done / elapsed
            print(f"translated {done}/{len(missing)} ({rate:.1f} units/s)", flush=True)

        for block, units in zip(blocks, block_units):
            value = " ".join(translated.get(unit, "") for unit in units).strip()
            block.translated = enhance_translation(block.source, value)
    finally:
        cache.close()


def native_json(block: NativeBlock) -> dict[str, object]:
    return {
        "type": block.kind,
        "page": block.page,
        "text": block.translated,
        "source": block.source,
    }


def build(
    pdf_path: Path,
    template: Path,
    output: Path,
    model: Path,
    cache: Path,
    batch_size: int,
) -> dict[str, int]:
    if output.resolve().is_relative_to(template.resolve()) or template.resolve().is_relative_to(output.resolve()):
        raise ValueError("output and template must be separate, non-overlapping directories")
    output.mkdir(parents=True, exist_ok=True)
    print("copying template assets", flush=True)
    shutil.copytree(template, output, dirs_exist_ok=True)

    index_path = output / "content_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    document = pymupdf.open(pdf_path)
    extracted: dict[str, list[NativeBlock]] = {}
    all_blocks: list[NativeBlock] = []
    try:
        print("collecting source word frequencies", flush=True)
        frequencies = collect_word_frequencies(document)
        print(f"source vocabulary: {len(frequencies)} words", flush=True)
        for section in index.get("sections", []):
            slug = str(section["slug"])
            if slug in {"about", "wiring"}:
                extracted[slug] = []
                continue
            blocks: list[NativeBlock] = []
            for page_number in range(int(section["startPage"]), int(section["endPage"]) + 1):
                if 1 <= page_number <= len(document):
                    page = document[page_number - 1]
                    if page_is_layout_table(page):
                        print(f"skipped layout table: page {page_number}", flush=True)
                        continue
                    blocks.extend(cached_page_blocks(page, page_number, frequencies))
            extracted[slug] = blocks
            all_blocks.extend(blocks)
            print(f"extracted {slug}: {len(blocks)} text blocks", flush=True)
    finally:
        document.close()

    translate_blocks(all_blocks, model, cache, batch_size)

    stats = {
        "sections": 0,
        "text_blocks": 0,
        "image_blocks": 0,
        "source_characters": 0,
    }
    for section in index.get("sections", []):
        slug = str(section["slug"])
        article_path = output / "articles" / f"{slug}.json"
        article = json.loads(article_path.read_text(encoding="utf-8"))
        old_blocks = list(article.get("blocks", []))
        if slug == "wiring":
            new_blocks = old_blocks
        else:
            curated = [block for block in old_blocks
                       if block.get("curated") and not int(block.get("page", 0))]
            reviewed_pages = {int(block["page"]) for block in old_blocks
                              if block.get("curated") and int(block.get("page", 0))}
            images_by_page: dict[int, list[dict[str, object]]] = defaultdict(list)
            for block in old_blocks:
                if block.get("type") == "image" and not block.get("curated"):
                    page_number = int(block.get("page", 0))
                    block["description"] = f"Иллюстрация из руководства, страница {page_number}"
                    images_by_page[page_number].append(block)
            text_by_page: dict[int, list[NativeBlock]] = defaultdict(list)
            for block in extracted.get(slug, []):
                text_by_page[block.page].append(block)
            pages = sorted(set(text_by_page) | set(images_by_page) | reviewed_pages)
            new_blocks = list(curated)
            for page_number in pages:
                if page_number in reviewed_pages:
                    # New extraction can change block boundaries. Keep the whole edited
                    # page in place instead of duplicating or moving its corrections.
                    new_blocks.extend(block for block in old_blocks
                                      if int(block.get("page", 0)) == page_number)
                    continue
                new_blocks.extend(native_json(block) for block in text_by_page[page_number])
                new_blocks.extend(images_by_page[page_number])

        article["blocks"] = new_blocks
        article_path.write_text(
            json.dumps(article, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        section["blockCount"] = len(new_blocks)
        section["imageCount"] = sum(block.get("type") == "image" for block in new_blocks)
        stats["sections"] += 1
        stats["text_blocks"] += sum(block.get("type") != "image" for block in new_blocks)
        stats["image_blocks"] += int(section["imageCount"])
        stats["source_characters"] += sum(
            len(str(block.get("source", ""))) for block in new_blocks
        )

    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    stats = build(args.input, args.template, args.output, args.model, args.cache, args.batch_size)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
