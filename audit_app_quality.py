#!/usr/bin/env python3
"""Run translation and formatting quality checks over native Android articles."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_ASSETS = (
    ROOT / "android-manual" / "app" / "src" / "main" / "assets",
    ROOT / "android-bfq" / "app" / "src" / "main" / "assets",
)

ALLOWED_LATIN = {
    "abs", "ae", "aeh", "ahu", "akl", "apk", "aqy", "asv", "avf", "avu",
    "azj", "bfq", "bora", "bosch", "diesel", "diy", "dis", "dohc", "dot",
    "ecu", "egr", "golf", "gti", "haynes", "jetta", "longlife", "max", "min",
    "mpi", "ngk", "obd", "oben", "off", "on", "pierburg", "ptfe", "ron",
    "sae", "simos", "sohc", "tdc", "tdi", "top", "torx", "volkswagen", "vw",
}

ENGLISH_WORDS = {
    "and", "bearing", "bolt", "camshaft", "chapter", "check", "clutch", "coolant",
    "cylinder", "engine", "fitting", "from", "fuel", "general", "information",
    "inspection", "note", "pressure", "refit", "refitting", "removal", "remove",
    "replacement", "section", "system", "the", "timing", "warning", "with",
}

BAD_TRANSLATION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(?:камвал|камшафт|камшарт)\w*\b", "нестандартное название распределительного вала"),
    (r"\b(?:стартовый двигатель|стартерный двигатель)\b", "стартер переведён как двигатель"),
    (r"\bдвигатель переворачивается\b", "буквальный перевод turns over"),
    (r"\b(?:тестер|испытатель) сжатия\b", "вместо «компрессометр»"),
    (r"\bплоская батарея\b", "буквальный перевод flat battery"),
    (r"\b(?:удаление и переоборудование|снятие и переоборудование)\b", "ошибка removal/refitting"),
    (r"\bретит\w*\b", "непереведённое refit"),
    (r"\bбезопасн(?:ые|ы) (?:электрические )?соединени", "secure переведено как safe"),
    (r"\bручной тормоз\b", "термин «стояночный тормоз»"),
    (r"\bпо цепочке от\b", "буквальный перевод chain drive"),
    (r"\bпятинесущ\w*\b", "ошибка перевода five-bearing"),
    (r"\bрама-постель\b|\bгидроопор\w*\b", "неудачный технический термин"),
    (r"\bтранспортн(?:ое|ого|ому|ым|ом) средств(?:о|а|у|ом|е)\b", "канцеляризм вместо «автомобиль»"),
    (r"\b(?:фаси(?:я|и|ю|ей)|фасад(?:а|у|ом|е)?)\b", "fac(i)a переведено не как «панель приборов»"),
    (r"\bвысвобождени\w*\b", "release переведено как «высвобождение»"),
    (r"\b(?:HT|аккумулятор\w*|воздушн\w*)\s+свинец\b|\b(?:переподключите|отсоедините|подключите) свинец\b", "lead переведено как металл, а не провод"),
    (r"\b(?:проводн|штепсельн)\w* вилк\w*\b", "plug переведено как «вилка»"),
    (r"\b(?:взрывател\w*|плавуч\w* звен\w*|легковоспламеняющ\w* лини\w*)\b", "ошибка перевода fuse/fusible link"),
    (r"\b(?:кровоточ\w*|кроветвор\w*|пролить кровь)\b", "ошибка перевода bleeding"),
    (r"\bразворот\w* .{0,24}\bудалени\w*\b", "буквальный перевод reverse of removal"),
    (r"\b(?:замена снятия|обратн\w* операци\w* снятия|изменени\w* направления разворота)\b", "буквальный перевод reverse of removal"),
    (r"\b(?:луковиц\w*|колб(?:а|ы|у|ой|е))\b", "bulb переведено не как «лампа»"),
    (r"\bспаннер\w*\b", "spanner не переведён как ключ"),
    (r"\bрозетк\w* проводк\w*\b", "wiring socket переведено не как разъём"),
    (r"\bоткажитесь от (?:болт|винт|гаек|гайк)\w*\b", "discard переведено как отказ"),
    (r"\bрезервуар(?:а|е|ом|у)? главн\w* цилиндр\w*\b", "reservoir переведено не как бачок"),
    (r"\b(?:осев\w* стенд\w*|стенд\w* оси)\b", "axle stands переведено не как страховочные опоры"),
    (r"\b(?:подставк|подпорк|опор)\w*\s+(?:(?:для|под|на)\s+)?ос\w*\b", "axle stands переведено не как страховочные опоры"),
    (r"\b(?:опустите|поставьте) .{0,60}\bна массу\b", "ground переведено как электрическая масса"),
    (r"\bподшипников\w* оболоч\w*\b", "bearing shells переведено не как вкладыши"),
    (r"\bопорн\w* (?:колес|катк)\w*\b", "roadwheel переведено как опорное колесо/каток"),
    (r"\bобнов(?:ить|ите|лять|ляться|ляется|лены|лено)\b", "renew переведено как обновление, а не замена"),
    (r"\bвыпускн\w* винт\w*\b", "bleed screw переведено не как прокачной штуцер"),
    (r"\bнажимн\w* пластин\w*\b", "pressure plate переведено не как нажимной диск"),
    (r"\b(?:тип\w* )?шар и клетк\w*\b", "ball-and-cage joint переведён буквально"),
    (r"\bтип\w* тройник\w*\b", "tripod joint переведён буквально"),
)

MOJIBAKE = ("�", "Рђ", "Рџ", "Рµ", "Гѓ", "Г‚", "&amp;", "&apos;")
LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
MIXED_SCRIPT_RE = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё])(?=[A-Za-zА-Яа-яЁё]*[A-Za-z])(?=[A-Za-zА-Яа-яЁё]*[А-Яа-яЁё])[A-Za-zА-Яа-яЁё]{2,}(?![A-Za-zА-Яа-яЁё])"
)


@dataclass(frozen=True)
class Issue:
    category: str
    location: str
    message: str
    excerpt: str


def suspicious_english(text: str) -> list[str]:
    tokens = LATIN_TOKEN_RE.findall(text)
    suspicious = []
    for token in tokens:
        folded = token.casefold()
        if folded in ALLOWED_LATIN:
            continue
        if token.isupper() and 2 <= len(token) <= 6:
            continue
        if re.fullmatch(r"[A-Z]{1,4}\d[A-Z0-9-]*", token):
            continue
        if folded in ENGLISH_WORDS:
            suspicious.append(token)
    return suspicious


def audit_assets(assets: Path) -> tuple[dict[str, int], list[Issue]]:
    index_path = assets / "content_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    issues: list[Issue] = []
    stats: Counter[str] = Counter()
    referenced: set[str] = set()
    seen_slugs: set[str] = set()
    if not index.get("sections"):
        issues.append(Issue("structure", "index", "пустой список разделов", ""))

    for section in index.get("sections", []):
        slug = str(section.get("slug", ""))
        if not re.fullmatch(r"[a-z0-9_\-]+", slug):
            issues.append(Issue("structure", slug, "недопустимый идентификатор раздела", ""))
            continue
        if slug in seen_slugs:
            issues.append(Issue("structure", slug, "повтор раздела в индексе", ""))
        seen_slugs.add(slug)
        article_path = assets / "articles" / f"{slug}.json"
        if not article_path.is_file():
            issues.append(Issue("structure", slug, "отсутствует файл статьи", ""))
            continue
        article = json.loads(article_path.read_text(encoding="utf-8"))
        blocks = article.get("blocks", [])
        if article.get("slug") != slug:
            issues.append(Issue("structure", slug, "идентификатор статьи не совпадает с индексом", ""))
        if not blocks:
            issues.append(Issue("structure", slug, "пустая статья", ""))
        stats["sections"] += 1
        stats["blocks"] += len(blocks)
        image_count = 0
        for position, block in enumerate(blocks):
            location = f"{slug}:{position}"
            kind = str(block.get("type", "text"))
            if kind not in {"heading", "text", "note", "caption", "image"}:
                issues.append(Issue("structure", location, "неизвестный тип блока", kind))
            if kind == "image":
                image_count += 1
                stats["images"] += 1
                asset = str(block.get("asset", ""))
                referenced.add(asset)
                if not asset or not (assets / asset).is_file():
                    issues.append(Issue("structure", location, "отсутствует изображение", asset))
                source_asset = block.get("sourceAsset", "")
                if source_asset:
                    referenced.add(source_asset)
                    if not (assets / source_asset).is_file():
                        issues.append(Issue("structure", location, "отсутствует полная страница", source_asset))
                description = str(block.get("description", ""))
                if description and not CYRILLIC_RE.search(description):
                    issues.append(Issue("translation", location, "описание изображения не на русском", description[:180]))
                continue

            stats["text_blocks"] += 1
            text = str(block.get("text", ""))
            stripped = text.strip()
            if not stripped:
                issues.append(Issue("structure", location, "пустой текстовый блок", ""))
                continue
            stats["characters"] += len(stripped)
            if re.search(r"\b\d{1,2}[ABCDАБВГ]?[eе•·]\d{1,2}\b", stripped):
                issues.append(Issue("format", location, "колонтитул попал в текст", stripped[:220]))
            if re.search(r"\b([А-Яа-яЁё]{3,})/\1\b", stripped, re.I):
                issues.append(Issue("format", location, "повтор слова через косую черту", stripped[:220]))

            for marker in MOJIBAKE:
                if marker in stripped:
                    issues.append(Issue("encoding", location, f"подозрительная кодировка: {marker}", stripped[:220]))
                    break
            if re.search(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", stripped):
                issues.append(Issue("encoding", location, "управляющий символ", stripped[:220]))
            mixed_words = MIXED_SCRIPT_RE.findall(stripped)
            if mixed_words:
                issues.append(
                    Issue(
                        "encoding",
                        location,
                        "смешаны кириллица и латиница: " + ", ".join(mixed_words[:8]),
                        stripped[:220],
                    )
                )
            if re.search(r"\s+[,.!?;:]", stripped):
                issues.append(Issue("format", location, "пробел перед знаком препинания", stripped[:220]))
            if re.search(r"[.!?](?=[А-ЯЁA-Z])", stripped):
                issues.append(Issue("format", location, "нет пробела после знака препинания", stripped[:220]))
            if re.search(r"\b([А-Яа-яЁё]{3,})\s+\1\b", stripped, re.IGNORECASE):
                issues.append(Issue("format", location, "повтор слова", stripped[:220]))
            if re.search(r"[!?.,;:]{3,}", stripped):
                issues.append(Issue("format", location, "повторяющаяся пунктуация", stripped[:220]))
            if re.search(r"\b[А-Яа-яЁё]{2,}\([А-Яа-яЁё]{1,4}\)", stripped):
                issues.append(Issue("format", location, "OCR-нотация вариантного окончания", stripped[:220]))
            bracket_text = re.sub(r"^[a-zа-я]\)\s+", "", stripped, flags=re.I)
            if bracket_text.count("(") != bracket_text.count(")") or bracket_text.count("[") != bracket_text.count("]"):
                issues.append(Issue("format", location, "несбалансированные скобки", stripped[:220]))
            if len(stripped) > 1800:
                issues.append(Issue("format", location, "слишком длинный блок", stripped[:220]))
            if kind == "heading" and len(stripped) > 180:
                issues.append(Issue("format", location, "слишком длинный заголовок", stripped[:220]))
            if kind == "heading" and re.search(r"\b(?:и|в|на|с|для|из|от|по)$", stripped, re.IGNORECASE):
                issues.append(Issue("format", location, "заголовок обрывается на предлоге/союзе", stripped[:220]))

            bad_english = suspicious_english(stripped)
            if len(bad_english) >= 2:
                issues.append(
                    Issue(
                        "translation",
                        location,
                        "вероятный английский фрагмент: " + ", ".join(bad_english[:8]),
                        stripped[:220],
                    )
                )
            source = str(block.get("source", ""))
            if source and len(re.findall(r"[A-Za-z]", source)) >= 25 and len(CYRILLIC_RE.findall(stripped)) < 5:
                issues.append(Issue("translation", location, "текст не переведён", stripped[:220]))
            if re.search(r"\brecover(?:ed|ing|s)?\b", source, re.IGNORECASE) and re.search(
                r"\bсохран(?:ить|ите|яя)\b", stripped, re.IGNORECASE
            ):
                issues.append(Issue("terminology", location, "recover переведено как «сохранить»", stripped[:220]))
            if re.search(r"\bdriveshafts?\b", source, re.IGNORECASE) and re.search(
                r"\bкарданн\w* вал\w*\b", stripped, re.IGNORECASE
            ):
                issues.append(Issue("terminology", location, "driveshaft переведено не как приводной вал", stripped[:220]))
            if re.search(r"\bfriction (?:disc|plate)\b", source, re.IGNORECASE) and re.search(
                r"\bфрикционн\w* диск\w*\b", stripped, re.IGNORECASE
            ):
                issues.append(Issue("terminology", location, "friction disc переведено не как ведомый диск", stripped[:220]))

            for pattern, explanation in BAD_TRANSLATION_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    issues.append(Issue("terminology", location, explanation, stripped[:220]))

        if int(section.get("blockCount", -1)) != len(blocks):
            issues.append(Issue("structure", slug, "не совпадает число блоков", ""))
        if int(section.get("imageCount", -1)) != image_count:
            issues.append(Issue("structure", slug, "не совпадает число изображений", ""))

    media = {path.relative_to(assets).as_posix() for path in (assets / "media").rglob("*.webp")}
    for orphan in sorted(media - referenced):
        issues.append(Issue("structure", "media", "неиспользуемое изображение", orphan))
    for path in sorted((assets / "articles").glob("*.json")):
        if path.stem not in seen_slugs:
            issues.append(Issue("structure", path.stem, "статья отсутствует в индексе", ""))
    stats["issues"] = len(issues)
    return dict(stats), issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", action="append", type=Path)
    parser.add_argument("--show", type=int, default=120)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    roots = tuple(args.assets) if args.assets else DEFAULT_ASSETS
    total_issues = 0
    for assets in roots:
        stats, issues = audit_assets(assets)
        total_issues += len(issues)
        print(f"\n## {assets}")
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        by_category = Counter(issue.category for issue in issues)
        print("categories:", json.dumps(dict(sorted(by_category.items())), ensure_ascii=False))
        for issue in issues[: args.show]:
            suffix = f": {issue.excerpt}" if issue.excerpt else ""
            print(f"- [{issue.category}] {issue.location}: {issue.message}{suffix}")
        if len(issues) > args.show:
            print(f"... and {len(issues) - args.show} more")
    return 1 if args.strict and total_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
