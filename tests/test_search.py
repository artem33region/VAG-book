import base64
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path("app/src/main/java/ru/vagguides/golf4manual")
APPS = ("android-manual", "android-bfq", "android-bca")


def encode(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class SearchTests(unittest.TestCase):
    def test_shared_search_engine_and_loader(self):
        for name in ("SearchIndex.java", "ArticleSearch.java"):
            for app in APPS[1:]:
                self.assertEqual((ROOT / APPS[0] / JAVA / name).read_bytes(), (ROOT / app / JAVA / name).read_bytes())

    @unittest.skipUnless(shutil.which("javac") and shutil.which("java"), "JDK is required")
    def test_search_against_each_shipped_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            subprocess.run(["javac", "-encoding", "UTF-8", "-d", directory,
                            str(ROOT / APPS[0] / JAVA / "SearchIndex.java"),
                            str(ROOT / APPS[0] / JAVA / "Section.java"),
                            str(ROOT / "tests/java/SearchIndexTest.java")], check=True, capture_output=True)
            for app in APPS:
                with self.subTest(app=app):
                    assets = ROOT / app / "app/src/main/assets"
                    catalogue = json.loads((assets / "content_index.json").read_text(encoding="utf-8"))
                    rows = []
                    for section in catalogue["sections"]:
                        slug = section["slug"]
                        rows.append("\t".join(["S", slug, encode(section["code"]), encode(section["category"]), encode(section["title"])]))
                        article = json.loads((assets / "articles" / (slug + ".json")).read_text(encoding="utf-8"))
                        position, heading = 0, ""
                        for block in article["blocks"]:
                            image = block.get("type", "text") == "image"
                            text = block.get("text", "").strip()
                            if not (block.get("asset", "").strip() if image else text):
                                continue
                            if block.get("type") == "heading":
                                heading = text
                            rows.append("\t".join(["D", slug, str(position), encode(block.get("description", "") if image else text), encode(heading)]))
                            position += 1
                    queries = [("трос", "automatic_transmission"), ("свеч", "maintenance_petrol"), ("термостат", "cooling")] if app == "android-manual" else [
                        ("свеч", "ignition"), ("коленчат", "timing"),
                        ("приёмной трубы" if app == "android-bfq" else "маслоприёмник", "lubrication")]
                    rows += ["\t".join(["Q", encode(q), slug]) for q, slug in queries]
                    fixture = work / (app + ".tsv")
                    fixture.write_text("\n".join(rows), encoding="utf-8")
                    completed = subprocess.run(["java", "-Dfile.encoding=UTF-8", "-Dsun.stdout.encoding=UTF-8", "-Dsun.stderr.encoding=UTF-8", "-cp", directory, "ru.vagguides.golf4manual.SearchIndexTest", str(fixture)],
                                               capture_output=True, text=True, encoding="utf-8")
                    self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                    self.assertIn("search checks passed", completed.stdout)
                    print(app + ": " + completed.stdout.strip())


if __name__ == "__main__":
    unittest.main()
