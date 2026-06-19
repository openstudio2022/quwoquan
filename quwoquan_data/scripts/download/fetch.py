"""HTTP fetch and text extraction (pure IO, no semantic processing)."""
from __future__ import annotations

import html as html_lib
import hashlib
import http.client
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

from _common.paths import DATA_ROOT
from vertical.source_registry import resolve_travel_source_runtime

# Wikimedia/多数公共源要求 User-Agent 含 contact，否则触发严格限流(429)。
_USER_AGENT = (
    "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@quwoquan.example)"
)
DOWNLOAD_TEXT_TIMEOUT_SECONDS = max(5, int(os.environ.get("QWQ_DOWNLOAD_TEXT_TIMEOUT_SECONDS", "20")))
DOWNLOAD_BYTES_TIMEOUT_SECONDS = max(3, int(os.environ.get("QWQ_DOWNLOAD_BYTES_TIMEOUT_SECONDS", "8")))
DOWNLOAD_CURL_RETRIES = max(0, int(os.environ.get("QWQ_DOWNLOAD_CURL_RETRIES", "1")))

# 图片魔数 → 扩展名（仅放行真实图片二进制，拒绝 HTML 错误页伪装）。
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)

SUPPORTED_TEXT_EXTRACTORS: frozenset[str] = frozenset(
    {
        "wikipedia_api",
        "baidu_baike_html",
        "sogou_baike_html",
        "qunar_html",
        "static_official_html",
        "generic_html",
    }
)


def _curl_get_text(url: str, *, timeout: int = DOWNLOAD_TEXT_TIMEOUT_SECONDS) -> str:
    proc = subprocess.run(
        [
            "curl", "-sS", "-L", "-A", _USER_AGENT,
            "--retry", "2", "--retry-delay", "1", "--retry-all-errors",
            "--max-time", str(timeout),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"curl exit {proc.returncode}")
    return proc.stdout


def _wikipedia_api_plaintext(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if not any(host.endswith(domain) for domain in ("wikipedia.org", "wikivoyage.org")):
        return ""
    if "/wiki/" not in parsed.path:
        return ""
    title = urllib.parse.unquote(parsed.path.split("/wiki/", 1)[1].split("#")[0])
    q = urllib.parse.urlencode({
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "titles": title,
        "format": "json",
    })
    api_url = f"https://{parsed.hostname}/w/api.php?{q}"
    try:
        data = json.loads(_curl_get_text(api_url))
    except Exception:
        return ""
    pages = data.get("query", {}).get("pages") or {}
    for page in pages.values():
        extract = str(page.get("extract") or "").strip()
        if extract:
            return extract
    return ""


def _html_to_plain_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    match = re.search(
        r'(?is)<div[^>]+class="[^"]*mw-parser-output[^"]*"[^>]*>(.*)</div>\s*</div>\s*</div>',
        text,
    )
    if match:
        text = match.group(1)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<[^>]+>", "\n", text)
    text = html_lib.unescape(text)
    text = re.sub(r"&nbsp;|&amp;|&lt;|&gt;|&quot;|&#\d+;", " ", text)
    lines = [ln.strip() for ln in text.splitlines()]
    kept: list[str] = []
    for ln in lines:
        if not ln or len(ln) < 2:
            continue
        if any(tok in ln for tok in ("wgBreakFrames", "RLCONF", "vector-feature", "DOCTYPE")):
            continue
        kept.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _html_meta_plain_text(html: str) -> str:
    """Extract only useful head metadata, including disabled meta comments.

    Some official scenic sites keep their stable introduction in
    keywords/description meta tags, and a few leave those tags commented out in
    the deployed shell. We intentionally extract only meta tag content rather
    than preserving arbitrary HTML comments, which would pull in templates and
    implementation notes as source text.
    """
    search_space = str(html or "")
    comments = "\n".join(re.findall(r"(?is)<!--(.*?)-->", search_space))
    if comments:
        search_space = f"{search_space}\n{comments}"
    chunks: list[str] = []
    for tag in re.findall(r"(?is)<meta\b[^>]*>", search_space):
        if not re.search(
            r"""(?is)\b(?:name|property)\s*=\s*["'](?:description|keywords|og:description|twitter:description)["']""",
            tag,
        ):
            continue
        match = re.search(r"""(?is)\bcontent\s*=\s*(["'])(.*?)\1""", tag)
        if not match:
            continue
        value = html_lib.unescape(match.group(2)).strip()
        value = re.sub(r"\s+", " ", value)
        if len(value) < 12 or not re.search(r"[\u4e00-\u9fff]", value):
            continue
        chunks.append(value)
    return _join_unique_text_chunks(chunks)


def _baike_html_plaintext(url: str) -> str:
    try:
        html = _curl_get_text(url)
    except Exception:
        return ""
    return _html_to_plain_text(html)[:50000]


def _join_unique_text_chunks(chunks: list[str]) -> str:
    seen: set[str] = set()
    kept: list[str] = []
    for chunk in chunks:
        text = re.sub(r"\n{3,}", "\n\n", str(chunk or "").strip())
        if not text or text in seen:
            continue
        seen.add(text)
        kept.append(text)
    return "\n\n".join(kept).strip()


def _ems517_json_payload(url: str, *, raw_text: str | None = None) -> dict[str, object] | None:
    try:
        raw = raw_text if raw_text is not None else _curl_get_text(url)
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("code") or 0) != 0:
        return None
    return payload


def _ems517_record_plaintext(record: dict[str, object]) -> str:
    chunks: list[str] = []
    for key in ("title", "name", "titleEn", "subtitle", "cateName", "columnName", "intro", "note"):
        value = str(record.get(key) or "").strip()
        if value:
            chunks.append(value)
    content = str(record.get("content") or "").strip()
    if content:
        chunks.append(_html_to_plain_text(content))
    ext_button = str(record.get("ext1value") or "").strip()
    if ext_button and "http" not in ext_button.lower():
        chunks.append(ext_button)
    return _join_unique_text_chunks(chunks)


def _ems517_payload_plaintext(payload: dict[str, object]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        records = data.get("records")
        if isinstance(records, list):
            return _join_unique_text_chunks(
                [
                    _ems517_record_plaintext(record)
                    for record in records[:5]
                    if isinstance(record, dict)
                ]
            )
        return _ems517_record_plaintext(data)
    if isinstance(data, list):
        return _join_unique_text_chunks(
            [_ems517_record_plaintext(record) for record in data[:5] if isinstance(record, dict)]
        )
    return ""


def _ems517_api_plaintext(url: str, *, raw_text: str | None = None) -> str:
    payload = _ems517_json_payload(url, raw_text=raw_text)
    if payload is None:
        return ""
    return _ems517_payload_plaintext(payload)[:50000]


def _ems517_shell_plaintext(url: str, html: str) -> str:
    parsed = urllib.parse.urlparse(url)
    api_base = urllib.parse.urljoin(f"{parsed.scheme}://{parsed.netloc}", "/new_api/")
    query = urllib.parse.parse_qs(parsed.query)
    chunks: list[str] = []

    if query.get("id"):
        article_id = str(query["id"][0]).strip()
        if article_id:
            chunks.append(_ems517_api_plaintext(urllib.parse.urljoin(api_base, f"api/article/{article_id}")))

    if parsed.path.startswith("/new/visitor"):
        for category_id in ("31", "33", "34", "94"):
            chunks.append(_ems517_api_plaintext(urllib.parse.urljoin(api_base, f"api/category/{category_id}")))
        category_payload = _ems517_json_payload(urllib.parse.urljoin(api_base, "api/category/31"))
        root_item_id = ""
        if category_payload and isinstance(category_payload.get("data"), dict):
            root_item_id = str(category_payload["data"].get("itemId") or "").strip()
        if root_item_id:
            chunks.append(
                _ems517_api_plaintext(
                    urllib.parse.urljoin(
                        api_base,
                        f"api/notice/list?page=1&limit=3&itemId={root_item_id}",
                    )
                )
            )
            chunks.append(
                _ems517_api_plaintext(
                    urllib.parse.urljoin(
                        api_base,
                        f"api/article/list?page=1&limit=3&itemId={root_item_id}",
                    )
                )
            )

    joined = _join_unique_text_chunks(chunks)
    if joined:
        return joined[:50000]
    return _html_to_plain_text(html)[:50000]


def _qunar_html_plaintext(html_bytes: bytes, url: str = "") -> str:
    _ = url
    raw = html_bytes.decode("utf-8", errors="replace")
    return _html_to_plain_text(raw)[:50000]


def _flatten_json_strings(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        if (
            len(text) >= 4
            and re.search(r"[\u4e00-\u9fff]", text)
            and not re.search(r"[\u3040-\u30ff\uac00-\ud7af]", text)
        ):
            return [text]
        return []
    if isinstance(value, dict):
        chunks: list[str] = []
        for item in value.values():
            chunks.extend(_flatten_json_strings(item))
        return chunks
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            chunks.extend(_flatten_json_strings(item))
        return chunks
    return []


def _spa_bundle_plaintext(url: str, html: str) -> str:
    """Extract public copy embedded in SPA bundles for official scenic sites."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    script_srcs = re.findall(r'(?is)<script[^>]+src=["\']?([^"\' >]+)', html)
    chunks: list[str] = []
    for src in script_srcs:
        if not src:
            continue
        src_host = urllib.parse.urlparse(src).hostname
        if src_host and src_host != host:
            continue
        if not src.endswith(".js") and ".js" not in src:
            continue
        try:
            js = _curl_get_text(urllib.parse.urljoin(url, src), timeout=DOWNLOAD_TEXT_TIMEOUT_SECONDS)
        except Exception:
            continue
        for match in re.finditer(r"JSON\.parse\('((?:\\.|[^'])*)'\)", js):
            raw = match.group(1).replace("\\'", "'")
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            chunks.extend(_flatten_json_strings(payload))
        if chunks:
            break
    positive = ("景区", "旅游", "游客", "开放", "门票", "竹海", "风景", "度假", "交通", "服务")
    negative = ("観光", "発車", "検索", "詳細", "閉館", "推奨", "敷地", "総建築", "物語", "連絡")

    def _locale_score(text: str) -> int:
        return sum(token in text for token in positive) - sum(token in text for token in negative)

    chunks = [
        chunk for chunk in chunks
        if not (any(token in chunk for token in negative) and not any(token in chunk for token in positive))
    ]
    chunks = sorted(chunks, key=_locale_score, reverse=True)
    return _join_unique_text_chunks(chunks)[:50000]


def _static_official_plaintext(url: str) -> str:
    try:
        html = _curl_get_text(url)
    except Exception:
        return ""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.endswith("ems517.com"):
        if "/new_api/" in parsed.path:
            text = _ems517_api_plaintext(url, raw_text=html)
            if text:
                return text[:50000]
        if parsed.path.startswith("/new/"):
            text = _ems517_shell_plaintext(url, html)
            if text:
                return text[:50000]
    meta_text = _html_meta_plain_text(html)
    text = _join_unique_text_chunks([meta_text, _html_to_plain_text(html)])
    if len(text) < 200 or "加载中" in text:
        bundle_text = _spa_bundle_plaintext(url, html)
        if bundle_text:
            return _join_unique_text_chunks([meta_text, bundle_text])[:50000]
    return text[:50000]


def _extract_text_by_extractor(extractor: str, html_bytes: bytes, url: str = "") -> str:
    if extractor == "wikipedia_api":
        return _wikipedia_api_plaintext(url)[:50000]
    if extractor in {"baidu_baike_html", "sogou_baike_html"}:
        return _baike_html_plaintext(url)
    if extractor == "qunar_html":
        return _qunar_html_plaintext(html_bytes, url)
    if extractor == "static_official_html":
        return _static_official_plaintext(url)
    raw = html_bytes.decode("utf-8", errors="replace")
    return _html_to_plain_text(raw)[:50000]


def extract_page_text(html_bytes: bytes, url: str = "", *, extractor: str = "generic_html") -> str:
    """从 HTML 响应抽取可读正文（按 registry extractor 分发）。"""
    return _extract_text_by_extractor(extractor, html_bytes, url)[:50000]


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


def candidate_image_urls(url: str) -> list[str]:
    """Return deterministic same-source high-resolution candidates.

    The candidates stay on the same host/path family and are only used for
    fetch attempts. Rights, relevance, source-unit ownership and pixel gates
    still run after bytes are downloaded.
    """
    raw = str(url or "").strip()
    if not raw:
        return []
    candidates: list[str] = []

    def _add(item: str) -> None:
        if item and item not in candidates:
            candidates.append(item)

    _add(raw)
    parsed = urllib.parse.urlparse(raw)
    if parsed.query:
        _add(urllib.parse.urlunparse(parsed._replace(query="", fragment="")))

    # Qunar-style compressed variants:
    #   foo.jpg_r_720x480x95_hash.jpg -> foo.jpg
    #   foo.jpg_r_600x600x95_hash.jpg -> foo.jpg
    stripped = re.sub(
        r"(?i)(\.(?:jpe?g|png|webp))_r_\d+x\d+(?:x\d+)?_[A-Za-z0-9]+(?:\.(?:jpe?g|png|webp))$",
        r"\1",
        urllib.parse.urlunparse(parsed._replace(query="", fragment="")),
    )
    _add(stripped)

    # Some CDNs append a post-extension rendition marker.
    stripped_bang = re.sub(
        r"(?i)(\.(?:jpe?g|png|webp))(?:![^/?#]+)$",
        r"\1",
        urllib.parse.urlunparse(parsed._replace(query="", fragment="")),
    )
    _add(stripped_bang)

    # Wikimedia thumb URLs keep the original file path before the final
    # size-prefixed segment.
    path_parts = parsed.path.split("/")
    if "/wikipedia/commons/thumb/" in parsed.path and len(path_parts) > 4:
        try:
            thumb_index = path_parts.index("thumb")
            original_parts = path_parts[:thumb_index] + path_parts[thumb_index + 1:-1]
            original_path = "/".join(original_parts)
            _add(urllib.parse.urlunparse(parsed._replace(path=original_path, query="", fragment="")))
        except ValueError:
            pass

    return candidates


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

    runtime = resolve_travel_source_runtime(url)
    extractor = str(runtime.get("extractor") or "generic_html")
    text = extract_page_text(body, url, extractor=extractor)
    source_md_path = output_dir / "source.md"
    source_md_path.write_text(text, encoding="utf-8")

    return {
        "url": url,
        "statusCode": resp.status,
        "contentLength": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "htmlPath": str(html_path),
        "sourceMdPath": str(source_md_path),
        "runtime": runtime,
    }


def _source_fetchable_override(source: Mapping[str, Any] | None) -> bool:
    if not isinstance(source, Mapping):
        return False
    for key in ("fetchableOverride", "fetchable"):
        value = source.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}:
            return True
    return False


def fetch_source_payload(url: str, *, source: Mapping[str, Any] | None = None) -> dict:
    """抓取原文但不落盘，返回 {url, statusCode, htmlBytes, text, sha256}。

    供来源单元写入器把 page.html/source.md 落进 1.download/sources/{NN}.{sourceKind}/。
    网络异常抛出，由调用方走离线兜底。
    """
    runtime = resolve_travel_source_runtime(url)
    fetchable_override = _source_fetchable_override(source)
    if runtime.get("matched") and not runtime.get("fetchable") and not fetchable_override:
        raise RuntimeError(
            f"fetch blocked for {url}: siteId={runtime.get('siteId')} marked fetchable=false in source registry"
        )
    if fetchable_override:
        runtime = {**runtime, "sourceFetchableOverride": True}
    status, body, _ = _http_get_bytes(url, timeout=20, max_redirects=4, max_retries=4)
    if status != 200 or not body:
        raise RuntimeError(f"fetch failed for {url} (status={status})")
    extractor = str(runtime.get("extractor") or "generic_html")
    return {
        "url": url,
        "statusCode": status,
        "htmlBytes": body,
        "text": extract_page_text(body, url, extractor=extractor),
        "sha256": hashlib.sha256(body).hexdigest(),
        "runtime": runtime,
    }


def _parse_retry_after(raw: str | None, *, attempt: int) -> float:
    """解析 Retry-After 头(秒)；缺省用指数退避 2,4,8,16(上限30s)。"""
    if raw:
        try:
            return min(float(raw.strip()), 30.0)
        except ValueError:
            pass
    return float(min(2 ** (attempt + 1), 30))


def _curl_get_bytes(url: str, *, timeout: int = DOWNLOAD_BYTES_TIMEOUT_SECONDS) -> tuple[int, bytes, str]:
    """curl 回退：本机 http.client 对 Wikimedia CDN 偶发 SSL EOF 时仍可下图。"""
    with tempfile.NamedTemporaryFile() as body_file:
        proc = subprocess.run(
            [
                "curl", "-sS", "-L", "-A", _USER_AGENT,
                "--retry", str(DOWNLOAD_CURL_RETRIES), "--retry-delay", "1", "--retry-all-errors",
                "--max-time", str(timeout),
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
    max_retries: int = 4,
) -> tuple[int, bytes, str]:
    """GET 返回 (status, body, content_type)。

    跟随有限次重定向（图片 CDN 常 301/302）；对 429/503 限流按 Retry-After 或指数
    退避重试（公共源批量抓取常见），避免单次限流即放弃下载。
    """
    if os.environ.get("QWQ_DOWNLOAD_USE_HTTP_CLIENT", "0") != "1":
        return _curl_get_bytes(url, timeout=timeout)

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
            body = resp.read()
            content_type = resp.getheader("Content-Type", "") or ""
            conn.close()
            break
        if status == 200 and body:
            return status, body, content_type
    except Exception:
        pass
    return _curl_get_bytes(url, timeout=timeout)


def _fetch_image_payload_once(url: str, *, min_bytes: int = 3000) -> dict | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        try:
            path = Path(urllib.parse.unquote(parsed.path)).resolve()
            data_root = DATA_ROOT.resolve()
            if not path.is_relative_to(data_root) or not path.is_file():
                return None
            body = path.read_bytes()
            status = 200
            content_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }.get(path.suffix.lower(), "")
        except Exception:
            return None
    else:
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


def fetch_image_payload(url: str, *, min_bytes: int = 3000) -> dict | None:
    """下载单张图片但不落盘，返回 {url, ext, bytes, contentType, sha256}。

    供来源单元写入器（write_source_unit）把图片直接落进来源 assets/，
    避免对象级散落 images/。非 200 / 过小 / 非图片 / 网络异常一律返回 None。
    """
    for candidate in candidate_image_urls(url):
        payload = _fetch_image_payload_once(candidate, min_bytes=min_bytes)
        if payload is not None:
            payload["requestedUrl"] = url
            payload["normalizedFromUrl"] = url if candidate != url else ""
            return payload
    return None


def fetch_image(url: str, images_dir: Path, *, index: int, min_bytes: int = 3000) -> dict | None:
    """下载单张图片到 images_dir/img_<index>.<ext>。

    仅落真实图片二进制（按魔数判定，拒 HTML/错误页）；非 200 / 过小 / 非图片 / 网络异常
    一律返回 None（不抛），由调用方决定是否记账或重试。
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    payload = fetch_image_payload(url, min_bytes=min_bytes)
    if payload is None:
        return None
    body = payload["bytes"]
    content_type = payload.get("contentType") or ""
    ext = payload["ext"]
    status = 200
    file_name = f"img_{index:02d}{ext}"
    (images_dir / file_name).write_bytes(body)
    return {
        "url": payload.get("url") or url,
        "requestedUrl": payload.get("requestedUrl") or url,
        "fileName": file_name,
        "statusCode": status,
        "contentType": content_type,
        "bytes": len(body),
        "sha256": payload.get("sha256") or hashlib.sha256(body).hexdigest(),
    }
