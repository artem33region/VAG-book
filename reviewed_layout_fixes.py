"""Explicit OCR/layout repairs checked against the local original manual.

Rules use source text, never changing array positions. Original source is kept
for review; no guessed global replacement of letters or technical numbers.
"""
import re


def reviewed_fixes(block):
    if block.get("layoutReviewed") or block.get("type") == "image":
        return [block]
    source = block.get("source", "")
    text = block.get("text", "")
    role = None
    heading = None
    if block.get("type") == "caption" and re.match(r"^(?:5\.1|3\.7|4\.9)¢\s", text):
        return [dict(block, text=text.replace("¢", "c", 1), layoutReviewed=True)]
    if source.startswith("C] The only emission test for diesel engines"):
        text = "• " + re.sub(r"^[CС]\s+", "", text)
        role = "bullets"
    elif source.startswith("the coil connector with the slip ring from the Column"):
        text = ("Разъём катушки с контактным кольцом с рулевой колонки.\n\n"
                "5. Ослабьте винт зажима переключателя и снимите узел переключателя с колонки (см. рисунок).\n\n"
                "6. Установка выполняется в порядке, обратном снятию. Точно выставьте положение переключателя:\n\n"
                "a) Установите переключатель на колонку, но лишь слегка затяните винт зажима.\n\n"
                "b) Установите на переключатель разъём катушки с контактным кольцом. Убедитесь, что стопорные выступы вошли в зацепление.\n\n"
                "c) Временно установите рулевое колесо и измерьте зазор между ним и разъёмом катушки с контактным кольцом.")
        role = "bullets"
    elif source.startswith("12 If the complete system is to be bled"):
        text = ("12. При прокачке всей тормозной системы соблюдайте следующую последовательность.\n\n"
                "Система MK20 IE:\n"
                "a) Правый задний тормозной механизм.\n"
                "b) Левый задний тормозной механизм.\n"
                "c) Правый передний тормозной механизм.\n"
                "d) Левый передний тормозной механизм.\n\n"
                "Система MK60:\n"
                "a) Левый передний тормозной механизм.\n"
                "b) Правый передний тормозной механизм.\n"
                "c) Левый задний тормозной механизм.\n"
                "d) Правый задний тормозной механизм.\n\n"
                "Если в одной из камер бачка закончилась тормозная жидкость, перед выполнением этой процедуры необходимо предварительно прокачать систему.")
        role = "steps"
    elif source.startswith("16 Refitting is a reversal of removal, bearing") and "pedal-to-master" in source:
        # The printed original itself repeats d); bullets preserve item order.
        text = re.sub(r"(?<!\w)[acd] (?=[А-ЯЁ])", "\n\n• ", text)
        text = text.replace("16 ", "16. ", 1).replace("После завершения деталей", "После завершения установки")
        role = "bullets"
    elif source.startswith("Operations with engine in car"):
        text = text.removeprefix("Работы с двигателем в автомобиле ")
        text = split_letters(text, "abcdef")
        role = "bullets"
        return [dict(type="heading", page=block["page"], text="Работы с двигателем в автомобиле",
                     source="Operations with engine in car", layoutReviewed=True),
                dict(block, text=text, role=role, layoutReviewed=True)]
    elif source.startswith("i) Cylinder head = removal /)"):
        text = ("i) Головка блока цилиндров — снятие.\n\n"
                "j) Головка блока цилиндров — удаление нагара.\n\n"
                "k) Поддон — снятие и установка.\n\n"
                "l) Масляный насос — снятие, ремонт и установка.")
        role = "bullets"
    elif source.startswith("wiring connector. 16 Release the crankshaft"):
        text = split_letters(text, "abcdef")
        text = text.replace(" 16 ", "\n\n16. ").replace(" 17 ", "\n\n17. ")
        role = "bullets"
    elif source.startswith("a) Alternator (including mounting brackets)") and "glow plug" in source:
        text = split_letters(text.removesuffix(" Все двигатели"), "abcdefgh")
        role, heading = "bullets", "Все двигатели"
    elif source.startswith("A_ Recess in cylinder block B_"):
        text = "A) Углубление в блоке цилиндров\nB) Выступ на вкладыше подшипника\nC) Масляное отверстие"
        role = "legend"
    elif source.startswith("using vernier calipers. If necessary"):
        text = text.replace(" с На моделях", "\n\nc) На моделях").replace(" д При повторной", "\n\nd) При повторной")
        role = "bullets"
    elif source.startswith("(he ramnoval procedure i reverse"):
        text = split_letters(text.removesuffix(" Регулятор давления топлива"), "abcde")
        role, heading = "bullets", "Регулятор давления топлива"
    if not role:
        return [block]
    result = [dict(block, text=text.strip(), role=role, layoutReviewed=True)]
    if heading:
        result.append(dict(type="heading", page=block["page"], text=heading, layoutReviewed=True))
    return result


def split_letters(text, letters):
    for letter in letters:
        text = re.sub(r"(?<!\w)" + letter + r"\s+(?=[А-Яа-яЁё])",
                      "\n\n" + letter + ") ", text, flags=re.I)
    return text.strip()
