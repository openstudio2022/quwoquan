"""Source text extraction and page-layout parsing."""
from __future__ import annotations

import html as html_lib
from html.parser import HTMLParser
import hashlib
import http.client
import json
import re
import subprocess
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.mediawiki_identity import parse_mediawiki_page_identity
from core.runtime_policy import active_runtime_policy
from governance.coverage.source_registry import resolve_travel_source_runtime

# Wikimedia/多数公共源要求 User-Agent 含 contact，否则触发严格限流(429)。
_USER_AGENT = (
    "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@quwoquan.example)"
)
_RUNTIME_POLICY = active_runtime_policy()
DOWNLOAD_TEXT_TIMEOUT_SECONDS = _RUNTIME_POLICY.download_text_timeout_seconds
DOWNLOAD_BYTES_TIMEOUT_SECONDS = _RUNTIME_POLICY.download_bytes_timeout_seconds
DOWNLOAD_CURL_RETRIES = _RUNTIME_POLICY.curl_retries
MEDIAWIKI_HTTP_FALLBACK_MAX_RETRIES = _RUNTIME_POLICY.mediawiki_fallback_retries
SUPPORTED_TEXT_EXTRACTORS: frozenset[str] = frozenset(
    {
        "wikipedia_api",
        "baidu_baike_html",
        "sogou_baike_html",
        "toutiao_baike_html",
        "qunar_html",
        "static_official_html",
        "generic_html",
    }
)


def _curl_get_text(url: str, *, timeout: int = DOWNLOAD_TEXT_TIMEOUT_SECONDS) -> str:
    proc = subprocess.run(
        [
            "curl", "-sS", "-L", "-A", _USER_AGENT,
            "--retry", str(DOWNLOAD_CURL_RETRIES),
            "--retry-delay", str(_RUNTIME_POLICY.curl_retry_delay_seconds),
            "--retry-all-errors",
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


@dataclass(frozen=True, slots=True)
class MediaWikiExtractPayload:
    text: str
    raw: str
    requested_title: str
    resolved_title: str
    redirect_chain: tuple[str, ...]



def _wikipedia_api_extract_payload(url: str) -> MediaWikiExtractPayload:
    from content.source.fetch_http import _http_get_bytes

    api_url = _wikipedia_api_url(url)
    _host, requested_title = _wikipedia_title_from_url(url)
    if not api_url:
        return MediaWikiExtractPayload("", "", requested_title, requested_title, ())
    try:
        raw = _curl_get_text(api_url)
    except Exception as first_exc:  # noqa: BLE001
        try:
            status, body, _ = _http_get_bytes(
                api_url,
                timeout=DOWNLOAD_TEXT_TIMEOUT_SECONDS,
                max_redirects=4,
                max_retries=MEDIAWIKI_HTTP_FALLBACK_MAX_RETRIES,
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
            max_retries=MEDIAWIKI_HTTP_FALLBACK_MAX_RETRIES,
        )
        raw = body.decode("utf-8", errors="ignore") if status == 200 else raw
    data = _mediawiki_json_loads(raw)
    query = data.get("query") if isinstance(data.get("query"), Mapping) else {}
    identity = parse_mediawiki_page_identity(
        data,
        requested_title=requested_title,
    )
    pages = query.get("pages") if isinstance(query, Mapping) else {}
    pages = pages if isinstance(pages, Mapping) else {}
    for page in pages.values():
        if not isinstance(page, Mapping):
            continue
        extract = str(page.get("extract") or "").strip()
        if extract:
            return MediaWikiExtractPayload(
                extract,
                raw,
                identity.requested_title,
                identity.resolved_title,
                identity.redirect_chain,
            )
    return MediaWikiExtractPayload(
        "",
        raw,
        identity.requested_title,
        identity.resolved_title,
        identity.redirect_chain,
    )


def _mediawiki_extmeta_value(meta: Mapping[str, Any], key: str) -> str:
    value = meta.get(key)
    if isinstance(value, Mapping):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def _mediawiki_clean_meta_text(value: str) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _wikipedia_api_plaintext(url: str) -> str:
    try:
        payload = _wikipedia_api_extract_payload(url)
    except Exception:
        return ""
    return payload.text


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

    _HEADING_TAGS = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}

    def __init__(self, base_url: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._figure_index = 0
        self._group_index = 0
        self._base_url = str(base_url or "")
        # 内联图清单：与 source.md 中 asset://source-inline-NNN 占位符一一对应（同序）。
        self._inline_images: list[dict[str, str]] = []
        # 相邻连续图缓冲：仅被空白/块边界分隔的连续 <img> 合并为单个 figuregroup（P2）。
        # 一旦出现真实文字（handle_data 非空白）即 flush，绝不跨正文段落误并。
        self._pending_images: list[dict[str, str]] = []
        # 标题保结构：进入 h1-h6 时压栈对应 markdown 前缀，handle_data 内据此产出 `#` 级标题。
        self._heading_prefix: str | None = None

    # lazy-load 图片真实地址常见承载属性（按优先级）：站点把真实图放进 data-*，
    # src 仅留 1px/loading 占位。RC3 必须取真实地址，否则游记数十张图被占位吞掉（漏图）。
    _LAZY_SRC_ATTRS = (
        "data-original",
        "data-actualsrc",
        "data-src",
        "data-lazy-src",
        "data-lazy",
        "data-echo",
    )
    # 占位/装饰图特征：lazy 占位 gif、1px 透明、loading/spinner/spacer 等，不作为正文配图。
    _PLACEHOLDER_SRC_RE = re.compile(
        r"(?:^|/)(?:blank|spacer|placeholder|loading|grey|gray|transparent|pixel|1x1|s\.gif|t\.gif|default)"
        r"[-_.a-z0-9]*\.(?:gif|png|svg)(?:[?#]|$)",
        re.IGNORECASE,
    )

    @classmethod
    def _usable_img_src(cls, src: str) -> str:
        """只放行可就地下载的 src（http/https/协议相对//或相对路径）。

        data: 内联、javascript:、about:、纯锚点 #、以及 1px/loading 等占位装饰图一律视为
        不可下载——这类 <img> 不再产生悬空的 asset://source-inline 占位（RC3：占位必须能锚定真实资产）。
        """
        s = str(src or "").strip()
        if not s:
            return ""
        low = s.lower()
        if low.startswith(("data:", "javascript:", "about:", "#")):
            return ""
        if cls._PLACEHOLDER_SRC_RE.search(s):
            return ""
        return s

    @classmethod
    def _resolve_img_src(cls, attr: dict[str, str]) -> str:
        """从 <img> 属性里解析真实可下载地址：优先 lazy data-*（真实图），再退回 src。

        lazy-load 站点（如去哪儿游记移动页）把真实图放 data-original/data-src 等，src 留占位；
        若先取 src 会吞掉真实图。这里先扫 lazy 属性取首个可用真实地址，无 lazy 再用 src。
        """
        for key in cls._LAZY_SRC_ATTRS:
            lazy = cls._usable_img_src(attr.get(key))
            if lazy:
                return lazy
        return cls._usable_img_src(attr.get("src"))

    def _flush_pending_images(self) -> None:
        """把缓冲的相邻连续图落为 markdown：单图→`:::figure`，≥2 张→单个 `:::figuregroup` 占位。"""
        pending = self._pending_images
        if not pending:
            return
        self._pending_images = []
        if len(pending) == 1:
            img = pending[0]
            self._chunks.append(
                f"\n:::figure\n![{img['caption']}](asset://{img['placeholderId']})\n{img['caption']}\n:::\n"
            )
            return
        self._group_index += 1
        lines = [f'\n:::figuregroup id="grp-{self._group_index:03d}" count="{len(pending)}"']
        for img in pending:
            lines.append(f"![{img['caption']}](asset://{img['placeholderId']})")
        lines.append(":::\n")
        self._chunks.append("\n".join(lines))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "img":
            attr = {key.lower(): value or "" for key, value in attrs}
            src = self._resolve_img_src(attr)
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
            # 缓冲：连续图（仅空白/块边界分隔）合并；遇真实文字/标题/结束才 flush。
            self._pending_images.append(
                {"placeholderId": asset_id, "caption": caption}
            )
            return
        if tag in self._HEADING_TAGS:
            # 标题保结构：先 flush 图缓冲，再起一行 markdown 标题前缀。
            self._flush_pending_images()
            self._heading_prefix = self._HEADING_TAGS[tag]
            self._chunks.append(f"\n\n{self._heading_prefix} ")
            return
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def inline_images(self) -> list[dict[str, str]]:
        return [dict(row) for row in self._inline_images]

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in self._HEADING_TAGS:
            self._heading_prefix = None
            self._chunks.append("\n")
            return
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = html_lib.unescape(data)
        if text.strip():
            # 出现真实正文/标题文字 ⇒ 连续图段落到此为止，先 flush 图缓冲再写文字。
            self._flush_pending_images()
            self._chunks.append(text)

    def text(self) -> str:
        self._flush_pending_images()
        return "".join(self._chunks)


def _html_to_plain_text(html: str, base_url: str = "") -> str:
    text, _ = _html_to_plain_text_with_inline_images(html, base_url)
    return text


# P3 三类解耦：来源页内联视频检测（文章类含视频则放弃——不把视频内容强行图文化）。
# 命中 <video>/<source type=video> 原生视频标签，或主流视频站点的 <iframe>/<embed> 嵌入。
_VIDEO_TAG_RE = re.compile(r"(?is)<video[\s/>]|<source\b[^>]*\btype=['\"]?video/")
_VIDEO_EMBED_HOST_RE = re.compile(
    r"(?is)<(?:iframe|embed)\b[^>]*\bsrc=['\"][^'\"]*"
    r"(?:youtube\.com|youtu\.be|youku\.com|bilibili\.com|player\.bilibili|"
    r"iqiyi\.com|v\.qq\.com|video\.qq\.com|douyin\.com|ixigua\.com|"
    r"miaopai\.com|vimeo\.com|/v\.swf|/video/|/player/)"
)


def html_has_inline_video(html: str) -> bool:
    """来源页是否以视频为主要载体（含原生 <video> 或主流视频站嵌入）。

    用于 P3「文章=图文混排或长文；含视频则放弃」判据：检测到内联视频即标记 hasVideo，
    内容计划据此弃稿（不把视频内容强行图文化，避免成稿与原文严重不符）。
    """
    text = str(html or "")
    if not text:
        return False
    return bool(_VIDEO_TAG_RE.search(text) or _VIDEO_EMBED_HOST_RE.search(text))


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


def _baike_extractor_source_kind(extractor: str) -> str:
    return {
        "baidu_baike_html": "home_baidu_baike",
        "sogou_baike_html": "home_sogou_baike",
        "toutiao_baike_html": "home_toutiao_baike",
    }.get(extractor, extractor)


def _baike_layout_and_text(
    html_bytes: bytes, url: str, *, extractor: str
) -> tuple[str, dict[str, Any]]:
    """百度/搜狗百科结构前端：HTML → 统一 IR + 从 IR 渲染的正文。

    禁止静默降级纯文本：解析失败返回空文本 + `parseStatus=rejected` 的 IR
    （含结构化 rejectReason），由质量门按真实正文快照裁决 retained/rejected。
    """
    from content.source.baike_layout import parse_baike_layout, render_layout_markdown

    body = html_bytes
    if not body:
        try:
            body = _curl_get_text(url).encode("utf-8")
        except Exception:
            body = b""
    layout = parse_baike_layout(
        body,
        source_kind=_baike_extractor_source_kind(extractor),
        extractor=extractor,
    )
    if layout.get("parseStatus") != "ok":
        return "", layout
    return render_layout_markdown(layout)[:50000], layout


def _baike_html_plaintext(url: str, *, extractor: str = "baidu_baike_html", html_bytes: bytes = b"") -> str:
    text, _layout = _baike_layout_and_text(html_bytes, url, extractor=extractor)
    return text


def _toutiao_baike_layout_and_text(
    html_bytes: bytes,
    url: str,
) -> tuple[str, dict[str, Any]]:
    """今日头条百科专用 DOM extractor；身份仍由 toutiao_baike 严格契约校验。"""
    structured_text, layout = _baike_layout_and_text(
        html_bytes,
        url,
        extractor="toutiao_baike_html",
    )
    html = html_bytes.decode("utf-8", errors="replace")
    dom_text, _inline_images = _html_to_plain_text_with_inline_images(html, url)
    dom_text = dom_text.strip()
    if len(dom_text) > len(structured_text):
        layout = {
            **layout,
            "parseStatus": "ok",
            "sourceKind": "home_toutiao_baike",
            "extractor": "toutiao_baike_html",
            "extractionMode": "toutiao_dom",
        }
        return dom_text[:50000], layout
    return structured_text[:50000], layout


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
    if extractor == "toutiao_baike_html":
        text, _layout = _toutiao_baike_layout_and_text(html_bytes, url)
        return text
    if extractor in {"baidu_baike_html", "sogou_baike_html"}:
        return _baike_html_plaintext(url, extractor=extractor, html_bytes=html_bytes)
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
    - 其它 extractor（wikipedia_api 图片走 source plan 单一入口，baike/official 非图文混排游记）：
      返回 (正文, [])，不就地抓内联图，避免引入跨源/二次网络的第二图源。
    """
    if extractor in {"qunar_html", "generic_html"}:
        return _qunar_html_with_inline_images(html_bytes, url)
    return extract_page_text(html_bytes, url, extractor=extractor), []
