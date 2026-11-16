#!/usr/bin/env python3
"""Retranslate native article blocks with Google Translate's public endpoint.

The script is resumable: every source block is cached in SQLite before article
files are changed.  Several blocks are sent in one request with validated
sentinels; if a sentinel is altered, the batch is split automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4
from pathlib import Path

from polish_native_content import clean_text


ROOT = Path(__file__).resolve().parent
DEFAULT_ASSETS = ROOT / ".work" / "native_content" / "google_assets"
DEFAULT_CACHE = ROOT / ".work" / "google_native_translations.sqlite3"
ENDPOINTS = (
    "https://translate.google.com/translate_a/single",
    "https://translate.google.co.uk/translate_a/single",
    "https://translate.google.de/translate_a/single",
    "https://translate.googleapis.com/translate_a/single",
)
GOOGLE_PROVIDER = "google-gtx-en-ru-v1"
MICROSOFT_PROVIDER = "microsoft-edge-en-ru-v1"
LINGVA_PROVIDER = "lingva-google-en-ru-v1"
BING_PROVIDER = "bing-web-en-ru-v1"
MARKER_RE = re.compile(r"VAGSEGMENT(\d{6})", re.IGNORECASE)
MICROSOFT_AUTH = "https://edge.microsoft.com/translate/auth"
MICROSOFT_ENDPOINT = "https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&from=en&to=ru&includeSentenceLength=true"
EDGE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
_microsoft_token: str | None = None
_microsoft_token_time = 0.0
_microsoft_token_lock = threading.Lock()
LINGVA_INSTANCES = (
    "https://lingva.ml",
    "https://translate.igna.wtf",
    "https://translate.plausibility.cloud",
    "https://lingva.lunar.icu",
    "https://translate.projectsegfau.lt",
    "https://translate.dr460nf1r3.org",
    "https://lingva.garudalinux.org",
    "https://translate.jae.fi",
)
_lingva_counter = 0
_lingva_lock = threading.Lock()
BING_PAGE = "https://www.bing.com/translator"
BING_ENDPOINT = "https://www.bing.com/ttranslatev3"
_bing_auth: tuple[str, str, str] | None = None
_bing_auth_time = 0.0
_bing_auth_lock = threading.Lock()


class Cache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS translations (
                source_hash TEXT NOT NULL,
                source_text TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                provider TEXT NOT NULL,
                PRIMARY KEY (source_hash, provider)
            )
            """
        )

    @staticmethod
    def digest(source: str) -> str:
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def get(self, source: str, providers: tuple[str, ...]) -> str | None:
        placeholders = ",".join("?" for _ in providers)
        row = self.connection.execute(
            f"SELECT translated_text FROM translations WHERE source_hash=? AND provider IN ({placeholders}) ORDER BY CASE provider WHEN ? THEN 0 ELSE 1 END LIMIT 1",
            (self.digest(source), *providers, providers[0]),
        ).fetchone()
        return str(row[0]) if row else None

    def put_many(self, rows: list[tuple[str, str]], provider: str) -> None:
        self.connection.executemany(
            "INSERT OR REPLACE INTO translations VALUES(?,?,?,?)",
            [(self.digest(source), source, translated, provider) for source, translated in rows],
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def request_translation(text: str, attempts: int = 8) -> str:
    payload = urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": "ru", "dt": "t", "q": text}
    ).encode("utf-8")
    for attempt in range(attempts):
        request = urllib.request.Request(
            ENDPOINTS[attempt % len(ENDPOINTS)],
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "Mozilla/5.0 native-manual-editor/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
            segments = data[0] if data and isinstance(data[0], list) else []
            translated = "".join(
                str(segment[0])
                for segment in segments
                if isinstance(segment, list) and segment and segment[0] is not None
            )
            if not translated.strip():
                raise ValueError("translation response is empty")
            return translated
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.HTTPError) as exc:
            if attempt + 1 >= attempts:
                raise RuntimeError(f"translation request failed after {attempts} attempts: {exc}") from exc
            time.sleep(min(20, 2 ** attempt))
    raise AssertionError("unreachable")


def get_microsoft_token(force: bool = False) -> str:
    global _microsoft_token, _microsoft_token_time
    with _microsoft_token_lock:
        if not force and _microsoft_token and time.monotonic() - _microsoft_token_time < 480:
            return _microsoft_token
        request = urllib.request.Request(
            MICROSOFT_AUTH,
            headers={
                "User-Agent": EDGE_USER_AGENT,
                "Accept": "*/*",
                "Origin": "https://www.microsoft.com",
            },
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            token = response.read().decode("utf-8").strip()
        if len(token) < 40:
            raise RuntimeError("Microsoft translation token is empty")
        _microsoft_token = token
        _microsoft_token_time = time.monotonic()
        return token


def request_microsoft_translation(sources: list[str], attempts: int = 6) -> list[str]:
    payload = json.dumps([{"Text": source} for source in sources], ensure_ascii=False).encode("utf-8")
    force_token = False
    for attempt in range(attempts):
        try:
            token = get_microsoft_token(force=force_token)
            request = urllib.request.Request(
                MICROSOFT_ENDPOINT,
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "User-Agent": EDGE_USER_AGENT,
                    "X-ClientTraceId": str(uuid4()),
                },
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
            output = [
                str(item["translations"][0]["text"]).strip()
                for item in data
            ]
            if len(output) != len(sources) or any(not value for value in output):
                raise ValueError("Microsoft translation response has the wrong length")
            return output
        except urllib.error.HTTPError as exc:
            force_token = exc.code in {401, 403}
            if attempt + 1 >= attempts:
                raise RuntimeError(f"Microsoft translation failed: HTTP {exc.code}") from exc
            time.sleep(min(20, 2 ** attempt))
        except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            if attempt + 1 >= attempts:
                raise RuntimeError(f"Microsoft translation failed after {attempts} attempts: {exc}") from exc
            time.sleep(min(20, 2 ** attempt))
    raise AssertionError("unreachable")


def marker(index: int) -> str:
    return f"VAGSEGMENT{index:06d}"


def parse_marked_translation(translated: str, sources: list[str], provider: str) -> list[str]:
    payload = "\n\n".join(f"{marker(index)}\n{source}" for index, source in enumerate(sources))
    matches = list(MARKER_RE.finditer(translated))
    found = [int(match.group(1)) for match in matches]
    if found == list(range(len(sources))):
        return [
            translated[matches[index].end() : matches[index + 1].start()].strip()
            if index + 1 < len(matches)
            else translated[matches[index].end() :].strip()
            for index in range(len(matches))
        ]

    # Translation services occasionally alter a sentinel in a very long
    # request.  Bisecting guarantees progress without losing block alignment.
    middle = len(sources) // 2
    return translate_batch(sources[:middle], provider) + translate_batch(sources[middle:], provider)


def request_lingva_translation(text: str, attempts: int = 10) -> str:
    global _lingva_counter
    with _lingva_lock:
        start = _lingva_counter
        _lingva_counter += 1
    encoded = urllib.parse.quote(text, safe="")
    last_error: Exception | None = None
    for attempt in range(attempts):
        instance = LINGVA_INSTANCES[(start + attempt) % len(LINGVA_INSTANCES)]
        request = urllib.request.Request(
            f"{instance}/api/v1/en/ru/{encoded}",
            headers={"User-Agent": EDGE_USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=50) as response:
                data = json.loads(response.read().decode("utf-8"))
            translated = str(data.get("translation", "")).strip()
            if not translated:
                raise ValueError("Lingva response is empty")
            return translated
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.HTTPError) as exc:
            last_error = exc
            print(f"Lingva retry: {instance}: {exc}", flush=True)
            if attempt + 1 < attempts:
                time.sleep(min(8, 1 + attempt))
    raise RuntimeError(f"all Lingva instances failed: {last_error}")


def get_bing_auth(force: bool = False) -> tuple[str, str, str]:
    """Read the short-lived anti-abuse values emitted by Bing Translator."""
    global _bing_auth, _bing_auth_time
    with _bing_auth_lock:
        if not force and _bing_auth and time.monotonic() - _bing_auth_time < 3000:
            return _bing_auth
        request = urllib.request.Request(
            BING_PAGE,
            headers={"User-Agent": EDGE_USER_AGENT, "Accept": "text/html,*/*"},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            page = response.read().decode("utf-8", errors="replace")
        ig_match = re.search(r'IG:"([A-Z0-9]+)"', page)
        token_match = re.search(
            r'params_AbusePreventionHelper\s*=\s*\[(\d+),"([^"]+)",',
            page,
        )
        if not ig_match or not token_match:
            raise RuntimeError("Bing Translator authentication values were not found")
        _bing_auth = (ig_match.group(1), token_match.group(1), token_match.group(2))
        _bing_auth_time = time.monotonic()
        return _bing_auth


def request_bing_translation(text: str, attempts: int = 7) -> str:
    force_auth = False
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            ig, key, token = get_bing_auth(force=force_auth)
            query = urllib.parse.urlencode(
                {"isVertical": "1", "IG": ig, "IID": "translator.5028.1"}
            )
            payload = urllib.parse.urlencode(
                {
                    "fromLang": "en",
                    "to": "ru",
                    "text": text,
                    "token": token,
                    "key": key,
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                f"{BING_ENDPOINT}?{query}",
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "User-Agent": EDGE_USER_AGENT,
                    "Referer": BING_PAGE,
                },
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
            translated = str(data[0]["translations"][0]["text"]).strip()
            if not translated:
                raise ValueError("Bing translation response is empty")
            return translated
        except urllib.error.HTTPError as exc:
            last_error = exc
            force_auth = exc.code in {400, 401, 403, 429}
        except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            last_error = exc
            force_auth = True
        if attempt + 1 < attempts:
            time.sleep(min(16, 2 ** attempt))
    raise RuntimeError(f"Bing translation failed after {attempts} attempts: {last_error}")


def translate_batch(sources: list[str], provider: str) -> list[str]:
    if not sources:
        return []
    if provider == "microsoft":
        return request_microsoft_translation(sources)
    if len(sources) == 1:
        if provider == "bing" and len(sources[0]) > 880:
            remaining = sources[0].strip()
            pieces: list[str] = []
            while len(remaining) > 880:
                cut = max(
                    remaining.rfind(". ", 0, 880),
                    remaining.rfind("; ", 0, 880),
                    remaining.rfind(", ", 0, 880),
                    remaining.rfind(" ", 0, 880),
                )
                if cut < 360:
                    cut = 880
                elif remaining[cut] in ".;,":
                    cut += 1
                pieces.append(remaining[:cut].strip())
                remaining = remaining[cut:].strip()
            if remaining:
                pieces.append(remaining)
            return [" ".join(request_bing_translation(piece) for piece in pieces)]
        if provider == "lingva":
            return [request_lingva_translation(sources[0]).strip()]
        if provider == "bing":
            return [request_bing_translation(sources[0]).strip()]
        return [request_translation(sources[0]).strip()]

    payload = "\n\n".join(f"{marker(index)}\n{source}" for index, source in enumerate(sources))
    if provider == "lingva":
        translated = request_lingva_translation(payload)
    elif provider == "bing":
        translated = request_bing_translation(payload)
    else:
        translated = request_translation(payload)
    return parse_marked_translation(translated, sources, provider)


def make_batches(sources: list[str], max_chars: int, max_items: int) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for source in sources:
        added = len(source) + 24
        if current and (size + added > max_chars or len(current) >= max_items):
            batches.append(current)
            current = []
            size = 0
        current.append(source)
        size += added
    if current:
        batches.append(current)
    return batches


def translatable_blocks(payload: dict):
    """Protect editorial text and fragments that retain a whole-block source."""
    blocks = payload.get("blocks", [])
    counts = Counter(
        (block.get("page"), str(block.get("source", "")).strip())
        for block in blocks
        if block.get("type") != "image"
    )
    for block in blocks:
        source = str(block.get("source", "")).strip()
        if (
            block.get("type") != "image"
            and not block.get("curated")
            and "translationPart" not in block
            and not block.get("role") and not block.get("layoutReviewed")
            and counts[(block.get("page"), source)] == 1
            and len(re.findall(r"[A-Za-z]", source)) >= 3
        ):
            yield block, source


def collect(assets: Path) -> tuple[list[Path], list[str]]:
    paths = sorted((assets / "articles").glob("*.json"))
    output: list[str] = []
    seen: set[str] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for block, source in translatable_blocks(payload):
            if source not in seen:
                seen.add(source)
                output.append(source)
    return paths, output


def rewrite_articles(paths: list[Path], translations: dict[str, str]) -> tuple[int, int]:
    articles_changed = 0
    blocks_changed = 0
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for block, source in translatable_blocks(payload):
            translated = translations.get(source)
            if translated is None:
                continue
            kind = str(block.get("type", "text"))
            cleaned = clean_text(source, translated, kind)
            if cleaned and cleaned != block.get("text"):
                block["text"] = cleaned
                changed = True
                blocks_changed += 1
        if changed:
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(path)
            articles_changed += 1
    return articles_changed, blocks_changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--max-chars", type=int, default=3600)
    parser.add_argument("--max-items", type=int, default=12)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--provider", choices=("google", "microsoft", "lingva", "bing"), default="bing")
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    paths, sources = collect(args.assets)
    cache = Cache(args.cache)
    try:
        provider_id = {
            "google": GOOGLE_PROVIDER,
            "microsoft": MICROSOFT_PROVIDER,
            "lingva": LINGVA_PROVIDER,
            "bing": BING_PROVIDER,
        }[args.provider]
        preferred_providers = (provider_id, GOOGLE_PROVIDER, BING_PROVIDER, LINGVA_PROVIDER, MICROSOFT_PROVIDER)
        translations: dict[str, str] = {}
        missing: list[str] = []
        for source in sources:
            cached = cache.get(source, preferred_providers)
            if cached is None:
                missing.append(source)
            else:
                translations[source] = cached

        batches = make_batches(missing, args.max_chars, args.max_items)
        if args.max_batches is not None:
            batches = batches[: args.max_batches]
        print(
            json.dumps(
                {
                    "unique_sources": len(sources),
                    "cached": len(translations),
                    "missing": len(missing),
                    "batches_this_run": len(batches),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

        if not 1 <= args.workers <= 6:
            parser.error("--workers must be between 1 and 6")
        started = time.monotonic()
        completed = 0
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            pending = {
                executor.submit(translate_batch, batch, args.provider): batch
                for batch in batches
            }
            for future in as_completed(pending):
                batch = pending[future]
                outputs = future.result()
                rows = list(zip(batch, outputs))
                cache.put_many(rows, provider_id)
                translations.update(rows)
                completed += 1
                elapsed = max(0.001, time.monotonic() - started)
                rate = completed / elapsed
                remaining = (len(batches) - completed) / rate if rate else 0.0
                print(
                    f"translated batch {completed}/{len(batches)} | units={len(batch)} | ETA={remaining / 60:.1f} min",
                    flush=True,
                )
                if args.preview:
                    for source, translated in rows[:3]:
                        print(f"SOURCE: {source}\nRUSSIAN: {translated}\n", flush=True)

        if args.preview:
            return 0
        articles_changed, blocks_changed = rewrite_articles(paths, translations)
        print(
            json.dumps(
                {"articles_changed": articles_changed, "blocks_changed": blocks_changed},
                ensure_ascii=False,
            ),
            flush=True,
        )
    finally:
        cache.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
