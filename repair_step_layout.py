"""Apply source-addressed structure reviews and normalize attested procedure steps.

Run after other content builders/reviews. This pass does not renumber procedures
or change image assets. Rules distinguish chapter headings, figure keys and prose.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from format_article_layout import format_lists

ROOT = Path(__file__).resolve().parent
REVIEW = "step-structure-2026-11-16"
ROOTS = [ROOT / app / "app/src/main/assets" for app in ("android-manual", "android-bfq", "android-bca")]


def load_rules():
    return json.loads((ROOT / "reviewed_structure_rules.json").read_text(encoding="utf-8"))


def apply_structure_blocks(slug, blocks, rules=None):
    rules = load_rules() if rules is None else rules
    lookup = {(r["slug"], r["page"], r["source"], r.get("matchText", "")): r for r in rules}
    result = []
    for block in blocks:
        source = block.get("source", "")
        key = (slug, block.get("page", 0), source, block.get("text", "") if not source else "")
        rule = lookup.get(key)
        if rule and block.get("structureReview") != REVIEW:
            for replacement in rule["replacements"]:
                item = {k: v for k, v in block.items() if k not in ("role", "label", "paragraph")}
                item.update(replacement, structureReview=REVIEW, sourceReview=REVIEW, layoutReviewed=True)
                result.append(item)
        else:
            result.append(block)
    return [format_lists(block) for block in result]


def repair():
    rules = load_rules()
    summary = {}
    for root in ROOTS:
        changes = Counter()
        index_path = root / "content_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for section in index["sections"]:
            path = root / "articles" / (section["slug"] + ".json")
            article = json.loads(path.read_text(encoding="utf-8"))
            before = article["blocks"]
            after = apply_structure_blocks(section["slug"], before, rules if root == ROOTS[0] else [])
            if after == before:
                continue
            changes["articles"] += 1
            for kind in ("steps", "legend", "bullets"):
                changes[kind] += sum(b.get("role") == kind for b in after) - sum(b.get("role") == kind for b in before)
            changes["headings"] += sum(b["type"] == "heading" for b in after) - sum(b["type"] == "heading" for b in before)
            article["blocks"] = after
            article["stepLayoutVersion"] = 2
            path.write_text(json.dumps(article, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
            section["blockCount"] = len(after)
            section["imageCount"] = sum(b["type"] == "image" for b in after)
        if changes:
            index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        summary[root.parents[3].name] = dict(changes)
    return summary


if __name__ == "__main__":
    print(json.dumps(repair(), ensure_ascii=False, indent=2))
