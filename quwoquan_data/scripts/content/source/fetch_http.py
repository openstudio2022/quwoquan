"""Bounded HTTP transport for source and media downloads."""
from __future__ import annotations

import http.client
import os
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

from core.runtime_policy import active_runtime_policy
from content.source.fetch_text import (
    DOWNLOAD_BYTES_TIMEOUT_SECONDS,
    DOWNLOAD_CURL_RETRIES,
    _USER_AGENT,
)

_SOURCE_FETCH_MAX_RETRIES = active_runtime_policy().source_fetch_max_retries

def _parse_retry_after(raw: str | None, *, attempt: int) -> float:
    """解析 Retry-After 头(秒)；缺省用指数退避 2,4,8,16(上限30s)。"""
    if raw:
        try:
            return min(float(raw.strip()), 30.0)
        except ValueError:
            pass
    return float(min(2 ** (attempt + 1), 30))


def _curl_get_bytes(
    url: str,
    *,
    timeout: int = DOWNLOAD_BYTES_TIMEOUT_SECONDS,
    max_bytes: int = 0,
) -> tuple[int, bytes, str]:
    """curl 回退：本机 http.client 对 Wikimedia CDN 偶发 SSL EOF 时仍可下图。"""
    size_guard: list[str] = []
    if int(max_bytes or 0) > 0:
        size_guard = ["--max-filesize", str(int(max_bytes))]
    with tempfile.NamedTemporaryFile() as body_file:
        proc = subprocess.run(
            [
                "curl", "-sS", "-L", "--compressed", "-A", _USER_AGENT,
                "--retry", str(DOWNLOAD_CURL_RETRIES), "--retry-delay", "1", "--retry-all-errors",
                "--max-time", str(timeout),
                *size_guard,
                "-o", body_file.name,
                "-w", "%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"curl exit {proc.returncode}")
        try:
            status = int((proc.stdout or "").strip() or "0")
        except ValueError:
            status = 0
        body = Path(body_file.name).read_bytes()
    return status, body, ""


def _http_get_bytes(
    url: str,
    *,
    timeout: int = DOWNLOAD_BYTES_TIMEOUT_SECONDS,
    max_redirects: int = 4,
    max_retries: int = _SOURCE_FETCH_MAX_RETRIES,
    max_bytes: int = 0,
) -> tuple[int, bytes, str]:
    """GET 返回 (status, body, content_type)。

    跟随有限次重定向（图片 CDN 常 301/302）；对 429/503 限流按 Retry-After 或指数
    退避重试（公共源批量抓取常见），避免单次限流即放弃下载。
    """
    if os.environ.get("QWQ_DOWNLOAD_USE_HTTP_CLIENT", "0") != "1":
        return _curl_get_bytes(url, timeout=timeout, max_bytes=max_bytes)

    current = url
    status, body, content_type = 0, b"", ""
    redirects = 0
    attempt = 0
    try:
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
            content_length = resp.getheader("Content-Length")
            if int(max_bytes or 0) > 0 and content_length:
                try:
                    if int(content_length) > int(max_bytes):
                        conn.close()
                        return status, b"", resp.getheader("Content-Type", "") or ""
                except ValueError:
                    pass
            if int(max_bytes or 0) > 0:
                body = resp.read(int(max_bytes) + 1)
                if len(body) > int(max_bytes):
                    conn.close()
                    return status, b"", resp.getheader("Content-Type", "") or ""
            else:
                body = resp.read()
            content_type = resp.getheader("Content-Type", "") or ""
            conn.close()
            break
        if status == 200 and body:
            return status, body, content_type
    except (OSError, ValueError, http.client.HTTPException):
        return _curl_get_bytes(url, timeout=timeout, max_bytes=max_bytes)
    return _curl_get_bytes(url, timeout=timeout, max_bytes=max_bytes)

