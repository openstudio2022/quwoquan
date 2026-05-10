from __future__ import annotations

import hashlib
import mimetypes
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import unescape
from pathlib import Path


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(slots=True)
class FetchedPage:
    url: str
    final_url: str
    title: str
    html: str
    text: str
    paragraphs: list[str]
    image_urls: list[str]


@dataclass(slots=True)
class DownloadedAsset:
    source_url: str
    local_path: Path
    sha256: str
    mime_type: str
    width: int | None
    height: int | None
    size_bytes: int


class NativeFetchError(RuntimeError):
    pass


def _normalize_text(value: str) -> str:
    return " ".join(unescape(value).replace("\ufeff", "").split())


def _strip_html_tags(source: str) -> str:
    body = re.sub(r"<script[\s\S]*?</script>", " ", source, flags=re.I)
    body = re.sub(r"<style[\s\S]*?</style>", " ", body, flags=re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    return _normalize_text(body)


def _extract_title(source: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", source, flags=re.I | re.S)
    return _normalize_text(match.group(1)) if match else ""


def _extract_paragraphs(source: str) -> list[str]:
    preferred_sections: list[str] = []
    for pattern in (
        r"<article[\s\S]*?</article>",
        r"<main[\s\S]*?</main>",
        r'<div[^>]+class="[^"]*(?:article|content|post|detail)[^"]*"[\s\S]*?</div>',
    ):
        preferred_sections.extend(re.findall(pattern, source, flags=re.I))
    blocks = preferred_sections or [source]
    paragraphs: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        for paragraph in re.findall(r"<p[^>]*>(.*?)</p>", block, flags=re.I | re.S):
            cleaned = _strip_html_tags(paragraph)
            if len(cleaned) < 32 or cleaned in seen:
                continue
            seen.add(cleaned)
            paragraphs.append(cleaned)
    if paragraphs:
        return paragraphs
    fallback = _strip_html_tags(source)
    return [fallback] if fallback else []


def _extract_image_urls(base_url: str, source: str, *, limit: int = 8) -> list[str]:
    candidates: list[str] = []
    direct_patterns = (
        r"<meta[^>]+property=['\"]og:image['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<meta[^>]+name=['\"]twitter:image['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<img[^>]+src=['\"]([^'\"]+)['\"]",
        r"<img[^>]+data-src=['\"]([^'\"]+)['\"]",
        r"<a[^>]+href=['\"]([^'\"]+\.(?:jpg|jpeg|png|webp)(?:\?[^'\"]*)?)['\"]",
    )
    srcset_patterns = (
        r"<img[^>]+srcset=['\"]([^'\"]+)['\"]",
        r"<source[^>]+srcset=['\"]([^'\"]+)['\"]",
    )

    def add_candidate(value: str) -> bool:
        normalized = urllib.parse.urljoin(base_url, unescape(value).strip())
        if normalized.startswith("data:"):
            return False
        lowered = normalized.lower()
        if any(
            token in lowered
            for token in (
                "wordmark",
                "logo",
                "icon",
                "button",
                "edit.svg",
                "wikimedia-button",
                "poweredby_mediawiki",
                "/static/images/",
            )
        ):
            return False
        if lowered.endswith(".svg"):
            return False
        if normalized not in candidates:
            candidates.append(normalized)
        return len(candidates) >= limit

    for pattern in direct_patterns:
        for value in re.findall(pattern, source, flags=re.I):
            if add_candidate(value):
                return candidates

    for pattern in srcset_patterns:
        for value in re.findall(pattern, source, flags=re.I):
            for part in value.split(","):
                url = part.strip().split(" ", 1)[0].strip()
                if not url:
                    continue
                if add_candidate(url):
                    return candidates
    return candidates


def _curl_fetch(url: str) -> tuple[bytes, str, str]:
    with tempfile.TemporaryDirectory() as tempdir:
        body_path = Path(tempdir) / "body.bin"
        headers_path = Path(tempdir) / "headers.txt"
        command = [
            "curl",
            "-L",
            "-A",
            DEFAULT_USER_AGENT,
            "-H",
            "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
            "-sS",
            "-o",
            str(body_path),
            "-D",
            str(headers_path),
            "-w",
            "%{url_effective}\n%{content_type}",
            url,
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise NativeFetchError(f"curl 获取失败: {url} -> {result.stderr.strip()}")
        lines = result.stdout.splitlines()
        final_url = lines[0].strip() if lines else url
        content_type = lines[1].strip() if len(lines) > 1 else ""
        return body_path.read_bytes(), final_url, content_type


def fetch_html_page(url: str, *, timeout_seconds: int = 20) -> FetchedPage:
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                html = raw.decode(charset, errors="ignore")
                final_url = response.geturl()
                break
        except (urllib.error.URLError, TimeoutError) as error:
            try:
                raw, final_url, _ = _curl_fetch(url)
                html = raw.decode("utf-8", errors="ignore")
                break
            except NativeFetchError as curl_error:
                last_error = NativeFetchError(
                    f"fetch html 失败: {url} -> {error}; curl fallback -> {curl_error}"
                )
        if attempt == 2:
            assert last_error is not None
            raise last_error
        time.sleep(0.8 * (attempt + 1))
    title = _extract_title(html) or url
    paragraphs = _extract_paragraphs(html)
    text = "\n\n".join(paragraphs) if paragraphs else _strip_html_tags(html)
    image_urls = _extract_image_urls(final_url, html)
    return FetchedPage(
        url=url,
        final_url=final_url,
        title=title,
        html=html,
        text=text,
        paragraphs=paragraphs,
        image_urls=image_urls,
    )


def _png_dimensions(blob: bytes) -> tuple[int | None, int | None]:
    if len(blob) >= 24 and blob[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(blob[16:20], "big"), int.from_bytes(blob[20:24], "big")
    return None, None


def _gif_dimensions(blob: bytes) -> tuple[int | None, int | None]:
    if len(blob) >= 10 and blob[:6] in {b"GIF87a", b"GIF89a"}:
        return int.from_bytes(blob[6:8], "little"), int.from_bytes(blob[8:10], "little")
    return None, None


def _jpeg_dimensions(blob: bytes) -> tuple[int | None, int | None]:
    if len(blob) < 4 or blob[:2] != b"\xff\xd8":
        return None, None
    offset = 2
    while offset + 9 < len(blob):
        if blob[offset] != 0xFF:
            offset += 1
            continue
        marker = blob[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        segment_length = int.from_bytes(blob[offset : offset + 2], "big")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if offset + 7 < len(blob):
                height = int.from_bytes(blob[offset + 3 : offset + 5], "big")
                width = int.from_bytes(blob[offset + 5 : offset + 7], "big")
                return width, height
            return None, None
        offset += max(segment_length, 2)
    return None, None


def _webp_dimensions(blob: bytes) -> tuple[int | None, int | None]:
    if len(blob) < 30 or blob[:4] != b"RIFF" or blob[8:12] != b"WEBP":
        return None, None
    chunk_type = blob[12:16]
    if chunk_type == b"VP8X" and len(blob) >= 30:
        width = 1 + int.from_bytes(blob[24:27], "little")
        height = 1 + int.from_bytes(blob[27:30], "little")
        return width, height
    return None, None


def sniff_image_dimensions(blob: bytes) -> tuple[int | None, int | None]:
    for resolver in (_png_dimensions, _gif_dimensions, _jpeg_dimensions, _webp_dimensions):
        width, height = resolver(blob)
        if width and height:
            return width, height
    return None, None


def download_binary(url: str, target_path: Path, *, timeout_seconds: int = 25) -> DownloadedAsset:
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                blob = response.read()
                mime_type = response.headers.get_content_type() or ""
                final_url = response.geturl()
                break
        except (urllib.error.URLError, TimeoutError) as error:
            try:
                blob, final_url, mime_type = _curl_fetch(url)
                break
            except NativeFetchError as curl_error:
                last_error = NativeFetchError(
                    f"download asset 失败: {url} -> {error}; curl fallback -> {curl_error}"
                )
        if attempt == 2:
            assert last_error is not None
            raise last_error
        time.sleep(0.8 * (attempt + 1))
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    guessed_type, _ = mimetypes.guess_type(final_url)
    if not mime_type:
        mime_type = guessed_type or "application/octet-stream"
    width, height = sniff_image_dimensions(blob)
    return DownloadedAsset(
        source_url=final_url,
        local_path=target_path,
        sha256=digest,
        mime_type=mime_type,
        width=width,
        height=height,
        size_bytes=len(blob),
    )


def safe_filename_from_url(url: str, *, fallback: str = "download") -> str:
    parsed = urllib.parse.urlparse(url)
    candidate = Path(parsed.path).name or fallback
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", candidate).strip("._")
    return candidate or fallback
