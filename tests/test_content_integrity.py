"""Checks against the observed OCR, lost-page and erased-illustration bugs."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / ".tools")]

import pymupdf
from PIL import Image, ImageDraw, ImageChops, ImageStat
from build_native_content import MediaBox, OcrLine, redact_media_crop, SECTION_DEFS
from repair_content_integrity import strip_header, repair_number, split_steps
from rebuild_native_text import extract_pdf_lines, page_is_layout_table
from reviewed_automatic_transmission import blocks
from restore_manual_images import MANUAL, BFQ
from translate_haynes import DEFAULT_INPUT


class IntegrityTests(unittest.TestCase):
    def test_ocr_does_not_erase_drawing_or_label_pixels(self):
        image = Image.new("RGB", (200, 120), "white")
        draw = ImageDraw.Draw(image)
        draw.line((10, 20, 190, 100), fill="black", width=4)
        draw.text((40, 40), "H32007", fill="black")
        line = OcrLine(0, "misrecognised drawing", 20, 30, 150, 45)
        crop = redact_media_crop(image, MediaBox(10, 10, 190, 110), [line])
        self.assertEqual(crop.tobytes(), image.crop((10, 10, 190, 110)).tobytes())

    def test_running_header_removed_without_discarding_body(self):
        b = {"source": "7Be4 Automatic transmission", "text": "7Бе4 АКПП"}
        self.assertIsNone(strip_header(b, [b["source"]]))
        b = {"source": "2 Check hoses. 4De2 Emission control and exhaust systems — diesel engines",
             "text": "2 Проверьте шланги. Системы контроля выбросов и выхлопные системы — дизельные двигатели"}
        fixed = strip_header(b, [])
        self.assertEqual(fixed["source"], "2 Check hoses.")
        self.assertEqual(fixed["text"], "2 Проверьте шланги.")

    def test_figure_numbers_and_engine_displacement_are_distinct(self):
        block = {"type": "caption", "source": "6.1 Boost pressure solenoid valve", "text": "6. Клапан наддува"}
        self.assertEqual(repair_number(block)["text"], "6.1 Клапан наддува")
        engine = {"type": "text", "source": "1.6 litre SOHC engines", "text": "Двигатели SOHC объёмом 1,6 л"}
        self.assertEqual(repair_number(engine), engine)

    def test_sequential_steps_split_without_renumbering(self):
        b = {"type": "text", "source": "5 Remove cover. 6 Check cable.",
             "text": "5 Снимите крышку. 6 Проверьте трос."}
        self.assertEqual([x["text"] for x in split_steps(b)], ["5 Снимите крышку.", "6 Проверьте трос."])
        b["text"] = "5 Снимите крышку. 8 Проверьте трос."
        self.assertEqual(split_steps(b), [b])

    def test_automatic_procedure_numbers_are_complete(self):
        for section, count in ((2, 31), (4, 13), (5, 12)):
            values = [b["paragraph"] for b in blocks() if b.get("sourceSection") == section and "paragraph" in b]
            self.assertEqual(values, list(range(1, count + 1)))

    def test_reference_to_torque_settings_does_not_hide_procedure(self):
        with pymupdf.open() as doc:
            p = doc.new_page()
            p.insert_text((30, 80), "13 Remove the starter motor.")
            p.insert_text((30, 100), "Tighten to the specified torque wrench settings.")
            self.assertFalse(page_is_layout_table(p))

    def test_chapter_codes_and_ranges_match_catalogue(self):
        index = json.loads((MANUAL / "content_index.json").read_text(encoding="utf-8"))
        expected = {slug: (code, start, end) for code, slug, _, _, start, end in SECTION_DEFS}
        self.assertEqual(len(index["sections"]), len(expected))
        for section in index["sections"]:
            self.assertEqual((section["code"], section["startPage"], section["endPage"]), expected[section["slug"]])

    def test_reviewed_ocr_numbers_survive_in_shipped_content(self):
        corrections = json.loads((ROOT / "reviewed_numbering.json").read_text(encoding="utf-8"))
        for correction in corrections:
            article = json.loads((MANUAL / "articles" / (correction["slug"] + ".json")).read_text(encoding="utf-8"))
            block = next(b for b in article["blocks"] if b.get("sourceOcr") == correction["source"])
            self.assertEqual(int(re.match(r"\d+", block["text"])[0]), correction["number"])
            self.assertEqual(int(re.match(r"\d+", block["source"])[0]), correction["number"])

    def test_every_source_page_link_resolves_and_bfq_copy_matches(self):
        for root in (MANUAL, BFQ):
            for path in (root / "articles").glob("*.json"):
                for b in json.loads(path.read_text(encoding="utf-8"))["blocks"]:
                    if b["type"] != "image":
                        continue
                    self.assertTrue((root / b["asset"]).is_file())
                    if re.search(r"_\d{4}_\d{2}\.webp$", b["asset"]):
                        self.assertTrue((root / b["sourceAsset"]).is_file())
                    if root == BFQ:
                        self.assertEqual((root / b["asset"]).read_bytes(), (MANUAL / b["asset"]).read_bytes())

    @unittest.skipUnless(DEFAULT_INPUT.exists(), "Optional local original PDF")
    def test_screenshot_diagram_matches_original_pixels(self):
        with pymupdf.open(DEFAULT_INPUT) as doc:
            pix = doc[253].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            expected = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).crop((30, 795, 545, 1025))
            with Image.open(MANUAL / "media/automatic_transmission_0254_03.webp") as actual:
                self.assertEqual(actual.size, expected.size)
                # WEBP is lossy; erasing a band changes substantially more pixels.
                self.assertLess(max(ImageStat.Stat(ImageChops.difference(expected, actual.convert("RGB"))).mean), 3)

    @unittest.skipUnless(DEFAULT_INPUT.exists(), "Optional local original PDF")
    def test_screenshot_page_body_survives_extraction(self):
        with pymupdf.open(DEFAULT_INPUT) as doc:
            self.assertFalse(page_is_layout_table(doc[254]))
            lines = extract_pdf_lines(doc[255])
            self.assertFalse(any("7Be4" in l.text for l in lines))
            line = next(l for l in lines if l.text.startswith("2 This function"))
            self.assertNotIn("ignition switch", line.text)


if __name__ == "__main__":
    unittest.main()
