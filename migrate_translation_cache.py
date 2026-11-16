#!/usr/bin/env python3
"""Create the reference-terminology translation cache from the prior Haynes cache."""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
from pathlib import Path

from reference_terminology import enhance_translation


ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".work" / "translations.sqlite3"
REPORT = ROOT / ".work" / "reference_terminology_changes.tsv"
OLD_MODEL_ID = "quickmt-en-ru+haynes-glossary-v4"
NEW_MODEL_ID = "quickmt-en-ru+haynes-reference-v5"


ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("timing belt as chronology", r"ремн\w* хронометраж"),
    ("wrench settings", r"настройки гаечного ключа"),
    ("socket as outlet", r"\bрозетк\w*\b"),
    ("anti-roll transliteration", r"анти[- ]?рол|антипрокат"),
    ("bleeding as haemorrhage", r"кровотеч"),
    ("jump-lead literalism", r"прыжк"),
    ("fuel rail literalism", r"топливн\w* рельс"),
    ("shock absorber literalism", r"ударн\w* поглотител"),
    ("starter motor literalism", r"стартерн\w* двигатель|стартов\w* мотор"),
)


def cache_key(text: str, model_id: str) -> str:
    return hashlib.sha256(f"{model_id}\0{text}".encode("utf-8")).hexdigest()


def count_pattern(rows: list[tuple[str, str, str]], pattern: str, index: int) -> int:
    return sum(bool(re.search(pattern, row[index], re.IGNORECASE)) for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the v5 cache rows")
    args = parser.parse_args()

    connection = sqlite3.connect(CACHE)
    old_rows = connection.execute(
        "SELECT source_text, translated_text FROM translations WHERE model_id = ? ORDER BY source_text",
        (OLD_MODEL_ID,),
    ).fetchall()
    if not old_rows:
        raise SystemExit(f"no source rows found for {OLD_MODEL_ID}")

    rows: list[tuple[str, str, str]] = []
    for source, old_target in old_rows:
        rows.append((source, old_target, enhance_translation(source, old_target)))

    changed = [row for row in rows if row[1] != row[2]]
    empty = [row for row in rows if row[1] and not row[2]]
    duplicate_terms = [
        row
        for row in rows
        if re.search(r"(?:привода ГРМ\s+){2,}|(?:топливная рампа\s+){2,}", row[2], re.IGNORECASE)
    ]
    print(f"source_rows={len(rows)}")
    print(f"changed_rows={len(changed)}")
    print(f"empty_results={len(empty)}")
    print(f"duplicate_terms={len(duplicate_terms)}")
    for label, pattern in ARTIFACTS:
        before = count_pattern(rows, pattern, 1)
        after = count_pattern(rows, pattern, 2)
        print(f"artifact {label}: {before} -> {after}")

    print("sample_changes:")
    for source, old_target, new_target in changed[:20]:
        print(f"EN: {source[:180]}")
        print(f"V4: {old_target[:220]}")
        print(f"V5: {new_target[:220]}")

    if empty or duplicate_terms:
        connection.close()
        raise SystemExit("validation failed; cache was not modified")

    if args.apply:
        connection.executemany(
            "INSERT OR REPLACE INTO translations(source_hash, source_text, translated_text, model_id) VALUES(?,?,?,?)",
            [
                (cache_key(source, NEW_MODEL_ID), source, new_target, NEW_MODEL_ID)
                for source, _, new_target in rows
            ],
        )
        connection.commit()
        report_lines = ["source\tv4\tv5"]
        report_lines.extend(
            "\t".join(value.replace("\t", " ").replace("\n", " ") for value in row)
            for row in changed
        )
        REPORT.write_text("\n".join(report_lines), encoding="utf-8")
        written = connection.execute(
            "SELECT COUNT(1) FROM translations WHERE model_id = ?",
            (NEW_MODEL_ID,),
        ).fetchone()[0]
        print(f"written_rows={written}")
        print(f"report={REPORT}")
    else:
        print("dry_run=1 (use --apply after reviewing the audit)")
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
