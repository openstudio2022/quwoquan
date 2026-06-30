"""HTTP fetch and text extraction (pure IO, no semantic processing)."""
from __future__ import annotations

import html as html_lib
from html.parser import HTMLParser
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


def _wikipedia_title_from_url(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if not any(host.endswith(domain) for domain in ("wikipedia.org", "wikivoyage.org")):
        return "", ""
    if "/wiki/" not in parsed.path:
        return host, ""
    title = urllib.parse.unquote(parsed.path.split("/wiki/", 1)[1].split("#")[0])
    return host, title


def _wikipedia_api_url(url: str) -> str:
    host, title = _wikipedia_title_from_url(url)
    if not host or not title:
        return ""
    q = urllib.parse.urlencode({
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "titles": title,
        "format": "json",
    })
    return f"https://{host}/w/api.php?{q}"


def _mediawiki_json_loads(raw: str) -> Mapping[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        # Keep the original raw evidence, but parse a repaired copy when
        # MediaWiki extract text contains a literal malformed \u fragment.
        repaired = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", raw or "")
        data = json.loads(repaired or "{}")
    return data if isinstance(data, Mapping) else {}


def _wikipedia_api_extract_payload(url: str) -> tuple[str, str]:
    api_url = _wikipedia_api_url(url)
    if not api_url:
        return "", ""
    try:
        raw = _curl_get_text(api_url)
    except Exception as first_exc:  # noqa: BLE001
        try:
            status, body, _ = _http_get_bytes(
                api_url,
                timeout=DOWNLOAD_TEXT_TIMEOUT_SECONDS,
                max_redirects=4,
                max_retries=2,
            )
            raw = body.decode("utf-8", errors="ignore") if status == 200 else ""
        except Exception as fallback_exc:  # noqa: BLE001
            raise RuntimeError(
                f"wikipedia_api fetch failed for {api_url}: {first_exc}; fallback: {fallback_exc}"
            ) from first_exc
    if not str(raw or "").strip():
        status, body, _ = _http_get_bytes(
            api_url,
            timeout=DOWNLOAD_TEXT_TIMEOUT_SECONDS,
            max_redirects=4,
            max_retries=2,
        )
        raw = body.decode("utf-8", errors="ignore") if status == 200 else raw
    data = _mediawiki_json_loads(raw)
    pages = data.get("query", {}).get("pages") or {}
    for page in pages.values():
        extract = str(page.get("extract") or "").strip()
        if extract:
            return extract, raw
    return "", raw


def _mediawiki_extmeta_value(meta: Mapping[str, Any], key: str) -> str:
    value = meta.get(key)
    if isinstance(value, Mapping):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def _mediawiki_clean_meta_text(value: str) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _mediawiki_file_titles(url: str, *, limit: int = 8) -> tuple[str, list[str]]:
    host, title = _wikipedia_title_from_url(url)
    if not host or not title:
        return "", []
    q = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "pageimages|images",
            "redirects": "1",
            "titles": title,
            "pithumbsize": "1600",
            "imlimit": str(max(1, int(limit))),
            "format": "json",
        }
    )
    try:
        data = _mediawiki_json_loads(_curl_get_text(f"https://{host}/w/api.php?{q}") or "{}")
    except Exception:
        return host, []
    titles: list[str] = []
    pages = ((data.get("query") or {}).get("pages") or {}) if isinstance(data, Mapping) else {}
    for page in pages.values():
        if not isinstance(page, Mapping):
            continue
        pageimage = str(page.get("pageimage") or "").strip()
        if pageimage:
            titles.append(f"File:{pageimage}" if not pageimage.startswith("File:") else pageimage)
        for image in page.get("images") or []:
            if isinstance(image, Mapping):
                titles.append(str(image.get("title") or "").strip())
    seen: set[str] = set()
    out: list[str] = []
    for raw_title in titles:
        file_title = raw_title.strip()
        if not file_title or file_title in seen:
            continue
        suffix = Path(file_title.split(":", 1)[-1]).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        seen.add(file_title)
        out.append(file_title)
        if len(out) >= int(limit):
            break
    return host, out


# 维基/Commons 图片候选上限：下载所有与底稿相符的真实图（图标/SVG 已按扩展名/安全门排除），
# 不是只取 1-3 张。可经 QWQ_WIKI_IMAGE_CANDIDATE_LIMIT 调整。
WIKI_IMAGE_CANDIDATE_LIMIT = max(1, int(os.environ.get("QWQ_WIKI_IMAGE_CANDIDATE_LIMIT", "12")))


def _wikipedia_api_image_assets(url: str, *, limit: int = WIKI_IMAGE_CANDIDATE_LIMIT) -> list[dict[str, Any]]:
    host, titles = _mediawiki_file_titles(url, limit=max(limit * 2, limit))
    if not host or not titles:
        return []
    q = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "titles": "|".join(titles[:50]),
            "format": "json",
        },
        safe="|:",
    )
    try:
        data = _mediawiki_json_loads(_curl_get_text(f"https://{host}/w/api.php?{q}") or "{}")
    except Exception:
        return []
    pages = ((data.get("query") or {}).get("pages") or {}) if isinstance(data, Mapping) else {}
    assets: list[dict[str, Any]] = []
    for page in pages.values():
        if not isinstance(page, Mapping):
            continue
        file_title = str(page.get("title") or "").strip()
        imageinfo = page.get("imageinfo") or []
        if not imageinfo or not isinstance(imageinfo[0], Mapping):
            continue
        info = imageinfo[0]
        direct_url = str(info.get("url") or "").strip()
        if not direct_url:
            continue
        meta = info.get("extmetadata") if isinstance(info.get("extmetadata"), Mapping) else {}
        license_name = (
            _mediawiki_extmeta_value(meta, "LicenseShortName")
            or _mediawiki_extmeta_value(meta, "UsageTerms")
            or _mediawiki_extmeta_value(meta, "License")
        )
        credit = (
            _mediawiki_extmeta_value(meta, "Artist")
            or _mediawiki_extmeta_value(meta, "Credit")
            or _mediawiki_extmeta_value(meta, "ObjectName")
            or "Wikimedia Commons"
        )
        terms_url = _mediawiki_extmeta_value(meta, "LicenseUrl") or str(info.get("descriptionurl") or "").strip()
        if not license_name or not terms_url:
            continue
        asset_key = f"{file_title}|{direct_url}"
        assets.append(
            {
                "assetId": "asset_" + hashlib.sha1(asset_key.encode("utf-8")).hexdigest()[:16],
                "url": direct_url,
                "requestedUrl": direct_url,
                "sourceUrl": str(info.get("descriptionurl") or direct_url),
                "collectionPageUrl": str(info.get("descriptionurl") or direct_url),
                "license": _mediawiki_clean_meta_text(license_name),
                "credit": _mediawiki_clean_meta_text(credit),
                "termsUrl": terms_url,
                "usageScope": "wikimedia_commons_open_license_publish_candidate",
                "modelReleaseStatus": "not_required",
                "contentType": str(info.get("mime") or ""),
                "width": int(info.get("width") or 0),
                "height": int(info.get("height") or 0),
                "sourceCollectionId": "wikimedia_commons:" + hashlib.sha1(file_title.encode("utf-8")).hexdigest()[:16],
                "creator": _mediawiki_clean_meta_text(credit),
                "caption": file_title.split(":", 1)[-1].rsplit(".", 1)[0].replace("_", " "),
                "fileTitle": file_title,
            }
        )
        if len(assets) >= int(limit):
            break
    return assets


def _wikipedia_api_plaintext(url: str) -> str:
    try:
        extract, _raw = _wikipedia_api_extract_payload(url)
    except Exception:
        return ""
    return extract


class _InlineFigureHTMLTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self, base_url: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._figure_index = 0
        self._base_url = str(base_url or "")
        # 内联图清单：与 source.md 中 asset://source-inline-NNN 占位符一一对应（同序）。
        self._inline_images: list[dict[str, str]] = []

    @staticmethod
    def _usable_img_src(src: str) -> str:
        """只放行可就地下载的 src（http/https/协议相对//或相对路径）。

        data: 内联、javascript:、about:、纯锚点 # 一律视为不可下载——这类 <img>
        不再产生悬空的 asset://source-inline 占位（RC3：占位必须能锚定真实资产）。
        """
        s = str(src or "").strip()
        if not s:
            return ""
        low = s.lower()
        if low.startswith(("data:", "javascript:", "about:", "#")):
            return ""
        return s

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")
        if tag == "img":
            attr = {key.lower(): value or "" for key, value in attrs}
            src = self._usable_img_src(
                attr.get("src")
                or attr.get("data-src")
                or attr.get("data-original")
                or attr.get("data-lazy-src")
                or ""
            )
            if not src:
                # 无可下载 src ⇒ 不插入 figure（避免悬空占位、图文对不上）。
                return
            caption = (attr.get("alt") or attr.get("title") or "source image").strip()
            caption = re.sub(r"\s+", " ", html_lib.unescape(caption)) or "source image"
            self._figure_index += 1
            asset_id = f"source-inline-{self._figure_index:03d}"
            abs_src = urllib.parse.urljoin(self._base_url, src) if self._base_url else src
            self._inline_images.append(
                {
                    "placeholderId": asset_id,
                    "src": abs_src,
                    "rawSrc": src,
                    "caption": caption,
                }
            )
            self._chunks.append(
                f"\n:::figure\n![{caption}](asset://{asset_id})\n{caption}\n:::\n"
            )

    def inline_images(self) -> list[dict[str, str]]:
        return [dict(row) for row in self._inline_images]

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = html_lib.unescape(data)
        if text.strip():
            self._chunks.append(text)

    def text(self) -> str:
        return "".join(self._chunks)


def _html_to_plain_text(html: str, base_url: str = "") -> str:
    text, _ = _html_to_plain_text_with_inline_images(html, base_url)
    return text


def _html_to_plain_text_with_inline_images(
    html: str, base_url: str = ""
) -> tuple[str, list[dict[str, str]]]:
    """抽取正文 + 同序内联 <img> 清单。

    内联图占位 asset://source-inline-NNN 就地嵌入正文（保留图文交错），返回的清单
    src 已按 base_url 解析为绝对 URL，供来源单元写入器就地同源下载并锚定 sourceAssetRef。
    """
    text = str(html or "")
    match = re.search(
        r'(?is)<div[^>]+class="[^"]*mw-parser-output[^"]*"[^>]*>(.*)</div>\s*</div>\s*</div>',
        text,
    )
    if match:
        text = match.group(1)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    parser = _InlineFigureHTMLTextExtractor(base_url=base_url)
    inline_images: list[dict[str, str]] = []
    try:
        parser.feed(text)
        text = parser.text()
        inline_images = parser.inline_images()
    except Exception:  # noqa: BLE001
        text = re.sub(r"(?is)<[^>]+>", "\n", text)
        inline_images = []
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
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip(), inline_images


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
    raw = html_bytes.decode("utf-8", errors="replace")
    return _html_to_plain_text(raw, url)[:50000]


def _qunar_html_with_inline_images(
    html_bytes: bytes, url: str = ""
) -> tuple[str, list[dict[str, str]]]:
    raw = html_bytes.decode("utf-8", errors="replace")
    text, imgs = _html_to_plain_text_with_inline_images(raw, url)
    return text[:50000], imgs


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


def extract_page_text_with_inline_images(
    html_bytes: bytes, url: str = "", *, extractor: str = "generic_html"
) -> tuple[str, list[dict[str, str]]]:
    """抽取正文 + 同源内联 <img> 清单（RC3：图文混排游记就地配图真相源）。

    - qunar_html / generic_html：解析 html_bytes，返回 (正文, 内联图清单)；正文与
      extract_page_text 一致，清单 src 已解析为绝对 URL，按出现顺序与正文里的
      asset://source-inline-NNN 占位符一一对应。
    - 其它 extractor（wikipedia_api 走 API assets、baike/official 非图文混排游记）：
      返回 (正文, [])，不就地抓内联图，避免引入跨源/二次网络的第二图源。
    """
    if extractor in {"qunar_html", "generic_html"}:
        return _qunar_html_with_inline_images(html_bytes, url)
    return extract_page_text(html_bytes, url, extractor=extractor), []


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

    供来源单元写入器把 page.html/source.md 落进 `sources/{sourceUnitId}/`。
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
    source_extractor = str((source or {}).get("extractor") or "").strip()
    if source_extractor:
        runtime = {**runtime, "extractor": source_extractor, "sourceExtractorOverride": True}
    extractor = str(runtime.get("extractor") or "generic_html")
    if extractor == "wikipedia_api":
        text, raw = _wikipedia_api_extract_payload(url)
        body = raw.encode("utf-8")
        if not body:
            raise RuntimeError(f"fetch failed for {url} (wikipedia_api empty response)")
        assets = _wikipedia_api_image_assets(url)
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": body,
            "text": text[:50000],
            "assets": assets,
            "sha256": hashlib.sha256(body).hexdigest(),
            "runtime": {**runtime, "rawFormat": "mediawiki_api_json"},
        }
    status, body, _ = _http_get_bytes(url, timeout=20, max_redirects=4, max_retries=4)
    if status != 200 or not body:
        raise RuntimeError(f"fetch failed for {url} (status={status})")
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
                "curl", "-sS", "-L", "-A", _USER_AGENT,
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
    max_retries: int = 4,
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
    except Exception:
        pass
    return _curl_get_bytes(url, timeout=timeout, max_bytes=max_bytes)


def _fetch_image_payload_once(url: str, *, min_bytes: int = 3000, max_bytes: int = 0) -> dict | None:
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
            status, body, content_type = _http_get_bytes(url, max_bytes=max_bytes)
        except Exception:
            return None
    if status != 200 or len(body) < min_bytes:
        return None
    if int(max_bytes or 0) > 0 and len(body) > int(max_bytes):
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


def fetch_image_payload(url: str, *, min_bytes: int = 3000, max_bytes: int = 0) -> dict | None:
    """下载单张图片但不落盘，返回 {url, ext, bytes, contentType, sha256}。

    供来源单元写入器（write_source_unit）把图片直接落进来源 assets/，
    避免对象级散落 images/。非 200 / 过小 / 非图片 / 网络异常一律返回 None。
    """
    for candidate in candidate_image_urls(url):
        payload = _fetch_image_payload_once(candidate, min_bytes=min_bytes, max_bytes=max_bytes)
        if payload is not None:
            payload["requestedUrl"] = url
            payload["normalizedFromUrl"] = url if candidate != url else ""
            return payload
    return None


def fetch_image(
    url: str,
    images_dir: Path,
    *,
    index: int,
    min_bytes: int = 3000,
    max_bytes: int = 0,
) -> dict | None:
    """下载单张图片到 images_dir/img_<index>.<ext>。

    仅落真实图片二进制（按魔数判定，拒 HTML/错误页）；非 200 / 过小 / 非图片 / 网络异常
    一律返回 None（不抛），由调用方决定是否记账或重试。
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    payload = fetch_image_payload(url, min_bytes=min_bytes, max_bytes=max_bytes)
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


def _wikipedia_wikitext_api_url(url: str) -> str:
    host, title = _wikipedia_title_from_url(url)
    if not host or not title:
        return ""
    q = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "format": "json",
        }
    )
    return f"https://{host}/w/api.php?{q}"


def fetch_wikipedia_wikitext(url: str) -> str:
    """抓取维基页面 wikitext（段落级图片锚点 + 真 caption 真相源）。"""
    api_url = _wikipedia_wikitext_api_url(url)
    if not api_url:
        return ""
    try:
        raw = _curl_get_text(api_url)
    except Exception:  # noqa: BLE001
        try:
            status, body, _ = _http_get_bytes(
                api_url,
                timeout=DOWNLOAD_TEXT_TIMEOUT_SECONDS,
                max_redirects=4,
                max_retries=2,
            )
            raw = body.decode("utf-8", errors="ignore") if status == 200 else ""
        except Exception:  # noqa: BLE001
            return ""
    data = _mediawiki_json_loads(raw)
    parse_block = data.get("parse") if isinstance(data, Mapping) else {}
    if isinstance(parse_block, Mapping):
        return str(parse_block.get("wikitext") or parse_block.get("*") or "").strip()
    return ""


def enrich_source_unit_meta_wikitext(unit_dir: Path, page_url: str) -> None:
    """联网解析 wikitext，把 sectionOutline/imagePlacements 写入 meta 并回填 asset caption。"""
    from _common.io import read_json, write_json
    from _common.source_unit import SOURCE_UNIT_ASSET_INDEX, SOURCE_UNIT_MANIFEST
    from _common.wiki_wikitext import enrich_meta_from_wikitext

    wikitext = fetch_wikipedia_wikitext(page_url)
    if not wikitext:
        return
    meta_path = unit_dir / SOURCE_UNIT_MANIFEST
    if not meta_path.is_file():
        return
    meta = read_json(meta_path)
    if not isinstance(meta, dict):
        return
    enriched = enrich_meta_from_wikitext(meta, wikitext)
    write_json(meta_path, enriched)

    placements = enriched.get("imagePlacements") or []
    if not isinstance(placements, list) or not placements:
        return
    caption_by_file: dict[str, str] = {}
    for row in placements:
        if not isinstance(row, dict):
            continue
        fn = str(row.get("fileName") or "").strip()
        cap = str(row.get("caption") or "").strip()
        if fn and cap:
            caption_by_file[fn.lower()] = cap

    index_path = unit_dir / SOURCE_UNIT_ASSET_INDEX
    if not index_path.is_file() or not caption_by_file:
        return
    index_payload = read_json(index_path)
    assets = index_payload.get("assets") if isinstance(index_payload, dict) else []
    if not isinstance(assets, list):
        return
    changed = False
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        current = str(asset.get("caption") or "").strip()
        if current and not re.match(r"^\d{2,}[-_]", current):
            continue
        matched_cap = ""
        for key in (
            str(asset.get("fileName") or ""),
            Path(str(asset.get("url") or "")).name,
            Path(str(asset.get("sourceUrl") or "")).name,
        ):
            stem = Path(key.replace(" ", "_")).stem.lower()
            for file_key, cap in caption_by_file.items():
                file_stem = Path(file_key).stem.lower()
                if stem == file_stem or file_stem in stem or stem in file_stem:
                    matched_cap = cap
                    break
            if matched_cap:
                break
        if matched_cap:
            asset["caption"] = matched_cap
            if not str(asset.get("relevance") or "").strip() or asset.get("relevance") == current:
                asset["relevance"] = matched_cap
            changed = True
    if changed:
        write_json(index_path, index_payload)
