"""Restore source pixels and give every illustration its complete source page.

Requires the two local source PDFs and the original OCR cache. No text is
erased, even if it is English: labels are part of the technical illustration.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

import pymupdf
from PIL import Image

from build_native_content import detect_media, load_ocr_lines, render_page
from translate_haynes import DEFAULT_INPUT
from add_reference_wiring import DEFAULT_REFERENCE, render as render_wiring

ROOT = Path(__file__).resolve().parent
MANUAL = ROOT / "android-manual/app/src/main/assets"
BFQ = ROOT / "android-bfq/app/src/main/assets"


def save_page(page, destination: Path) -> None:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False,
                          colorspace=pymupdf.csRGB)
    Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(
        destination, "WEBP", quality=88, method=4)


def restore() -> None:
    by_page = defaultdict(set)
    for path in (MANUAL / "articles").glob("*.json"):
        for block in json.loads(path.read_text(encoding="utf-8"))["blocks"]:
            match = re.search(r"_(\d{4})_(\d{2})\.webp$", block.get("asset", ""))
            if match:
                by_page[int(match[1])].add((block["asset"], int(match[2])))
    sources = MANUAL / "media/source"
    sources.mkdir(exist_ok=True)
    report = []
    provenance = ROOT / "image_provenance.json"
    known = ({row["asset"]: row for row in json.loads(provenance.read_text(encoding="utf-8"))["images"]}
             if provenance.exists() else {})
    with pymupdf.open(DEFAULT_INPUT) as pdf:
        for number, assets in sorted(by_page.items()):
            page = pdf[number - 1]
            original = render_page(page)
            boxes = detect_media(original, load_ocr_lines(number))
            save_page(page, sources / f"haynes_{number:04d}.webp")
            for asset, index in sorted(assets):
                if asset in known:
                    # Reviewed crops need not match the legacy detector's
                    # region count or numbering. Their stored box is definitive.
                    rect = known[asset]["box"]
                    original.crop(rect).save(MANUAL / asset, "WEBP", quality=88, method=4)
                    report.append(dict(known[asset]))
                    continue
                old = Image.open(MANUAL / asset)
                if index > len(boxes):
                    raise ValueError(f"Missing source region for {asset}")
                box = boxes[index - 1]
                expected = (box.width, box.height)
                if box.width > 1100:
                    expected = (1100, round(box.height * 1100 / box.width))
                # Refuse silent image mis-association if the detector changes.
                # On repeat runs the saved source box is authoritative.
                if old.size != expected and asset not in known:
                    raise ValueError(f"Source region changed: {asset}: {old.size} != {expected}")
                old.close()
                # Padding retains nearby arrows and frame edges. A source-page
                # link remains available for drawings split by the old detector.
                rect = [max(0, box.x0 - 12), max(0, box.y0 - 12),
                        min(original.width, box.x1 + 12), min(original.height, box.y1 + 12)]
                if number == 254 and index == 3:
                    # Figure 2.11 includes the legend to the right of the cable.
                    rect = [30, 795, 545, 1025]
                if number == 256:
                    # One complete assembly drawing, with all 45 callouts.
                    rect = [30, 330, original.width, original.height]
                if asset in known:
                    rect = known[asset]["box"]
                crop = original.crop(rect)
                crop.save(MANUAL / asset, "WEBP", quality=88, method=4)
                report.append({"asset": asset, "page": number, "box": rect,
                               "sourceAsset": f"media/source/haynes_{number:04d}.webp"})
            print(f"Restored page {number}: {len(assets)} illustrations", flush=True)
        # Preserve tables and chapter-opening text excluded by the old pipeline.
        for path in (MANUAL / "articles").glob("*.json"):
            article = json.loads(path.read_text(encoding="utf-8"))
            if article["slug"] in {"about", "wiring", "index"}:
                continue
            for number in range(article["startPage"], article["endPage"] + 1):
                if any(b.get("page") == number and b["type"] != "image" for b in article["blocks"]):
                    continue
                if len(pdf[number - 1].get_text().strip()) > 100:
                    save_page(pdf[number - 1], sources / f"haynes_{number:04d}.webp")
    with pymupdf.open(DEFAULT_REFERENCE) as pdf:
        for path in sorted((MANUAL / "media").glob("wiring_ru_*.webp")):
            number = int(path.stem.rsplit("_", 1)[1])
            render_wiring(pdf[number - 1], number).save(path, "WEBP", quality=88, method=4)
    mapping = {row["asset"]: row["sourceAsset"] for row in report}
    for root in (MANUAL, BFQ):
        for path in (root / "articles").glob("*.json"):
            article = json.loads(path.read_text(encoding="utf-8"))
            for block in article["blocks"]:
                asset = block.get("asset", "")
                if block["type"] != "image":
                    continue
                if asset in mapping:
                    block["sourceAsset"] = mapping[asset]
                if root == BFQ:
                    shutil.copy2(MANUAL / asset, BFQ / asset)
                    if asset in mapping:
                        dest = BFQ / mapping[asset]
                        dest.parent.mkdir(exist_ok=True)
                        shutil.copy2(MANUAL / mapping[asset], dest)
            path.write_text(json.dumps(article, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (ROOT / "image_provenance.json").write_text(
        json.dumps({"source": DEFAULT_INPUT.name, "scale": 1.5, "images": report},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Restored {len(report)} source crops and all wiring sheets", flush=True)


if __name__ == "__main__":
    restore()
