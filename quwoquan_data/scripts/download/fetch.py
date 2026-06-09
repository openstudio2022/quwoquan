"""HTTP fetch and text extraction (pure IO, no semantic processing)."""
from __future__ import annotations

import hashlib
import http.client
import time
import urllib.parse
from pathlib import Path

# Wikimedia/多数公共源要求 User-Agent 含 contact，否则触发严格限流(429)。
_USER_AGENT = (
    "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@quwoquan.example)"
)

# 图片魔数 → 扩展名（仅放行真实图片二进制，拒绝 HTML 错误页伪装）。
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def sniff_image_ext(body: bytes, content_type: str = "") -> str | None:
    """按魔数优先、content-type 兜底判定图片扩展名；非图片返回 None。"""
    for magic, ext in _IMAGE_MAGIC:
        if body.startswith(magic):
            return ext
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return ".webp"
    ct = (content_type or "").lower()
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    return None


def fetch_source(url: str, output_dir: Path) -> dict:
    """Fetch a URL and extract text content. Returns metadata dict."""
    output_dir.mkdir(parents=True, exist_ok=True)

    parsed = urllib.parse.urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parsed.hostname, parsed.port, timeout=15)

    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"

    conn.request("GET", path, headers={"User-Agent": _USER_AGENT})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()

    html_path = output_dir / "page.html"
    html_path.write_bytes(body)

    text = body.decode("utf-8", errors="replace")
    source_md_path = output_dir / "source.md"
    source_md_path.write_text(text[:50000], encoding="utf-8")

    return {
        "url": url,
        "statusCode": resp.status,
        "contentLength": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "htmlPath": str(html_path),
        "sourceMdPath": str(source_md_path),
    }


def fetch_source_payload(url: str) -> dict:
    """抓取原文但不落盘，返回 {url, statusCode, htmlBytes, text, sha256}。

    供来源单元写入器把 page.html/source.md 落进 1.download/sources/{NN}.{sourceKind}/。
    网络异常抛出，由调用方走离线兜底。
    """
    parsed = urllib.parse.urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parsed.hostname, parsed.port, timeout=15)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    conn.request("GET", path, headers={"User-Agent": _USER_AGENT})
    resp = conn.getresponse()
    body = resp.read()
    status = resp.status
    conn.close()
    return {
        "url": url,
        "statusCode": status,
        "htmlBytes": body,
        "text": body.decode("utf-8", errors="replace")[:50000],
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _parse_retry_after(raw: str | None, *, attempt: int) -> float:
    """解析 Retry-After 头(秒)；缺省用指数退避 2,4,8,16(上限30s)。"""
    if raw:
        try:
            return min(float(raw.strip()), 30.0)
        except ValueError:
            pass
    return float(min(2 ** (attempt + 1), 30))


def _http_get_bytes(
    url: str,
    *,
    timeout: int = 20,
    max_redirects: int = 4,
    max_retries: int = 4,
) -> tuple[int, bytes, str]:
    """GET 返回 (status, body, content_type)。

    跟随有限次重定向（图片 CDN 常 301/302）；对 429/503 限流按 Retry-After 或指数
    退避重试（公共源批量抓取常见），避免单次限流即放弃下载。
    """
    current = url
    status, body, content_type = 0, b"", ""
    redirects = 0
    attempt = 0
    while True:
        parsed = urllib.parse.urlparse(current)
        conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(parsed.hostname, parsed.port, timeout=timeout)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        conn.request("GET", path, headers={"User-Agent": _USER_AGENT})
        resp = conn.getresponse()
        status = resp.status
        if status in (301, 302, 303, 307, 308):
            location = resp.getheader("Location") or ""
            conn.close()
            redirects += 1
            if not location or redirects > max_redirects:
                break
            current = urllib.parse.urljoin(current, location)
            continue
        if status in (429, 503) and attempt < max_retries:
            delay = _parse_retry_after(resp.getheader("Retry-After"), attempt=attempt)
            conn.close()
            time.sleep(delay)
            attempt += 1
            continue
        body = resp.read()
        content_type = resp.getheader("Content-Type", "") or ""
        conn.close()
        break
    return status, body, content_type


def fetch_image_payload(url: str, *, min_bytes: int = 3000) -> dict | None:
    """下载单张图片但不落盘，返回 {url, ext, bytes, contentType, sha256}。

    供来源单元写入器（write_source_unit）把图片直接落进来源 assets/，
    避免对象级散落 images/。非 200 / 过小 / 非图片 / 网络异常一律返回 None。
    """
    try:
        status, body, content_type = _http_get_bytes(url)
    except Exception:
        return None
    if status != 200 or len(body) < min_bytes:
        return None
    ext = sniff_image_ext(body, content_type)
    if ext is None:
        return None
    return {
        "url": url,
        "ext": ext,
        "bytes": body,
        "contentType": content_type,
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def fetch_image(url: str, images_dir: Path, *, index: int, min_bytes: int = 3000) -> dict | None:
    """下载单张图片到 images_dir/img_<index>.<ext>。

    仅落真实图片二进制（按魔数判定，拒 HTML/错误页）；非 200 / 过小 / 非图片 / 网络异常
    一律返回 None（不抛），由调用方决定是否记账或重试。
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    try:
        status, body, content_type = _http_get_bytes(url)
    except Exception:
        return None
    if status != 200 or len(body) < min_bytes:
        return None
    ext = sniff_image_ext(body, content_type)
    if ext is None:
        return None
    file_name = f"img_{index:02d}{ext}"
    (images_dir / file_name).write_bytes(body)
    return {
        "url": url,
        "fileName": file_name,
        "statusCode": status,
        "contentType": content_type,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
