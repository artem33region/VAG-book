"""Source-guided list formatting and the reported diesel chapter regressions."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / ".tools")]

from format_article_layout import format_lists, merge_note_continuations, separate_all_headings, review_diesel
from polish_native_content import clean_text
from translate_native_google import translatable_blocks
from reviewed_layout_fixes import reviewed_fixes
from reviewed_layout_fixes import reviewed_fixes


class ArticleLayoutTests(unittest.TestCase):
    def block(self, text, source="", **kwargs):
        return dict(type="text", page=1, text=text, source=source, **kwargs)

    def test_legend_has_one_numbered_part_per_line(self):
        b = self.block("1 Впускной коллектор 2 Прокладка 3 Болт", "1 Inlet manifold 2 Gasket 3 Bolt")
        fixed = format_lists(b)
        self.assertEqual(fixed["role"], "legend")
        self.assertEqual(fixed["text"], "1. Впускной коллектор\n2. Прокладка\n3. Болт")
        self.assertEqual(format_lists(fixed), fixed)

    def test_instructions_are_not_figure_legends(self):
        fixed = format_lists(self.block("1 Снимите кожух. 2 Отсоедините разъём.", "1 Remove cover. 2 Disconnect connector."))
        self.assertEqual(fixed["role"], "steps")
        self.assertIn("\n\n2.", fixed["text"])

    def test_units_engine_codes_and_cross_references_are_preserved(self):
        for text, source in [
            ("Двигатели 1,6 и 2,0 л", "1.6 and 2.0 litre engines"),
            ("Затяните до 30 Н·м и доверните на 90°.", "Tighten to 30 Nm and turn 90 degrees."),
            ("См. главу 2 и раздел 3.", "See Chapter 2 and Section 3."),
        ]:
            b = self.block(text, source)
            self.assertEqual(format_lists(b), b)

    def test_cyrillic_translated_list_markers_are_recovered(self):
        b = self.block("а Снимите кожух. б Проверьте трос. в Установите кожух.",
                       "a) Remove cover. b) Check cable. c) Refit cover.")
        fixed = format_lists(b)
        self.assertEqual(fixed["text"], "a) Снимите кожух.\n\nb) Проверьте трос.\n\nc) Установите кожух.")

    def test_parenthetical_figure_letter_is_not_a_list(self):
        b = self.block("Проверьте зазор (c) на рисунке.", "Check clearance (c) on illustration.")
        self.assertEqual(format_lists(b), b)

    def test_reviewed_ocr_symbols_and_brake_sequence(self):
        caption = dict(type="caption", text="4.9¢ Разъёмы проводки", source="4.9¢ Wiring plugs")
        self.assertEqual(reviewed_fixes(caption)[0]["text"], "4.9c Разъёмы проводки")
        checkbox = self.block("C Измерение дымности", "C] The only emission test for diesel engines")
        self.assertEqual(reviewed_fixes(checkbox)[0]["text"], "• Измерение дымности")
        brake = self.block("", "12 If the complete system is to be bled")
        fixed = reviewed_fixes(brake)[0]
        first, second = fixed["text"].split("Система MK60:")
        self.assertIn("a) Правый задний", first)
        self.assertIn("a) Левый передний", second)
        self.assertEqual(reviewed_fixes(fixed), [fixed])

    def test_reviewed_ocr_symbols_and_brake_sequence(self):
        caption = dict(type="caption", text="4.9¢ Разъёмы проводки", source="4.9¢ Wiring plugs")
        self.assertEqual(reviewed_fixes(caption)[0]["text"], "4.9c Разъёмы проводки")
        checkbox = self.block("C Измерение дымности", "C] The only emission test for diesel engines")
        self.assertEqual(reviewed_fixes(checkbox)[0]["text"], "• Измерение дымности")
        brake = self.block("", "12 If the complete system is to be bled")
        fixed = reviewed_fixes(brake)[0]
        first, second = fixed["text"].split("Система MK60:")
        self.assertIn("a) Правый задний", first)
        self.assertIn("a) Левый передний", second)
        self.assertEqual(reviewed_fixes(fixed), [fixed])

    def test_cleanup_preserves_list_parentheses_and_line_breaks(self):
        text = "a) Проверьте трос.\n\nb) Установите крышку."
        self.assertEqual(clean_text("a) Check cable. b) Refit cover.", text, "text"),
                         "A) Проверьте трос.\n\nb) Установите крышку.")

    def test_only_incomplete_notes_join_with_their_continuation(self):
        note = dict(type="note", page=1, text="Примечание: потребуется", source="Note: A suitable tool will be")
        continuation = self.block("подходящий инструмент.", "required for this operation.")
        self.assertEqual(len(merge_note_continuations([note, continuation])), 1)
        step = self.block("1 Снимите крышку.", "1 Remove the cover.")
        self.assertEqual(len(merge_note_continuations([note, step])), 2)
        complete = dict(note, source="Note: Use a new seal", text="Примечание: замените уплотнение.")
        self.assertEqual(len(merge_note_continuations([complete, continuation])), 2)

    def test_heading_is_separate_from_instruction_and_model_name(self):
        b = self.block("5 Снимите кожух. Модели без турбонаддува 6 Отсоедините шланг.",
                       "5 Remove cover. Non-turbo models 6 Disconnect hose.")
        result = separate_all_headings(b)
        self.assertEqual([b["type"] for b in result], ["text", "heading", "text"])
        self.assertEqual(result[1]["text"], "Модели без турбонаддува")
        self.assertEqual(result[-1]["source"], "6 Disconnect hose.")

    def test_layout_blocks_are_not_retranslated(self):
        b = self.block("1. Болт\n2. Гайка", "1 Bolt 2 Nut", role="legend")
        self.assertEqual(list(translatable_blocks({"blocks": [b]})), [])

    def test_screenshot_pages_have_complete_note_and_numbered_legends(self):
        path = ROOT / "android-manual/app/src/main/assets/articles/emissions_diesel.json"
        blocks = json.loads(path.read_text(encoding="utf-8"))["blocks"]
        note = next(b for b in blocks if b["type"] == "note" and "AGR" in b["text"] and b.get("page") == 221)
        self.assertIn("кроме AGR", note["text"])
        self.assertIn("выпускным коллектором", note["text"])
        for figure, count in [("3.17", 10), ("5.11", 31), ("5.14", 25), ("6.3a", 4)]:
            legend = next(b for b in blocks if b.get("figure") == figure)
            self.assertEqual([int(re.match(r"\d+", line)[0]) for line in legend["text"].splitlines()], list(range(1, count + 1)))
        legend = next(b for b in blocks if b.get("figure") == "5.14")
        self.assertTrue(legend["text"].startswith("1. Выпускной коллектор\n2. Впускной коллектор"))
        image = next(b for b in blocks if b.get("asset", "").endswith("emissions_diesel_0223_02.webp"))
        self.assertTrue(image["description"].startswith("Рисунок 5.14."))
        self.assertEqual(review_diesel(review_diesel(blocks)), review_diesel(blocks))

    def test_shared_reader_typography_is_identical(self):
        suffix = "app/src/main/java/ru/vagguides/golf4manual/ArticleTypography.java"
        self.assertEqual((ROOT / "android-manual" / suffix).read_bytes(), (ROOT / "android-bfq" / suffix).read_bytes())
        self.assertEqual((ROOT / "android-manual" / suffix).read_bytes(), (ROOT / "android-bca" / suffix).read_bytes())


if __name__ == "__main__":
    unittest.main()
