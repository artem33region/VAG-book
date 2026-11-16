"""Apply editorial corrections verified against pages 62 and 267 of the source PDF.

Keep source and page provenance, and protect reviewed text from machine translation.
Matching source prefixes makes the pass independent of changing block positions.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "android-manual/app/src/main/assets"
CORRECTIONS = {
    ("engine_sohc", 62): [
        ("Note that the compression should build-up",
         "Примечание. В исправном двигателе давление при проверке компрессии должно нарастать быстро."),
        ("quickly in a healthy engine. Low compression",
         "Низкая компрессия на первом такте сжатия с постепенным повышением давления на последующих тактах указывает на износ поршневых колец. Если давление низкое на первом такте и не повышается на последующих, возможны негерметичность клапанов, повреждение прокладки или трещина головки блока цилиндров. Отложения на нижней стороне тарелок клапанов также могут снижать компрессию."),
        ("following test to isolate the cause.",
         "9 Если давление в каком-либо цилиндре равно указанному минимальному значению или ниже него, выполните дополнительную проверку. Через свечное отверстие влейте в этот цилиндр чайную ложку чистого моторного масла и повторите измерение компрессии."),
        ("10 If the addition of oil temporarily improves",
         "10 Если после добавления масла компрессия временно повышается, причиной потери давления является износ цилиндра или поршня. Если улучшения нет, возможны негерметичность или прогар клапанов либо повреждение прокладки головки блока цилиндров.\n11 Низкая компрессия в двух соседних цилиндрах почти наверняка указывает на повреждение прокладки между ними. Наличие охлаждающей жидкости в моторном масле подтверждает этот вывод."),
        ("12 If one cylinder is about 20 percent lower",
         "12 Если компрессия в одном цилиндре примерно на 20 процентов ниже, чем в остальных, а двигатель работает на холостом ходу немного неравномерно, причиной может быть износ кулачка распределительного вала."),
        ("13 If the compression reading is unusually high",
         "13 Необычно высокая компрессия может быть вызвана нагаром в камерах сгорания. В этом случае следует снять головку блока цилиндров и удалить нагар."),
    ],
    ("brakes", 267): [
        ("30 Discard any hydraulic fluid that has been",
         "30 Слитая при прокачке тормозная жидкость непригодна для повторного использования; её следует утилизировать."),
        ("2.14 Remove the dust cap (arrowed) from",
         "2.14 Снимите пылезащитный колпачок (указан стрелкой) с первого по порядку прокачки штуцера."),
        ("the first screw in the sequence 31 Check",
         "31 Проверьте ход педали тормоза. Если педаль остаётся мягкой, в системе присутствует воздух и прокачку необходимо продолжить. Если несколько повторений процедуры не дают результата, причиной может быть износ уплотнений главного тормозного цилиндра."),
        ("Note: Refer to the note in Section 2",
         "Примечание. См. предупреждение об опасности тормозной жидкости в разделе 2."),
        ("concerning the dangers of hydraulic fluid. 1 If",
         "1 При замене трубки или шланга сведите потери тормозной жидкости к минимуму. Снимите крышку бачка главного тормозного цилиндра, накройте горловину полиэтиленовой плёнкой и заверните крышку, чтобы герметично закрыть бачок. При необходимости гибкий шланг можно перекрыть специальным зажимом для тормозных шлангов. Соединения металлических трубок сразу после разъединения закройте заглушками или колпачками, не допуская попадания грязи в систему. Подложите ветошь под разъединяемое соединение для сбора вытекающей жидкости."),
    ],
}


def repair(assets: Path = ASSETS) -> int:
    changed = 0
    for (slug, page), corrections in CORRECTIONS.items():
        path = assets / "articles" / f"{slug}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for prefix, text in corrections:
            matches = [b for b in payload["blocks"]
                       if b.get("page") == page and b.get("source", "").startswith(prefix)]
            if len(matches) != 1:
                raise ValueError(f"{slug}:{page}: expected one match for {prefix!r}, got {len(matches)}")
            block = matches[0]
            if block.get("text") != text or not block.get("curated"):
                block["text"] = text
                block["curated"] = True
                changed += 1
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return changed


if __name__ == "__main__":
    print(f"Corrected blocks: {repair()}")
