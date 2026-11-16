"""Compare shipped source-linked images and page coverage with local PDFs.

This checks geometry and unaltered source pixels, not semantic translation
quality or whether every crop includes an entire figure. The separately listed
pages and block rules were reviewed visually by a human-readable source pass.
"""
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path

import pymupdf
from PIL import Image

from apply_source_review import MANUAL, BFQ, ROOT
from reviewed_source_pages import PAGES
from translate_haynes import DEFAULT_INPUT
from add_reference_wiring import DEFAULT_REFERENCE, render as render_wiring

# Visually checked blank ruled Notes pages, not missing repair instructions.
NOTES_PAGES = {40, 78, 132, 160, 172, 232, 264, 302}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def encoded(image):
    data = io.BytesIO()
    image.save(data, "WEBP", quality=88, method=4)
    return data.getvalue()


def audit():
    failures = []
    images = set()
    pages = set()
    sections = 0
    bfq_copies = set()
    provenance = {r["asset"]: r for r in json.loads((ROOT / "image_provenance.json").read_text())["images"]}
    with pymupdf.open(DEFAULT_INPUT) as pdf:
        for number in NOTES_PAGES:
            text = pdf[number - 1].get_text().strip()
            if "Notes" not in text or len(text) > 50:
                failures.append(f"Previously blank Notes page changed: {number}")
    for root in (MANUAL, BFQ):
        for path in (root / "articles").glob("*.json"):
            article = json.loads(path.read_text(encoding="utf-8"))
            sections += 1
            present = {b.get("page") for b in article["blocks"]}
            if root == MANUAL and article["slug"] not in ("wiring", "about", "index"):
                for p in range(article["startPage"], article["endPage"] + 1):
                    pages.add(p)
                    if p not in present and p not in NOTES_PAGES:
                        failures.append(f"Missing page {p}: {article['slug']}")
            for b in article["blocks"]:
                if b["type"] != "image":
                    continue
                for asset in (b["asset"], b.get("sourceAsset")):
                    if not asset:
                        continue
                    images.add(asset)
                    if root == BFQ:
                        bfq_copies.add(asset)
                        if (root / asset).read_bytes() != (MANUAL / asset).read_bytes():
                            failures.append(f"Different BFQ copy: {asset}")
    by_page = defaultdict(list)
    full_pages = {}
    wiring = []
    for asset in sorted(images):
        if asset in provenance:
            by_page[provenance[asset]["page"]].append(provenance[asset])
        elif asset.startswith("media/source/haynes_"):
            full_pages[int(Path(asset).stem.split("_")[-1])] = asset
        elif asset.startswith("media/wiring_ru_"):
            wiring.append(asset)
        else:
            failures.append(f"No source provenance: {asset}")
    with pymupdf.open(DEFAULT_INPUT) as pdf:
        for i, number in enumerate(sorted(set(by_page) | set(full_pages))):
            page = pdf[number - 1]
            if number in by_page:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False, colorspace=pymupdf.csRGB)
                source = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                for row in by_page[number]:
                    expected = encoded(source.crop(row["box"]))
                    if expected != (MANUAL / row["asset"]).read_bytes():
                        failures.append(f"Source pixels differ: {row['asset']}")
            if number in full_pages:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False, colorspace=pymupdf.csRGB)
                source = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                if encoded(source) != (MANUAL / full_pages[number]).read_bytes():
                    failures.append(f"Full source page differs: {number}")
            if (i + 1) % 50 == 0:
                print(f"Verified {i + 1} source pages", flush=True)
    with pymupdf.open(DEFAULT_REFERENCE) as pdf:
        for asset in wiring:
            number = int(Path(asset).stem.split("_")[-1])
            if encoded(render_wiring(pdf[number - 1], number)) != (MANUAL / asset).read_bytes():
                failures.append(f"Wiring source differs: {asset}")
    report = {
        "sourcePdfs": {p.name: digest(p) for p in (DEFAULT_INPUT, DEFAULT_REFERENCE)},
        "checks": {"articles": sections, "cataloguePages": len(pages),
                   "sourceCrops": sum(map(len, by_page.values())), "fullSourcePages": len(full_pages),
                   "wiringSheets": len(wiring), "bfqImageCopies": len(bfq_copies)},
        "reviewedWholePages": [{"slug": slug, "page": page} for slug, page in PAGES],
        "reviewedBlockRules": len(json.loads((ROOT / "reviewed_source_blocks.json").read_text(encoding="utf-8"))),
        "intentionallyOmittedNotesPages": sorted(NOTES_PAGES),
        "limitations": ["Automated checks cover provenance, file equality and page presence, not complete semantic accuracy.",
                        "Printed text was manually reviewed on listed pages and in source-anchored block rules.",
                        "BFQ prose is independently authored; the full manual is not a verbatim BFQ source."],
        "failures": failures,
    }
    (ROOT / "source_comparison_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["failures"]))
