"""Apply the second printed-source review without re-running translation.

Reviewed replacements are anchored to original English text or PDF pages.
Repeat runs are idempotent. Image crops use the original scan, without redaction.
"""
import json
import re
import shutil
from pathlib import Path

from reviewed_source_pages import PAGES, blocks_for

ROOT = Path(__file__).resolve().parent
MANUAL = ROOT / "android-manual/app/src/main/assets"
BFQ = ROOT / "android-bfq/app/src/main/assets"
REVIEW = "printed-pdf-v2"

# Coordinates in the original 1.5x rendering, checked visually against the scan.
FIGURES = {
27: [(5, 70, 790, 515, "Вид днища сзади — двигатель 1,4 л; позиции 1–8")],
77: [(5, 65, 260, 290, "22.4a Отжатие натяжителя отвёрткой"),
     (270, 65, 520, 290, "22.4b Фиксация натяжителя шестигранным ключом 3 мм"),
     (525, 65, 795, 290, "22.8 Метка и фиксирующий штифт VW T10060")],
90: [(295, 70, 550, 285, "6.21a Нижние крепёжные болты кожуха"),
     (550, 70, 812, 285, "6.21b Снятие нижнего кожуха — двигатель 1,8 л"),
     (40, 595, 295, 810, "7.9a Шланг адсорбера на бачке гидроусилителя"),
     (295, 595, 555, 810, "7.9b Винт крепления бачка"),
     (555, 595, 812, 810, "7.9c Бачок отведён из рабочей зоны"),
     (40, 810, 295, 1035, "7.10a Винты расширительного бачка"),
     (295, 810, 555, 1035, "7.10b Расширительный бачок отведён"),
     (555, 810, 812, 1035, "7.12a Снятие малого кронштейна")],
115: [(5, 70, 260, 300, "3.7a Отворачивание контрольной пробки большой гайкой"),
      (270, 70, 520, 300, "3.7b Резиновая заглушка картера; воздушный фильтр снят"),
      (525, 70, 795, 315, "3.7c Метка маховика совмещена с указателем картера МКПП"),
      (270, 835, 520, 1035, "3.9 Фиксаторы распределительного вала и звёздочки ТНВД"),
      (525, 820, 795, 1040, "3.10a Проверка положения паза распределительного вала линейкой")],
186: [(10, 390, 548, 812, "10.6 Впускной коллектор DOHC 1,4 л — позиции 1–13"),
      (40, 810, 290, 1035, "10.8a Ослабление болта впускного коллектора"),
      (295, 810, 550, 1035, "10.8b Снятие впускного коллектора — двигатель DOHC 1,4 л")],
159: [(265, 65, 520, 285, "20.17a Затяжка крепления крышки шатунного подшипника моментом"),
      (525, 65, 790, 285, "20.17b Доворот крепления на указанный угол")],
229: [(255, 65, 510, 275, "3.4a Гайка крепления держателя предохранителей"),
      (515, 65, 780, 275, "3.4b Освобождение кронштейна"),
      (255, 285, 510, 495, "3.5 Отсоединение положительного провода аккумулятора"),
      (515, 285, 780, 495, "3.6 Болт прижима аккумулятора"),
      (5, 810, 255, 1020, "5.3 Двухконтактный разъём генератора"),
      (260, 810, 515, 1020, "5.5 Отсоединение положительного провода генератора")],
}


def parse_parts(text, page, rule_id):
    # Reuse the same markup conventions as the full-page review.
    if not text.strip():
        return []
    if not text.strip():
        return []
    result = []
    for part in text.strip().split("\n\n"):
        kind = {"# ": "heading", "! ": "note", "> ": "caption"}.get(part[:2], "text")
        value = part[2:] if kind != "text" else part
        b = dict(type=kind, page=page, text=value, curated=True, layoutReviewed=True,
                 sourceReview=REVIEW, reviewId=rule_id)
        if kind == "text" and re.match(r"^\d+\. ", value):
            b["role"] = "steps"
        elif kind == "text" and re.search(r"(?m)^(?:[a-z]\)|•) ", value):
            b["role"] = "bullets"
        result.append(b)
    return result


def reviewed_images(page):
    images = [dict(type="image", page=page, asset=f"media/reviewed_{page:04d}_{i:02d}.webp",
                   sourceAsset=f"media/source/haynes_{page:04d}.webp", description=fig[4],
                   sourceReview=REVIEW)
              for i, fig in enumerate(FIGURES.get(page, []), 1)]
    images.append(dict(type="image", page=page, asset=f"media/source/haynes_{page:04d}.webp",
                       description=f"Полная страница {page} оригинала (английский текст)", sourceReview=REVIEW))
    return images


def apply_blocks(slug, blocks, rules):
    result = []
    seen_pages = set()
    for b in blocks:
        page = b.get("page", 0)
        if (slug, page) in PAGES:
            if page not in seen_pages:
                seen_pages.add(page)
                reviewed = blocks_for(slug, page)
                for correction in json.loads((ROOT / "reviewed_numbering.json").read_text(encoding="utf-8")):
                    if (correction["slug"], correction["page"]) == (slug, page):
                        matching = [x for x in reviewed if x.get("role") == "steps"
                                    and x["text"].startswith(str(correction["number"]) + ". ")]
                        if len(matching) != 1:
                            raise ValueError(f"Ambiguous reviewed paragraph: {correction}")
                        matching[0]["sourceOcr"] = correction["source"]
                        matching[0]["source"] = re.sub(r"^\d+", str(correction["number"]), correction["source"])
                previous = [x for x in blocks if x.get("page") == page]
                provenance = next((x["sourceOcrBlocks"] for x in previous if "sourceOcrBlocks" in x), None)
                reviewed[0]["sourceOcrBlocks"] = provenance or [x["source"] for x in previous if x.get("source")]
                result.extend(reviewed)
                result.extend(reviewed_images(page))
            continue
        rule = next((r for r in rules if r["slug"] == slug and r["page"] == page
                     and r["source"] == b.get("source") and b.get("sourceReview") != REVIEW), None)
        if rule:
            parts = parse_parts(rule["replacement"], page, rule["id"])
            if parts:
                parts[0]["source"] = b["source"]
            result.extend(parts)
        else:
            result.append(b)
    return result


def render_images():
    import pymupdf
    from PIL import Image
    from translate_haynes import DEFAULT_INPUT
    from restore_manual_images import save_page
    report = json.loads((ROOT / "image_provenance.json").read_text(encoding="utf-8"))
    by_asset = {row["asset"]: row for row in report["images"]}
    with pymupdf.open(DEFAULT_INPUT) as pdf:
        for _, number in PAGES:
            page = pdf[number - 1]
            save_page(page, MANUAL / f"media/source/haynes_{number:04d}.webp")
            pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            original = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            for i, fig in enumerate(FIGURES.get(number, []), 1):
                asset = f"media/reviewed_{number:04d}_{i:02d}.webp"
                rect = list(fig[:4])
                if not (0 <= rect[0] < rect[2] <= original.width and 0 <= rect[1] < rect[3] <= original.height):
                    raise ValueError((number, rect, original.size))
                original.crop(rect).save(MANUAL / asset, "WEBP", quality=88, method=4)
                by_asset[asset] = dict(asset=asset, page=number, box=rect, scale=1.5,
                                      sourceAsset=f"media/source/haynes_{number:04d}.webp", sourceReview=REVIEW)
    report["images"] = list(by_asset.values())
    (ROOT / "image_provenance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def apply():
    rules = json.loads((ROOT / "reviewed_source_blocks.json").read_text(encoding="utf-8"))
    changed = []
    for root in (MANUAL, BFQ):
        index_path = root / "content_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for section in index["sections"]:
            path = root / "articles" / (section["slug"] + ".json")
            article = json.loads(path.read_text(encoding="utf-8"))
            old = article["blocks"]
            # BFQ prose is independently authored; source-linked image copies
            # still have to stay identical to the general manual.
            if root == MANUAL:
                new = apply_blocks(section["slug"], old, rules)
            else:
                new = []
                rear_view_added = False
                for block in old:
                    if block.get("asset", "").startswith("media/maintenance_petrol_0027_"):
                        if not rear_view_added:
                            rear_view_added = True
                            new.append(dict(type="image", page=0, asset="media/reviewed_0027_01.webp",
                                            sourceAsset="media/source/haynes_0027.webp",
                                            description="Компоновка днища Golf/Bora: в оригинале показана модель 1,4 л",
                                            sourceReview=REVIEW))
                    else:
                        new.append(block)
                for block in new:
                    if block["type"] == "text" and not block.get("source") and re.match(r"^\d+\. ", block["text"]):
                        block["role"] = "steps"
            if new != old:
                changed.append(section["slug"])
            article["blocks"] = new
            path.write_text(json.dumps(article, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            section["blockCount"] = len(new)
            section["imageCount"] = sum(b["type"] == "image" for b in new)
            if root == BFQ:
                for b in new:
                    if b["type"] == "image":
                        for asset in (b["asset"], b.get("sourceAsset")):
                            if asset:
                                shutil.copy2(MANUAL / asset, BFQ / asset)
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


if __name__ == "__main__":
    render_images()
    print(json.dumps(apply(), ensure_ascii=False))
