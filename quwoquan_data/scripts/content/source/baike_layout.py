"""HTML 百科结构前端：解析章节/段落/信息框进统一 IR（source.layout.json）。

替换旧 `_baike_html_plaintext` 的纯文本降级：

- ``h1`` → 词条标题；``h2/h3`` → ``heading``（剥离「编辑/播报/讨论」等平台按钮文本）
- 段落容器（``p`` 与 class 含 ``para`` 的 ``div``）→ ``paragraph``
- basic-info 信息框 ``dt/dd`` 键值对 → ``factRow``
- 正文 ``img`` 默认**不采**（``factual_citation_only`` 版权约束），只记录存在性
  证据 ``imageEvidence.imageCount``，供质量门判断「源站有图但不可用」。
- 解析失败（零章节零段落）必须产出 ``parseStatus=rejected`` + 结构化原因，
  禁止静默降级回纯文本。

文本产物同时从 IR 渲染（heading → ``## 标题``，factRow → ``键：值`` 行），
与 wiki 侧 source.md 的结构语义对齐。
"""
from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser
from typing import Any

from core.source_layout import (
    build_layout,
    make_fact_row_block,
    make_heading_block,
    make_paragraph_block,
    rejected_layout,
)
from core.section_outline import slugify_section

# 平台交互按钮/编辑痕迹：出现在标题或正文中的平台文本，非词条内容。
_PLATFORM_TOKEN_RE = re.compile(r"(?:编辑|播报|讨论|上传视频|收藏|查看|纠错|添加义项|\[\d+(?:-\d+)?\])")
# 页面导航/推荐/版权等区域的 class/id 特征：整块跳过。
_SKIP_CONTAINER_RE = re.compile(
    r"(?:navbar|nav-|footer|copyright|toolbar|recommend|related|comment|"
    r"catalog|lemma-?catalog|side|banner|advert|breadcrumb|top-tool|share|"
    r"reference|refer|tashuo|album|video)",
    re.IGNORECASE,
)
_PARA_CLASS_RE = re.compile(r"(?:^|[\s_-])para(?:[\s_-]|$)|para[_-]", re.IGNORECASE)
_BASIC_INFO_RE = re.compile(r"basic-?info|basicInfo", re.IGNORECASE)


class _BaikeStructParser(HTMLParser):
    """把百科 HTML 流式解析为 (title, events)；events 为结构块半成品序列。"""

    _HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.events: list[dict[str, Any]] = []
        self.image_count = 0
        self._skip_depth = 0
        self._suppress_depth = 0  # sup/引用角标等行内噪声
        self._container_skip_stack: list[str] = []
        self._text_target: str | None = None  # heading|paragraph|dt|dd
        self._text_level = 0
        self._buf: list[str] = []
        self._para_depth = 0
        # basic-info 容器栈：class 命中可能在外层 div 或 dl 本身（百度/搜狗结构不同）。
        self._basic_info_stack: list[str] = []

    # ── helpers ──────────────────────────────────────────────
    def _flush(self) -> None:
        if self._text_target is None:
            return
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        text = _PLATFORM_TOKEN_RE.sub("", text).strip()
        target, level = self._text_target, self._text_level
        self._text_target = None
        self._buf = []
        if not text:
            return
        if target == "heading":
            if level == 1 and not self.title:
                self.title = text
                return
            self.events.append({"kind": "heading", "level": max(2, level), "text": text})
        elif target == "paragraph":
            self.events.append({"kind": "paragraph", "text": text})
        elif target == "dt":
            self.events.append({"kind": "factKey", "text": text})
        elif target == "dd":
            self.events.append({"kind": "factValue", "text": text})

    @staticmethod
    def _attr_hay(attrs: list[tuple[str, str | None]]) -> str:
        return " ".join(
            str(value or "")
            for key, value in attrs
            if key.lower() in {"class", "id", "data-module", "data-tag"}
        )

    # ── HTMLParser hooks ─────────────────────────────────────
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        hay = self._attr_hay(attrs)
        if self._container_skip_stack:
            if tag in {"div", "section", "aside", "ul", "ol", "table", "dl"}:
                self._container_skip_stack.append(tag)
            return
        if tag in {"div", "section", "aside"} and _SKIP_CONTAINER_RE.search(hay) and not _BASIC_INFO_RE.search(hay):
            self._container_skip_stack.append(tag)
            return
        if tag == "sup":
            self._suppress_depth += 1
            return
        if self._suppress_depth:
            return
        if tag == "img":
            self.image_count += 1
            return
        if tag in self._HEADING_TAGS:
            self._flush()
            self._text_target = "heading"
            self._text_level = self._HEADING_TAGS[tag]
            return
        if self._basic_info_stack and tag in {"div", "dl"}:
            # basic-info 内嵌套容器：入栈保持 endtag 平衡（真实百科左右双列 dl）。
            self._basic_info_stack.append(tag)
            return
        if tag in {"div", "dl"} and _BASIC_INFO_RE.search(hay):
            self._basic_info_stack.append(tag)
            return
        if self._basic_info_stack and tag in {"dt", "dd"}:
            self._flush()
            self._text_target = tag
            return
        if tag == "p" or (tag == "div" and _PARA_CLASS_RE.search(hay)):
            self._flush()
            self._text_target = "paragraph"
            self._para_depth += 1
            return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if self._container_skip_stack:
            if tag == self._container_skip_stack[-1]:
                self._container_skip_stack.pop()
            return
        if tag == "sup":
            if self._suppress_depth:
                self._suppress_depth -= 1
            return
        if tag in self._HEADING_TAGS or tag in {"dt", "dd"}:
            self._flush()
            return
        if self._basic_info_stack and tag == self._basic_info_stack[-1]:
            self._flush()
            self._basic_info_stack.pop()
            return
        if tag == "p" or (tag == "div" and self._para_depth):
            if self._text_target == "paragraph":
                self._flush()
            if tag != "p" and self._para_depth:
                self._para_depth -= 1
            return

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._suppress_depth or self._container_skip_stack:
            return
        if self._text_target is not None:
            self._buf.append(html_lib.unescape(data))


def parse_baike_layout(
    html_bytes: bytes | str,
    *,
    source_kind: str,
    extractor: str,
) -> dict[str, Any]:
    """HTML 百科页面 → 统一结构化 IR。

    解析失败（零章节零段落零信息框）返回 ``parseStatus=rejected``，原因
    ``baike_structure_not_found``（反抓取空壳/验证码页等由质量门按低分处理）。
    """
    raw = (
        html_bytes.decode("utf-8", errors="replace")
        if isinstance(html_bytes, (bytes, bytearray))
        else str(html_bytes or "")
    )
    if not raw.strip():
        return rejected_layout(
            source_kind=source_kind, extractor=extractor, reject_reason="empty_html"
        )
    parser = _BaikeStructParser()
    try:
        parser.feed(raw)
        parser._flush()  # noqa: SLF001 —— 同模块内部收尾
    except Exception as exc:  # noqa: BLE001
        return rejected_layout(
            source_kind=source_kind,
            extractor=extractor,
            reject_reason=f"html_parse_error: {exc}",
        )

    blocks: list[dict[str, Any]] = []
    section_slug = ""
    pending_key = ""
    for event in parser.events:
        kind = event["kind"]
        text = event["text"]
        if kind == "heading":
            section_slug = slugify_section(text)
            blocks.append(make_heading_block(int(event["level"]), text, section_slug))
            pending_key = ""
        elif kind == "paragraph":
            if len(text) >= 2:
                blocks.append(make_paragraph_block(text, section_slug))
            pending_key = ""
        elif kind == "factKey":
            pending_key = text
        elif kind == "factValue":
            if pending_key:
                blocks.append(make_fact_row_block(pending_key, text))
                pending_key = ""

    has_structure = any(b["type"] in {"heading", "paragraph", "factRow"} for b in blocks)
    if not has_structure:
        return rejected_layout(
            source_kind=source_kind,
            extractor=extractor,
            title=parser.title,
            reject_reason="baike_structure_not_found",
        )
    return build_layout(
        source_kind=source_kind,
        extractor=extractor,
        title=parser.title,
        blocks=blocks,
        # 版权约束：非开放图源不采图，只记录存在性证据供质量门消费。
        image_evidence={"imageCount": parser.image_count, "imagesUsable": False},
    )


def render_layout_markdown(layout: dict[str, Any]) -> str:
    """从 IR 渲染 source.md 正文（单一真相源：`source_layout.render_source_markdown`）。

    baike 源不采图（IR 无 figure 块），占位开关关闭以显式表达契约。
    """
    from core.source_layout import render_source_markdown

    return render_source_markdown(layout, figure_placeholder=False)


__all__ = ["parse_baike_layout", "render_layout_markdown"]
