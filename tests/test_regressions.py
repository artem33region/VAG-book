"""Offline regression checks for content preservation and PDF rendering."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".tools"))

import pymupdf
from audit_app_quality import audit_assets
from polish_native_content import clean_text, polish, split_long_block
from repair_reviewed_content import repair
from rebuild_native_text import clean_source_segments, extract_page
import rebuild_native_text as native
from translate_haynes import TextBlock, build_pdf, fit_textbox, parse_pages
from translate_native_google import collect, rewrite_articles


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.assets = Path(self.temp.name)
        (self.assets / "articles").mkdir()

    def write_article(self, blocks, slug="sample"):
        path = self.assets / "articles" / f"{slug}.json"
        path.write_text(json.dumps({"slug": slug, "blocks": blocks}, ensure_ascii=False), encoding="utf-8")
        index = {"sections": [{"slug": slug, "blockCount": len(blocks), "imageCount": 0}]}
        (self.assets / "content_index.json").write_text(json.dumps(index), encoding="utf-8")
        return path

    def test_manual_edit_and_image_are_not_retranslated(self):
        original = [
            {"type": "text", "page": 1, "source": "An engine", "text": "Ручная редактура.", "curated": True},
            {"type": "image", "page": 1, "source": "An engine", "asset": "media/photo.webp"},
            {"type": "text", "page": 2, "source": "An engine", "text": "Старый перевод."},
        ]
        path = self.write_article(original)
        self.assertEqual(rewrite_articles([path], {"An engine": "Двигатель."}), (1, 1))
        actual = json.loads(path.read_text(encoding="utf-8"))["blocks"]
        self.assertEqual(actual[:2], original[:2])
        self.assertEqual(actual[2]["text"], "Двигатель.")

    def test_legacy_fragments_keep_their_individual_text(self):
        original = [
            {"type": "text", "page": 1, "source": "A long source", "text": "Первая часть."},
            {"type": "text", "page": 1, "source": "A long source", "text": "Вторая часть."},
        ]
        path = self.write_article(original)
        self.assertEqual(collect(self.assets)[1], [])
        self.assertEqual(rewrite_articles([path], {"A long source": "Весь текст."}), (0, 0))
        polish(self.assets)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["blocks"], original)

    def test_new_fragment_is_protected_even_when_copied_alone(self):
        parts = split_long_block({"type": "text", "source": "A long source",
                                  "text": "Первая часть. Вторая часть."}, limit=15)
        self.assertEqual(len(parts), 2)
        path = self.write_article(parts[:1])
        self.assertEqual(collect(self.assets)[1], [])
        self.assertEqual(rewrite_articles([path], {"A long source": "Весь текст."}), (0, 0))

    def test_polishing_twice_does_not_expand_split_overrides(self):
        path = self.write_article([{"type": "text", "page": 1,
                                    "source": "Original source", "text": "Исходный текст."}])
        with patch("polish_native_content.clean_text", return_value="Проверка двигателя. " * 100):
            polish(self.assets)
        first = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreater(len(first["blocks"]), 1)
        polish(self.assets)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), first)

    def test_audit_catches_empty_catalogue(self):
        (self.assets / "content_index.json").write_text('{"sections":[]}', encoding="utf-8")
        self.assertTrue(audit_assets(self.assets)[1])

    def test_audit_catches_unknown_types_and_duplicate_sections(self):
        self.write_article([{"type": "typo", "text": "Русский текст."}])
        index_path = self.assets / "content_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["sections"] *= 2
        index_path.write_text(json.dumps(index), encoding="utf-8")
        messages = [issue.message for issue in audit_assets(self.assets)[1]]
        self.assertIn("неизвестный тип блока", messages)
        self.assertIn("повтор раздела в индексе", messages)

    def test_editorial_repairs_are_repeatable_and_keep_provenance(self):
        import shutil
        for slug in ("engine_sohc", "brakes"):
            shutil.copy2(ROOT / f"android-manual/app/src/main/assets/articles/{slug}.json",
                         self.assets / "articles" / f"{slug}.json")
        repair(self.assets)
        before = {p.name: p.read_bytes() for p in (self.assets / "articles").glob("*.json")}
        self.assertEqual(repair(self.assets), 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.assets / "articles").glob("*.json")})
        article = json.loads((self.assets / "articles/engine_sohc.json").read_text(encoding="utf-8"))
        block = next(b for b in article["blocks"] if b.get("source", "").startswith("quickly in a healthy engine"))
        self.assertIn("износ поршневых колец", block["text"])
        self.assertEqual(block["page"], 62)

    def test_rebuild_rejects_nested_output_before_copying(self):
        with self.assertRaises(ValueError):
            native.build(Path("unused.pdf"), self.assets, self.assets / "nested", Path("model"), Path("cache"), 1)
        self.assertFalse((self.assets / "nested").exists())

    def test_rebuild_keeps_reviewed_page_in_place_without_duplicates(self):
        template = self.assets / "template"
        template.mkdir()
        (template / "articles").mkdir()
        original = [
            {"type": "text", "page": 0, "text": "Введение.", "curated": True},
            {"type": "text", "page": 1, "text": "Старый текст."},
            {"type": "text", "page": 2, "text": "Ручная редактура.", "source": "Old boundaries", "curated": True},
            {"type": "text", "page": 2, "text": "Продолжение страницы."},
        ]
        (template / "articles/sample.json").write_text(json.dumps({"slug": "sample", "blocks": original}), encoding="utf-8")
        index = {"sections": [{"slug": "sample", "startPage": 1, "endPage": 2}]}
        (template / "content_index.json").write_text(json.dumps(index), encoding="utf-8")
        pdf = self.assets / "source.pdf"
        with pymupdf.open() as doc:
            doc.new_page(); doc.new_page(); doc.save(pdf)
        def extract(page, number, frequencies):
            return [native.NativeBlock("text", number, "New boundaries", "Новый перевод.")]
        output = self.assets / "output"
        with patch.object(native, "cached_page_blocks", side_effect=extract), patch.object(native, "translate_blocks"):
            native.build(pdf, template, output, Path("model"), Path("cache"), 1)
        blocks = json.loads((output / "articles/sample.json").read_text(encoding="utf-8"))["blocks"]
        self.assertEqual([b["page"] for b in blocks], [0, 1, 2, 2])
        self.assertEqual(blocks[2:], original[2:])
        self.assertEqual(blocks[1]["text"], "Новый перевод.")


class PdfTests(unittest.TestCase):
    def test_extraction_preserves_piston_ring_diagnosis(self):
        if not (ROOT / "Haynes_VW_Golf_&_Bora_Service_and_Repair_Manual_A_K_Legg,_Peter.pdf").exists():
            self.skipTest("Optional local source PDF is not included in the repository")
        with pymupdf.open(ROOT / "Haynes_VW_Golf_&_Bora_Service_and_Repair_Manual_A_K_Legg,_Peter.pdf") as source:
            text = " ".join(block.source for block in extract_page(source[61], 62))
            self.assertIn("indicates worn piston rings.", text)

    def test_source_cleanup_preserves_signed_values_and_sentence_end(self):
        self.assertEqual(clean_source_segments("-20 °C", None), "-20 °C")
        self.assertEqual(clean_source_segments("Check the engine.", None), "Check the engine.")
        self.assertEqual(clean_text("-20 °C", "-20 °C", "text"), "-20 °C")

    def test_reversed_range_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_pages("8-3", 10)
        self.assertEqual(parse_pages("3-5,1,3", 10), [0, 2, 3, 4])

    def test_preflight_does_not_draw_text(self):
        with pymupdf.open() as doc:
            page = doc.new_page(width=200, height=200)
            self.assertTrue(fit_textbox(page, pymupdf.Rect(10, 10, 190, 80), "Translation", "helv", 12, commit=False)[0])
            self.assertEqual(page.get_text(), "")

    def test_failed_translation_keeps_visible_original(self):
        with tempfile.TemporaryDirectory() as directory, pymupdf.open() as source:
            page = source.new_page(width=200, height=200)
            page.insert_text((20, 30), "ORIGINAL", fontsize=9)
            rect = pymupdf.Rect(18, 18, 80, 35)
            block = TextBlock(0, rect, "ORIGINAL", 9, False, False)
            translation = {(0, *tuple(rect)): "Очень длинный перевод. " * 300}
            output = Path(directory) / "result.pdf"
            before = page.get_pixmap().samples
            self.assertEqual(build_pdf(source, [0], [block], translation, output), (0, 0, 1))
            with pymupdf.open(output) as result:
                self.assertEqual(result[0].get_pixmap().samples, before)

    def test_successful_translation_is_rendered(self):
        with tempfile.TemporaryDirectory() as directory, pymupdf.open() as source:
            page = source.new_page(width=200, height=200)
            rect = pymupdf.Rect(10, 10, 190, 80)
            block = TextBlock(0, rect, "Engine", 12, False, False)
            output = Path(directory) / "result.pdf"
            self.assertEqual(build_pdf(source, [0], [block], {(0, *tuple(rect)): "Двигатель"}, output), (1, 0, 0))
            with pymupdf.open(output) as result:
                self.assertIn("Двигатель", result[0].get_text())


if __name__ == "__main__":
    unittest.main()
