#!/usr/bin/env python3
"""Replace sparse Haynes wiring crops with full Russian reference diagrams."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pymupdf
from PIL import Image


ROOT = Path(__file__).resolve().parent
DEFAULT_REFERENCE = ROOT / "VW Golf4 Bora Jetta 1997-2005-1.pdf"
DEFAULT_ASSETS = ROOT / ".work" / "native_content" / "generated_assets"


def render(page: pymupdf.Page, page_number: int, scale: float = 2.0) -> Image.Image:
    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(scale, scale),
        colorspace=pymupdf.csRGB,
        alpha=False,
    )
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    # Edge labels and continuation connectors belong to the wiring diagram.
    # Preserve the whole scanned page, including its margins.
    if page_number >= 483:
        image = image.transpose(Image.Transpose.ROTATE_270)
    return image


def add_wiring(reference: Path, assets: Path, start: int, end: int) -> dict[str, int]:
    media_dir = assets / "media"
    article_path = assets / "articles" / "wiring.json"
    payload = json.loads(article_path.read_text(encoding="utf-8"))
    curated = [
        block
        for block in payload.get("blocks", [])
        if block.get("curated") and int(block.get("page", 0)) == 0
    ]

    old_assets = {
        str(block.get("asset"))
        for block in payload.get("blocks", [])
        if block.get("type") == "image" and str(block.get("asset", "")).startswith("media/wiring_")
    }
    for asset in old_assets:
        path = assets / asset
        if path.is_file():
            path.unlink()

    blocks = list(curated)
    document = pymupdf.open(reference)
    try:
        for sheet, page_number in enumerate(range(start, end + 1), 1):
            if page_number < 1 or page_number > len(document):
                raise ValueError(f"reference page outside PDF: {page_number}")
            image = render(document[page_number - 1], page_number)
            asset_name = f"wiring_ru_{page_number:04d}.webp"
            image.save(media_dir / asset_name, "WEBP", quality=84, method=5)
            blocks.extend(
                [
                    {
                        "type": "heading",
                        "page": page_number,
                        "text": f"Электрическая схема — лист {sheet}",
                        "curated": True,
                    },
                    {
                        "type": "image",
                        "page": page_number,
                        "asset": f"media/{asset_name}",
                        "description": f"Русская электрическая схема, лист {sheet}",
                        "curated": True,
                    },
                ]
            )
    finally:
        document.close()

    payload["blocks"] = blocks
    article_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    index_path = assets / "content_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for section in index.get("sections", []):
        if section.get("slug") == "wiring":
            section["blockCount"] = len(blocks)
            section["imageCount"] = end - start + 1
            break
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "reference_pages": end - start + 1,
        "old_haynes_assets_removed": len(old_assets),
        "wiring_blocks": len(blocks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--start", type=int, default=481)
    parser.add_argument("--end", type=int, default=510)
    args = parser.parse_args()
    print(json.dumps(add_wiring(args.reference, args.assets, args.start, args.end), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
