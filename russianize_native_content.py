#!/usr/bin/env python3
"""Translate residual English spans in already generated article JSON."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from audit_native_content import ALLOWED_LATIN, UPPERCASE_WORDS, is_allowed_token
from reference_terminology import enhance_translation
from translate_haynes import DEFAULT_CACHE, DEFAULT_MODEL, QuickMTTranslator, TranslationCache


ROOT = Path(__file__).resolve().parent
DEFAULT_ASSETS = ROOT / ".work" / "native_content" / "generated_assets"
SPAN_RE = re.compile(r"[A-Za-z][A-Za-z'-]{1,}(?:\s+[A-Za-z][A-Za-z'-]{1,})*")

EXACT_SPANS = {
    "et seq": "и далее",
    "continued": "продолжение",
    "see illustration": "см. иллюстрацию",
    "see illustrations": "см. иллюстрации",
    "in car": "на автомобиле",
}


def needs_translation(span: str) -> bool:
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]{1,}", span)
    return any(not is_allowed_token(token) for token in tokens)


def collect_spans(article_paths: list[Path]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for path in article_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for block in payload.get("blocks", []):
            if block.get("type") == "image":
                continue
            for match in SPAN_RE.finditer(str(block.get("text", ""))):
                span = match.group(0)
                if needs_translation(span) and span not in seen:
                    seen.add(span)
                    output.append(span)
    return output


def translate_spans(
    spans: list[str],
    engine: QuickMTTranslator,
    cache: TranslationCache,
) -> dict[str, str]:
    replacements: dict[str, str] = {}
    missing: list[str] = []
    for span in spans:
        exact = EXACT_SPANS.get(span.casefold())
        if exact is not None:
            replacements[span] = exact
            continue
        cached = cache.get(span, engine.model_id)
        if cached is None:
            missing.append(span)
        else:
            replacements[span] = enhance_translation(span, cached)

    started = time.monotonic()
    for offset in range(0, len(missing), 64):
        batch = missing[offset : offset + 64]
        outputs = engine.translate_batch(batch)
        cache.put_many(list(zip(batch, outputs)), engine.model_id)
        for source, translated in zip(batch, outputs):
            replacements[source] = enhance_translation(source, translated)
        done = min(offset + len(batch), len(missing))
        elapsed = max(0.001, time.monotonic() - started)
        remaining = (len(missing) - done) / max(0.001, done / elapsed)
        print(f"residual spans {done}/{len(missing)} (ETA {remaining / 60:.1f} min)", flush=True)
    return replacements


def rewrite_articles(article_paths: list[Path], replacements: dict[str, str]) -> int:
    changed = 0
    for path in article_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        article_changed = False
        for block in payload.get("blocks", []):
            if block.get("type") == "image":
                continue
            text = str(block.get("text", ""))

            def replace(match: re.Match[str]) -> str:
                nonlocal article_changed
                span = match.group(0)
                replacement = replacements.get(span)
                if replacement and replacement != span:
                    article_changed = True
                    return replacement
                return span

            block["text"] = SPAN_RE.sub(replace, text)
        if article_changed:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()

    paths = sorted((args.assets / "articles").glob("*.json"))
    spans = collect_spans(paths)
    print(f"residual English spans: {len(spans)}", flush=True)
    if not spans:
        return 0
    engine = QuickMTTranslator(args.model)
    cache = TranslationCache(args.cache)
    try:
        replacements = translate_spans(spans, engine, cache)
    finally:
        cache.close()
    changed = rewrite_articles(paths, replacements)
    print(f"updated {changed} articles", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
