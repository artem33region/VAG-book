"""Regressions for second printed-source comparison, including semantic errors."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apply_source_review import apply_blocks, parse_parts, FIGURES
from reviewed_source_pages import PAGES, blocks_for
from audit_app_quality import source_term_conflicts
from audit_app_quality import source_term_conflicts


class SourceReviewTests(unittest.TestCase):
    def test_source_audit_detects_opposite_terms_without_rewriting_them(self):
        self.assertEqual(source_term_conflicts("Hold the camshaft", "Удерживайте коленчатый вал"), ["camshaft"])
        self.assertEqual(source_term_conflicts("Exhaust manifold", "Впускной коллектор"), ["exhaust manifold"])
        self.assertEqual(source_term_conflicts("Align camshaft and crankshaft", "Совместите распределительный и коленчатый валы"), [])

    def test_source_audit_detects_opposite_terms_without_rewriting_them(self):
        self.assertEqual(source_term_conflicts("Hold the camshaft", "Удерживайте коленчатый вал"), ["camshaft"])
        self.assertEqual(source_term_conflicts("Exhaust manifold", "Впускной коллектор"), ["exhaust manifold"])
        self.assertEqual(source_term_conflicts("Align camshaft and crankshaft", "Совместите распределительный и коленчатый валы"), [])

    def page(self, slug, page):
        path = ROOT / f"android-manual/app/src/main/assets/articles/{slug}.json"
        return [b for b in json.loads(path.read_text(encoding="utf-8"))["blocks"] if b.get("page") == page]

    def test_brake_warning_is_complete_and_keeps_negation(self):
        rows = self.page("maintenance_diesel", 57)
        note = next(b["text"] for b in rows if b["type"] == "note" and "тормозная жидкость" in b["text"])
        self.assertIn("Не используйте", note)
        self.assertIn("открытой ёмкости", note)
        self.assertIn("влагу", note)

    def test_diesel_compression_and_camshaft_are_not_reversed(self):
        rows = self.page("engine_diesel", 115)
        diagnostic = next(b["text"] for b in rows if "Низкое давление на первом" in b.get("text", ""))
        self.assertIn("износ поршневых колец", diagnostic)
        locking = next(b["text"] for b in rows if b.get("text", "").startswith("9. Зафиксируйте"))
        self.assertIn("распределительный вал", locking)
        self.assertNotIn("коленчатый вал", locking)

    def test_balance_shaft_steps_are_complete(self):
        rows = self.page("engine_sohc", 77)
        start = next(i for i,b in enumerate(rows) if b.get("text", "").startswith("22 Узел"))
        numbers = [int(re.match(r"\d+", b["text"])[0]) for b in rows[start:] if b.get("role") == "steps"]
        self.assertEqual(numbers, list(range(1,15)))
        self.assertIn("VW T10060", " ".join(b.get("text", "") for b in rows))

    def test_petrol_and_diesel_initial_start_have_distinct_steps(self):
        rows = self.page("engine_overhaul", 159)
        start = next(i for i,b in enumerate(rows) if b.get("text", "").startswith("21 Первый"))
        numbers = [int(re.match(r"\d+",b["text"])[0]) for b in rows[start:] if b.get("role") == "steps"]
        self.assertEqual(numbers, list(range(1,18)))

    def test_battery_density_table_does_not_mix_columns(self):
        rows = self.page("starting", 228)
        hot = next(b["text"] for b in rows if b.get("text", "").startswith("При температуре выше"))
        cold = next(b["text"] for b in rows if b.get("text", "").startswith("При температуре ниже"))
        self.assertIn("1,210–1,230",hot)
        self.assertIn("1,270–1,290",cold)
        self.assertEqual(hot.count("•"),3)
        self.assertEqual(cold.count("•"),3)

    def test_fuel_pressure_procedure_and_figure_are_separate(self):
        rows = self.page("fuel_petrol",186)
        start = next(i for i,b in enumerate(rows) if b.get("text", "").startswith("10 Впускной"))
        nums = [int(re.match(r"\d+",b["text"])[0]) for b in rows[:start] if b.get("role") == "steps"]
        self.assertEqual(nums,list(range(1,7)))
        legend = next(b for b in rows if b.get("role") == "legend")
        self.assertEqual([int(re.match(r"\d+",line)[0]) for line in legend['text'].splitlines()],list(range(1,14)))

    def test_reapplying_review_preserves_content_and_provenance(self):
        rules = json.loads((ROOT/'reviewed_source_blocks.json').read_text(encoding='utf-8'))
        for path in (ROOT/'android-manual/app/src/main/assets/articles').glob('*.json'):
            rows=json.loads(path.read_text(encoding='utf-8'))['blocks']
            self.assertEqual(apply_blocks(path.stem,rows,rules),rows,path.stem)
        self.assertEqual(parse_parts('',1,'remove-duplicate'),[])

    def test_reviewed_figures_and_full_pages_exist(self):
        for slug,page in PAGES:
            rows=self.page(slug,page)
            self.assertTrue(rows[0].get('sourceOcrBlocks'))
            images=[b for b in rows if b['type']=='image']
            self.assertEqual(len(images),len(FIGURES.get(page,[]))+1)
            self.assertEqual(images[-1]['asset'],f'media/source/haynes_{page:04d}.webp')

    def test_no_references_to_nonexistent_chapters(self):
        for path in (ROOT/'android-manual/app/src/main/assets/articles').glob('*.json'):
            for b in json.loads(path.read_text(encoding='utf-8'))['blocks']:
                for m in re.finditer(r'\bглав[аыуе]\s+(\d+)',b.get('text',''),re.I):
                    self.assertLessEqual(int(m[1]),12,(path.stem,b.get('page'),m[0]))


if __name__ == '__main__':
    unittest.main()
