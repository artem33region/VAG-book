#!/usr/bin/env python3
"""Compare recurring Haynes translations with the OCR reference corpus."""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".work" / "translations.sqlite3"
CORPUS = ROOT / ".work" / "ru_reference_corpus.txt"
MODEL_ID = "quickmt-en-ru+haynes-glossary-v4"


TERMS: tuple[tuple[str, str, str], ...] = (
    (r"\broadside repairs?\b", "roadside repairs", "ремонт в пути"),
    (r"\bjump[- ]start(?:ing)?\b", "jump starting", "запуск двигателя от внешней аккумуляторной батареи"),
    (r"\bbooster battery\b", "booster battery", "внешняя аккумуляторная батарея"),
    (r"\bjump leads?\b", "jump lead", "пусковой провод"),
    (r"\broutine maintenance\b", "routine maintenance", "техническое обслуживание"),
    (r"\bremoval and refitting\b", "removal/refitting", "снятие и установка"),
    (r"\bslacken\b", "slacken", "ослабьте"),
    (r"\bwithdraw\b", "withdraw", "извлеките"),
    (r"\b(?:prise|pry|lever)\b", "prise/pry/lever", "подденьте"),
    (r"\bbleed(?:ing)?\b", "bleed", "прокачка"),
    (r"\baxle stands?\b", "axle stand", "надёжная подставка"),
    (r"\bjack up\b", "jack up", "поднимите автомобиль"),
    (r"\bwheel chocks?\b|\bchock the wheels?\b", "wheel chock", "противооткатный упор"),
    (r"\bhandbrake\b|\bparking brake\b", "handbrake", "стояночный тормоз"),
    (r"\bspanner\b", "spanner", "ключ"),
    (r"\bsocket\b", "socket", "торцовая головка"),
    (r"\bAllen key\b", "Allen key", "шестигранный ключ"),
    (r"\btorque wrench\b", "torque wrench", "динамометрический ключ"),
    (r"\bcrankshaft\b", "crankshaft", "коленчатый вал"),
    (r"\bcamshaft\b", "camshaft", "распределительный вал"),
    (r"\bcylinder head\b", "cylinder head", "головка блока цилиндров"),
    (r"\btiming belt\b", "timing belt", "ремень привода ГРМ"),
    (r"\btiming chain\b", "timing chain", "цепь привода ГРМ"),
    (r"\bvariable valve timing\b", "variable valve timing", "изменяемые фазы газораспределения"),
    (r"\bsump\b|\boil pan\b", "sump", "масляный поддон"),
    (r"\boil seal\b", "oil seal", "сальник"),
    (r"\bgasket\b", "gasket", "прокладка"),
    (r"\bcirclip\b", "circlip", "стопорное кольцо"),
    (r"\bsplit pin\b", "split pin", "шплинт"),
    (r"\bvalve collets?\b|\bsplit collets?\b", "valve collets", "сухари клапана"),
    (r"\bhydraulic tappets?\b", "hydraulic tappet", "гидрокомпенсатор"),
    (r"\binjection pump\b", "injection pump", "топливный насос высокого давления"),
    (r"\bfuel rail\b", "fuel rail", "топливная рампа"),
    (r"\bthrottle body\b", "throttle body", "дроссельный узел"),
    (r"\b(?:inlet|intake) manifold\b", "inlet manifold", "впускной коллектор"),
    (r"\bexhaust manifold\b", "exhaust manifold", "выпускной коллектор"),
    (r"\bcatalytic (?:converter|convector)\b", "catalytic converter", "каталитический нейтрализатор"),
    (r"\b(?:oxygen|lambda) sensor\b", "oxygen sensor", "датчик концентрации кислорода"),
    (r"\bfiller neck\b", "filler neck", "заливная горловина"),
    (r"\btrack rod end\b", "track rod end", "наконечник рулевой тяги"),
    (r"\btrack rod\b", "track rod", "рулевая тяга"),
    (r"\bsteering rack\b", "steering rack", "рулевой механизм"),
    (r"\bball ?joint\b", "balljoint", "шаровая опора"),
    (r"\bwishbone\b|\bcontrol arm\b", "wishbone", "рычаг подвески"),
    (r"\bdrive ?shaft\b", "driveshaft", "приводной вал"),
    (r"\bCV joint\b|\bconstant velocity joint\b", "CV joint", "ШРУС"),
    (r"\bwheel hub\b", "wheel hub", "ступица колеса"),
    (r"\bwheel bearing\b", "wheel bearing", "подшипник ступицы"),
    (r"\bsuspension strut\b", "suspension strut", "амортизаторная стойка"),
    (r"\bshock absorber\b", "shock absorber", "амортизатор"),
    (r"\banti-roll bar\b", "anti-roll bar", "стабилизатор поперечной устойчивости"),
    (r"\bbrake caliper\b", "brake caliper", "тормозной суппорт"),
    (r"\bbrake pads?\b", "brake pad", "тормозная колодка"),
    (r"\bbrake discs?\b", "brake disc", "тормозной диск"),
    (r"\bbrake servo\b", "brake servo", "вакуумный усилитель тормозов"),
    (r"\bmaster cylinder\b", "master cylinder", "главный цилиндр"),
    (r"\bwheel cylinder\b", "wheel cylinder", "колёсный цилиндр"),
    (r"\bclutch\b", "clutch", "сцепление"),
    (r"\bgearbox\b|\bmanual transmission\b", "gearbox", "коробка передач"),
    (r"\bstarter motor\b", "starter motor", "стартер"),
    (r"\balternator\b", "alternator", "генератор"),
    (r"\bearth (?:lead|wire|point)\b", "earth/ground", "масса"),
    (r"\bwiring diagrams?\b", "wiring diagram", "электрическая схема"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filter", default=".", help="regular expression matched against the audit label")
    parser.add_argument("--examples", type=int, default=2)
    args = parser.parse_args()
    corpus = CORPUS.read_text(encoding="utf-8").lower()
    connection = sqlite3.connect(CACHE)
    rows = connection.execute(
        "SELECT source_text, translated_text FROM translations WHERE model_id = ? ORDER BY source_text",
        (MODEL_ID,),
    ).fetchall()
    for pattern, label, canonical in TERMS:
        if not re.search(args.filter, label, re.IGNORECASE):
            continue
        matches = [(source, target) for source, target in rows if re.search(pattern, source, re.IGNORECASE)]
        reference_count = corpus.count(canonical.lower())
        print(f"\n## {label} | haynes={len(matches)} | reference_exact={reference_count} | {canonical}")
        seen: set[str] = set()
        shown = 0
        for source, target in matches:
            if target in seen:
                continue
            seen.add(target)
            print(f"EN: {source[:260]}")
            print(f"RU: {target[:320]}")
            shown += 1
            if shown == args.examples:
                break
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
