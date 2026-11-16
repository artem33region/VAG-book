"""BCA isolation, reader contracts and comparison with the unmodified source scan."""
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / ".tools")]
from audit_app_quality import audit_assets
from build_bca_content import ASSETS, build
from prepare_updates import APPS
from translate_haynes import DEFAULT_INPUT


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class BcaContentTests(unittest.TestCase):
    def test_catalogue_matches_native_navigation_and_articles(self):
        index = read_json(ASSETS / "content_index.json")
        java = (ROOT / "android-bca/app/src/main/java/ru/vagguides/golf4manual/ManualSections.java").read_text(encoding="utf-8")
        navigation = re.findall(r'new Section\("([^"]+)", "([^"]+)", "([^"]+)", "([^"]+)"', java)
        expected = [tuple(s[k] for k in ("code", "slug", "category", "title")) for s in index["sections"]]
        self.assertEqual(navigation, expected)
        self.assertEqual(len(expected), 14)
        for row in index["sections"]:
            article = read_json(ASSETS / "articles" / (row["slug"] + ".json"))
            for key in ("code", "slug", "category", "title", "sourcePages"):
                self.assertEqual(article[key], row[key])
            self.assertTrue(row["sourcePages"])

    def test_text_assets_and_explicit_list_boundaries(self):
        stats, issues = audit_assets(ASSETS)
        self.assertEqual(issues, [])
        self.assertGreater(stats["characters"], 20000)
        steps_seen = 0
        for path in (ASSETS / "articles").glob("*.json"):
            for block in read_json(path)["blocks"]:
                if block.get("role") == "steps":
                    numbers = [int(n) for n in re.findall(r"(?m)^(\d+)\. ", block["text"])]
                    self.assertEqual(numbers, list(range(1, len(numbers) + 1)))
                    self.assertEqual(len(block["text"].split("\n\n")), len(numbers))
                    steps_seen += 1
                elif block.get("role") == "bullets":
                    self.assertTrue(all(line.startswith("• ") for line in block["text"].splitlines()))
        self.assertGreaterEqual(steps_seen, 10)

    def test_no_bfq_engine_data_leaked_into_bca(self):
        text = "\n".join(p.read_text(encoding="utf-8") for p in (ASSETS / "articles").glob("*.json"))
        for wrong in ["BFQ", "Simos", "1595", "102 л.", "4,5 л", "5,0 л", "7,5 бар", "SOHC"]:
            self.assertNotIn(wrong, text)
        for required in ["1390", "55 кВт", "128 Н·м", "76,5 × 75,6", "3,2 л", "6,0 л", "7,0 бар", "ME7.5.10", "индивидуальные катушки"]:
            self.assertIn(required, text)

    def test_bca_installs_and_updates_independently(self):
        app = next(row for row in APPS if row[0] == "android-bca")
        self.assertEqual(app[1:3], ("ru.vagguides.bcamanual", "bca"))
        self.assertEqual(len({row[1] for row in APPS}), len(APPS))
        gradle = (ROOT / "android-bca/app/build.gradle").read_text()
        self.assertIn('applicationId "ru.vagguides.bcamanual"', gradle)
        checker = (ROOT / "android-bca/app/src/main/java/ru/vagguides/golf4manual/AutoUpdateChecker.java").read_text()
        self.assertIn("getPackageName()", checker)
        main = (ROOT / "android-bca/app/src/main/java/ru/vagguides/golf4manual/MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("AutoUpdateChecker", main)
        manifest = read_json(ROOT / "updates.json")["apps"]
        self.assertEqual(manifest[app[1]]["packageName"], app[1])
        self.assertRegex(manifest[app[1]]["url"], r"/bca-\d+\.apk$")

    def test_all_images_have_provenance_and_full_source_pages(self):
        from PIL import Image
        entries = read_json(ROOT / "bca_image_provenance.json")["images"]
        actual = []
        for path in (ASSETS / "articles").glob("*.json"):
            for b in read_json(path)["blocks"]:
                if b["type"] == "image":
                    actual.append((b["asset"], b["page"]))
        self.assertCountEqual(actual, [(e["asset"], e["page"]) for e in entries])
        for entry in entries:
            for key in ("asset", "sourceAsset"):
                with Image.open(ASSETS / entry[key]) as im:
                    im.verify()
            if entry["box"]:
                with Image.open(ASSETS / entry["asset"]) as im:
                    x0, y0, x1, y1 = entry["box"]
                    self.assertEqual(im.size, (x1 - x0, y1 - y0))

    @unittest.skipUnless(DEFAULT_INPUT.exists(), "Local original PDF is required")
    def test_crops_are_exact_source_pixels_without_masking(self):
        import pymupdf
        from PIL import Image
        with pymupdf.open(DEFAULT_INPUT) as pdf:
            for entry in read_json(ROOT / "bca_image_provenance.json")["images"]:
                if not entry["box"]:
                    continue
                pix = pdf[entry["page"] - 1].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
                original = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                buffer = io.BytesIO()
                original.crop(entry["box"]).save(buffer, format="WEBP", quality=88, method=4)
                self.assertEqual(buffer.getvalue(), (ASSETS / entry["asset"]).read_bytes(), entry["asset"])

    @unittest.skipUnless(DEFAULT_INPUT.exists(), "Local original PDF is required")
    def test_builder_reproduces_committed_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory)
            build(generated)
            expected = {p.relative_to(ASSETS) for p in ASSETS.rglob("*") if p.is_file()}
            self.assertEqual(expected, {p.relative_to(generated) for p in generated.rglob("*") if p.is_file()})
            for rel in expected:
                self.assertEqual((ASSETS / rel).read_bytes(), (generated / rel).read_bytes(), str(rel))
