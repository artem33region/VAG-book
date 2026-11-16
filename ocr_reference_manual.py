#!/usr/bin/env python3
"""OCR the Russian Golf/Bora/Jetta reference manual into a resumable corpus."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "VW Golf4 Bora Jetta 1997-2005-1.pdf"
DEFAULT_CACHE = ROOT / ".work" / "ru_reference_ocr"
DEFAULT_CORPUS = ROOT / ".work" / "ru_reference_corpus.txt"
OCR_SCRIPT = ROOT / "windows_ocr.ps1"


def recognize_page(
    page_number: int,
    image_path: Path,
    cache_path: Path,
    language: str,
) -> tuple[int, int]:
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(OCR_SCRIPT),
                str(image_path),
                language,
            ],
            check=True,
            capture_output=True,
        )
        items = json.loads(completed.stdout.decode("utf-8-sig"))
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            raise ValueError("OCR result is not a JSON array")
        temporary = cache_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        temporary.replace(cache_path)
        return page_number, len(items)
    finally:
        image_path.unlink(missing_ok=True)


def build_corpus(cache_dir: Path, page_count: int, output: Path) -> tuple[int, int]:
    sections: list[str] = []
    line_count = 0
    character_count = 0
    for page_number in range(1, page_count + 1):
        cache_path = cache_dir / f"page_{page_number:04d}.json"
        items = json.loads(cache_path.read_text(encoding="utf-8-sig"))
        lines = [str(item.get("text", "")).strip() for item in items]
        lines = [line for line in lines if line]
        text = "\n".join(lines)
        line_count += len(lines)
        character_count += len(text)
        sections.append(f"\n=== PAGE {page_number} ===\n{text}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(sections).lstrip(), encoding="utf-8")
    return line_count, character_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--language", default="ru-RU")
    parser.add_argument("--scale", type=float, default=1.7)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    for required in (args.input, OCR_SCRIPT):
        if not required.exists():
            parser.error(f"required file not found: {required}")
    if args.workers < 1 or args.workers > 6:
        parser.error("--workers must be between 1 and 6")

    args.cache.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(args.input)
    total = document.page_count
    cached = sum((args.cache / f"page_{number:04d}.json").exists() for number in range(1, total + 1))
    completed_count = cached
    new_started = time.monotonic()
    print(f"pages={total}, cached={cached}, workers={args.workers}", flush=True)

    pending: dict[Future[tuple[int, int]], int] = {}

    def collect_one() -> None:
        nonlocal completed_count
        done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
        for future in done:
            page_number = pending.pop(future)
            try:
                _, lines = future.result()
            except Exception as exc:
                raise RuntimeError(f"OCR failed on page {page_number}: {exc}") from exc
            completed_count += 1
            new_done = completed_count - cached
            elapsed = max(0.001, time.monotonic() - new_started)
            rate = new_done / elapsed
            remaining = (total - completed_count) / rate if rate else 0.0
            print(
                f"ocr {completed_count}/{total}: page {page_number}, {lines} lines "
                f"({rate:.2f} pages/s, ETA {remaining / 60:.1f} min)",
                flush=True,
            )

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for page_index in range(total):
            page_number = page_index + 1
            cache_path = args.cache / f"page_{page_number:04d}.json"
            if cache_path.exists():
                continue
            while len(pending) >= args.workers * 2:
                collect_one()
            image_path = args.cache / f"page_{page_number:04d}.jpg"
            pixmap = document[page_index].get_pixmap(
                matrix=pymupdf.Matrix(args.scale, args.scale),
                colorspace=pymupdf.csRGB,
                alpha=False,
            )
            pixmap.save(image_path, jpg_quality=92)
            future = executor.submit(
                recognize_page,
                page_number,
                image_path,
                cache_path,
                args.language,
            )
            pending[future] = page_number
        while pending:
            collect_one()

    line_count, character_count = build_corpus(args.cache, total, args.corpus)
    print(
        f"saved {args.corpus} | pages={total}, lines={line_count}, chars={character_count}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
