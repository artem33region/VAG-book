"""Regressions for short 7B steps, chapter titles and figure/procedure separation."""
import json
import re
import unittest
from pathlib import Path

from format_article_layout import format_lists
from repair_step_layout import ROOTS, apply_structure_blocks, load_rules
from reviewed_automatic_transmission import blocks as automatic_blocks

ROOT = Path(__file__).resolve().parents[1]


class StepStructureTests(unittest.TestCase):
    def test_short_editorial_steps_have_same_style_as_long_steps(self):
        block = dict(type="text", text="3 Установите селектор в P.", paragraph=3, curated=True)
        result = format_lists(block)
        self.assertEqual((result["role"], result["text"]), ("steps", "3. Установите селектор в P."))
        self.assertEqual(format_lists(result), result)

    def test_less_common_source_openings_and_references(self):
        for source, text in [
            ("7 Undo the bolt.", "7 Отверните болт."),
            ("8 Refitting is a reversal of removal.", "8 Установка выполняется в обратном порядке."),
            ("9 Using a spanner, turn the bolt.", "9 Поверните болт ключом."),
            ("10 Reconnect the cable, see Section 2 Removal.", "10 Подключите трос; см. раздел 2 Снятие."),
            ("22 |f the connection is faulty, clean it.", "22 Если соединение неисправно, очистите его."),
        ]:
            b = dict(type="text", source=source, text=text)
            fixed = format_lists(b)
            self.assertEqual(fixed["role"], "steps")
            self.assertEqual(format_lists(fixed), fixed)

    def test_quantities_captions_and_unreviewed_titles_are_not_steps(self):
        for kind, source, text in [
            ("text", "20 Nm", "20 Н·м"),
            ("text", "1.4 litre engines", "Двигатели 1,4 л"),
            ("caption", "2.3 Remove the cable", "2.3 Отсоединение троса"),
            ("text", "3 Oil pump", "3 Масляный насос"),
            ("text", "3 Hydraulic system bleeding", "3 Прокачка гидропривода"),
        ]:
            self.assertNotEqual(format_lists(dict(type=kind, source=source, text=text)).get("role"), "steps")

    def test_multiline_step_normalization_is_immediately_idempotent(self):
        b = dict(type="text", source="9 Lubricate the bore. 10 Begin with piston No 1.",
                 text="9 Смажьте отверстие.\n10 Начните с поршня № 1.")
        result = format_lists(b)
        self.assertIn("\n10.", result["text"])
        self.assertEqual(format_lists(result), result)

    def test_7b_generator_and_shipped_steps_are_complete_and_styled(self):
        article = json.loads((ROOTS[0] / "articles/automatic_transmission.json").read_text(encoding="utf-8"))
        for corpus in [automatic_blocks(), article["blocks"]]:
            for section, count in [(2, 31), (4, 13), (5, 12)]:
                steps = [b for b in corpus if b.get("sourceSection") == section and "paragraph" in b]
                self.assertEqual([b["paragraph"] for b in steps], list(range(1, count + 1)))
                for b in steps:
                    self.assertEqual(b.get("role"), "steps", b["text"])
                    self.assertTrue(b["text"].startswith(str(b["paragraph"]) + ". "))

    def test_all_apps_have_no_unstyled_numbered_prose(self):
        for root in ROOTS:
            for path in (root / "articles").glob("*.json"):
                blocks = json.loads(path.read_text(encoding="utf-8"))["blocks"]
                for b in blocks:
                    if b["type"] == "text" and re.match(r"^\d{1,3}[.)]?\s+[А-ЯЁ]", b.get("text", "")):
                        self.assertIn(b.get("role"), ("steps", "legend", "bullets"), (path.name, b["text"]))

    def test_source_rules_keep_titles_and_figure_keys_separate(self):
        for rule in load_rules():
            for replacement in rule["replacements"]:
                if replacement.get("role") == "legend":
                    for line in replacement["text"].splitlines():
                        self.assertRegex(line, r"^\d+\. \S.+", line)
            block = dict(type="text", page=rule["page"], source=rule["source"],
                         text=rule.get("matchText", "исходный перевод"))
            fixed = apply_structure_blocks(rule["slug"], [block])
            self.assertEqual(apply_structure_blocks(rule["slug"], fixed), fixed)
            self.assertEqual(len(fixed), len(rule["replacements"]))
        for root in ROOTS:
            for path in (root / "articles").glob("*.json"):
                blocks = json.loads(path.read_text(encoding="utf-8"))["blocks"]
                self.assertEqual(apply_structure_blocks(path.stem, blocks, None if root == ROOTS[0] else []), blocks)

    def test_reviewed_ocr_numbers_and_mixed_columns(self):
        def article(slug):
            return json.loads((ROOTS[0] / "articles" / (slug + ".json")).read_text(encoding="utf-8"))["blocks"]
        for page in [309, 311]:
            step = next(b for b in article("bodywork") if b.get("page") == page and b.get("source", "").startswith("41 "))
            self.assertTrue(step["text"].startswith("11. "))
        b = next(b for b in article("maintenance_petrol") if b.get("source", "").startswith("1 Crankshaft pulley 2 Tensioner 7 Locate"))
        self.assertEqual(b["role"], "legend")
        self.assertNotIn("7 ", b["text"])
        steps = [b for b in article("fuel_diesel") if b.get("page") == 197 and b.get("text", "").startswith("17.")]
        self.assertEqual(len(steps), 1)
        self.assertIn("T10055", steps[0]["text"])
        self.assertIn("замените их новыми", steps[0]["text"])
        label = next(b for b in article("emissions_petrol") if b.get("source", "").startswith("171 Flexible section"))
        self.assertEqual([int(n) for n in re.findall(r"(?m)^(\d+)\.", label["text"])], [11, 12, 13, 14, 15])
        self.assertIn("Датчик кислорода № 1", label["text"])


if __name__ == "__main__":
    unittest.main()
