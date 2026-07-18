"""HTML text, inline-image and inline-video extraction."""
from __future__ import annotations
import html as html_lib
from html.parser import HTMLParser
import re
import urllib.parse

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
