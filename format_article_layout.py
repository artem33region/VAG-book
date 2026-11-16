"""Recover list structure using source markers, without inventing numbering.

The original text/source and image references survive layout changes. Ambiguous
numeric runs (units, cross references, incomplete OCR lists) are not split.
The reviewed diesel pages also repair mixed columns and missing figure labels.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from reviewed_diesel_turbo import TEXT, LEGENDS, page_blocks, legend
from reviewed_layout_fixes import reviewed_fixes

ROOT = Path(__file__).resolve().parent
ROOTS = [ROOT / app / "app/src/main/assets" for app in ("android-manual", "android-bfq")]
NUM = re.compile(r"(?<![\w.,])(\d{1,3})[.)]?\s+(?=[A-ZА-ЯЁ])")
UNITS = re.compile(r"^(?:Nm|mm|cm|bar|rpm|litre|volts?|amps?|Н(?:·м)?|В|А|Нм|МПа|кПа|Ом|°C)(?:\b|\s)", re.I)
VERBS = re.compile(r"^(?:Remove|Refit|Disconnect|Connect|Unscrew|Slacken|Tighten|Check|Ensure|Raise|Lower|Apply|Pull|Push|Prise|Use|Turn|With|When|If|The|This|It|Do|Note|Before|After|On|To|Carefully|Support|Position|Working|Lift|Release|Locate|Fit|Withdraw|Detach|Drain|Fill|Renew|Clean|Lubricate|Make|Obtain)\b", re.I)
# The leading paragraph marker is independent of numbers in references or units.
# In particular, a short instruction is still a step. Do not use text length as
# evidence: it excluded exactly the short 7B paragraphs reported in screenshots.
LEADING_NUMBER = re.compile(r"^(\d{1,3})[.)]?\s+")
STEP_OPENING = re.compile(
    r"^(?:Refitting|Where|Using|Undo|Reconnect|Unclip|Proceed|Examine|Slide|Unbolt|"
    r"Switch|Open|Loosen|Inspect|Insert|Wipe|Visually|Work|Refer|As|For|Trace|"
    r"Thoroughly|Once|Press|Smear|A|Securely|Prior|Progressively|Mark|Commence|"
    r"Engage|At|From|Unplug|Screw|Chock|Hold|Ease|Start|Separate|Install|"
    r"Manoeuvre|Move|Lightly|Listen|Fold|Depress|Repeat|Slowly|Again|Place|Spin|"
    r"In|Depressurise|Offer|Allow|Run|Have|Although|Tie|Relocate|Twist|Recover|"
    r"Clamp|Set|Adjust|First|Minimise|Firmly|Refill|Squeeze|Reach|Fully|Similarly|"
    r"Pack|Prevent|Wind|Lay|Attach|Park|Grasp|Now|Guide|Lever|Always|Unhook|"
    r"Operate|Stick|Drill|Whichever|By|Thinly|Bleed|Discard|Lock|Suspend|Reaching|"
    r"Swivel|Secure|Scoop|Loop|Relieve|Purchase|Finally|Alternatively|Coat|"
    r"Continue|Scrape|Begin|Prime|Re-attach|Gain|Referring|Top-up|Select|Measure|"
    r"Reassemble|Beneath|Tilt)\b", re.I)


def leading_step(block):
    """Return an attested paragraph marker, never infer one from a quantity."""
    if block.get("type") != "text" or block.get("translationPart"):
        return None
    text = block.get("text", "")
    translated = LEADING_NUMBER.match(text)
    if not translated:
        return None
    if block.get("paragraph") == int(translated[1]):
        return translated
    source = block.get("source", "")
    original = LEADING_NUMBER.match(source)
    if not original or original[1] != translated[1]:
        return None
    body = source[original.end():]
    # A few scans confuse the initial I of 'If'; keep the stored source intact.
    body = re.sub(r"^(?:\|f|lf|\\f)\b", "If", body)
    if VERBS.match(body) or STEP_OPENING.match(body):
        return translated
    return None
HEADINGS = [
    ("Removal", "Снятие"), ("Refitting", "Установка"), ("Precautions", "Меры предосторожности"),
    ("Inspection", "Проверка"), ("Adjustment", "Регулировка"),
    ("Non-turbo models", "Модели без турбонаддува"), ("Turbo models", "Модели с турбонаддувом"),
    ("All other engine codes", "Все остальные коды двигателя"), ("Engine code AGR", "Код двигателя AGR"),
]
LETTER_ALIASES = {en: en + ru for en, ru in zip("abcdefghijklmnopqrstuvwxyz", "абвгдежзийклмнопрстуфхцчшщ")}
for _en, _lookalike in {"b": "в", "c": "с", "e": "е"}.items():
    LETTER_ALIASES[_en] += _lookalike


def numeric_markers(text):
    result = []
    for match in NUM.finditer(text):
        if UNITS.match(text[match.end():]):
            continue
        if re.search(r"(?:chapter|section|paragraph|illustration|глава|главе|раздел|разделе|пункт|пункте|рисунок|рисунке)\s*$", text[:match.start()], re.I):
            continue
        result.append(match)
    return result


def format_lists(block):
    if block.get("role") == "steps":
        return dict(block, text=re.sub(r"^(\d{1,3})\s+", r"\1. ", block["text"], flags=re.M))
    if block.get("role") or block["type"] not in {"text", "note"}:
        return block
    result = dict(block)
    source, text = block.get("source", ""), block.get("text", "")
    if not text:
        return block
    # Printed bullets that OCR turned into currency symbols.
    if "¢" in source and "¢" in text:
        result["text"] = re.sub(r"\s*¢\s*", "\n\n• ", text).strip()
        result["role"] = "bullets"
        return result
    marker_source = source.replace("©)", "c)")
    letters = list(re.finditer(r"(?<![\w(°])([a-z])\)\s+", marker_source, re.I))
    if letters and not block.get("translationPart"):
        expected = [m[1].lower() for m in letters]
        if [ord(x) for x in expected] != list(range(ord(expected[0]), ord(expected[0]) + len(expected))):
            return block
        matches = []
        cursor = 0
        for letter in expected:
            aliases = LETTER_ALIASES[letter] + LETTER_ALIASES[letter].upper()
            pattern = r"(?<![\w(])([" + aliases + r"])\)?\s+(?=[А-Яа-яЁё])"
            options = []
            for candidate in re.finditer(pattern, text[cursor:]):
                prefix = text[:cursor + candidate.start()].rstrip()
                # Russian с/а/в can be ordinary prepositions/conjunctions.
                if candidate[1].isascii() or not prefix or prefix[-1] in ".!?;:":
                    options.append(candidate)
            if not options:
                matches = []
                break
            m = options[0]
            matches.append((cursor + m.start(), cursor + m.end(), letter))
            cursor += m.end()
        if matches and len(matches) == len(expected):
            pieces = [text[:matches[0][0]].strip()]
            for i, (_, end, letter) in enumerate(matches):
                tail = matches[i + 1][0] if i + 1 < len(matches) else len(text)
                pieces.append(f"{letter}) {text[end:tail].strip()}")
            result.update(text="\n\n".join(p for p in pieces if p), role="bullets")
            return result
    sm, tm = numeric_markers(source), numeric_markers(text)
    sn, tn = [int(m[1]) for m in sm], [int(m[1]) for m in tm]
    if len(sn) >= 2 and sn == tn and sn == list(range(sn[0], sn[0] + len(sn))) and sm[0].start() == 0 and tm[0].start() == 0:
        parts = [source[m.end():sm[i+1].start() if i+1 < len(sm) else None].strip() for i,m in enumerate(sm)]
        is_legend = all(len(p) <= 125 and len(p.split()) <= 18 and not (VERBS.match(p) or STEP_OPENING.match(p)) and not re.search(r"[.!?](?:\s|$)", p) for p in parts)
        lines = [f"{m[1]}. {text[m.end():tm[i+1].start() if i+1 < len(tm) else None].strip()}" for i,m in enumerate(tm)]
        result.update(text=("\n" if is_legend else "\n\n").join(lines), role="legend" if is_legend else "steps")
        if is_legend:
            result["label"] = "Обозначения на рисунке"
        return result
    if re.match(r"^(?:•|[a-z]\))\s+", text, re.I):
        result["role"] = "bullets"
    elif (m := leading_step(block)) is not None:
        result.update(text=f"{m[1]}. {text[m.end():]}", role="steps")
    if result.get("role") == "steps":
        result["text"] = re.sub(r"^(\d{1,3})\s+", r"\1. ", result["text"], flags=re.M)
    return result


def separate_headings(block):
    if block.get("layoutReviewed") or block.get("translationPart") or block["type"] not in {"text", "note", "caption"}:
        return [block]
    source, text = block.get("source", ""), block.get("text", "")
    for en, ru in HEADINGS:
        # Restrict this to a trailing title or a title followed by a new step.
        sm = re.search(r"\b" + re.escape(en) + r"(?=$|\s+\d{1,3}\s+[A-Z])", source)
        ru_pattern = re.escape(ru)
        if en == "Refitting":
            ru_pattern = r"(?:Установка обратно|Установка|Переустановка)"
        tm = re.search(r"\b" + ru_pattern + r"(?=$|\s+\d{1,3}\s+[А-ЯЁ])", text)
        if not sm or not tm:
            continue
        if (sm.start() == 0) != (tm.start() == 0):
            continue
        pieces = []
        if text[:tm.start()].strip():
            pieces.append(dict(block, text=text[:tm.start()].strip(), source=source[:sm.start()].strip()))
        pieces.append({"type": "heading", "page": block.get("page", 0), "text": ru,
                       "source": en, "layoutReviewed": True})
        if text[tm.end():].strip():
            pieces.append(dict(block, text=text[tm.end():].strip(), source=source[sm.end():].strip()))
        return pieces
    return [block]


def merge_note_continuations(blocks):
    result = []
    for block in blocks:
        if result and result[-1]["type"] == "note" and block["type"] == "text":
            note = result[-1]
            source = note.get("source", "")
            following = block.get("source", "")
            if (source and following and not note.get("curated") and not block.get("curated")
                    and "translationPart" not in note and "translationPart" not in block
                    and note.get("page") == block.get("page")
                    and not re.search(r"[.!?:]$", source)
                    and re.search(r"\b(?:a|an|the|to|of|for|with|and|be|is|are|will|must|should|may|can|as|that|in|on|at|from|than|before|after|code)\s*$", source, re.I)
                    and re.match(r"(?:[a-z]|[A-Z0-9]{2,5}[,)])", following)
                    and not numeric_markers(following)
                    and not block.get("role") and len(note["text"]) + len(block["text"]) < 1100):
                note["text"] += " " + block["text"]
                note["source"] += " " + following
                continue
        result.append(dict(block))
    return result


def separate_all_headings(block):
    parts = separate_headings(block)
    if parts == [block]:
        return parts
    return [piece for part in parts for piece in separate_all_headings(part)]


def review_diesel(blocks):
    # Deterministic replacement: no range tied to changing array indices.
    images = {p: [b for b in blocks if b["type"] == "image" and b.get("page") == p] for p in TEXT}
    result = [b for b in blocks if b.get("page") not in TEXT]
    for p in TEXT:
        result.extend(page_blocks(p))
        for i, image in enumerate(images[p]):
            # The original region IDs are stable, see image_provenance.json.
            figure = {221: ["3.17"], 222: ["5.11"], 223: ["6.1", "5.14", "6.3a"]}[p][i]
            title = LEGENDS[figure][1] if figure in LEGENDS else "Клапан управления наддувом — двигатели AGR, ALH, AHF и ASV"
            image = dict(image, description=f"Рисунок {figure}. {title}", layoutReviewed=True)
            result.append(image)
            if figure in LEGENDS:
                result.append(legend(figure))
    return sorted(result, key=lambda b: b.get("page", 0))


def format_articles():
    from repair_step_layout import apply_structure_blocks
    stats = Counter()
    for root in ROOTS:
        index_path = root / "content_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for section in index["sections"]:
            path = root / "articles" / (section["slug"] + ".json")
            article = json.loads(path.read_text(encoding="utf-8"))
            blocks = article["blocks"]
            if root == ROOTS[0] and section["slug"] == "emissions_diesel":
                blocks = review_diesel(blocks)
            blocks = [piece for b in blocks for piece in reviewed_fixes(b)]
            expanded = [piece for b in blocks for piece in separate_all_headings(b)]
            stats["headings_separated"] += len(expanded) - len(blocks)
            merged = merge_note_continuations(expanded)
            stats["note_fragments_joined"] += len(expanded) - len(merged)
            result = apply_structure_blocks(section["slug"], merged, None if root == ROOTS[0] else [])
            for before, after in zip(merged, result):
                if before != after:
                    stats[after.get("role", "other")] += 1
            article["blocks"] = result
            article["layoutVersion"] = 1
            path.write_text(json.dumps(article, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            section["blockCount"] = len(result)
            section["imageCount"] = sum(b["type"] == "image" for b in result)
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(stats)


if __name__ == "__main__":
    print(json.dumps(format_articles(), ensure_ascii=False, indent=2))
