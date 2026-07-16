"""Low-level MediaWiki inline-markup parsing primitives."""
from __future__ import annotations

import re

from core.page_media import is_image_dimension_token


_FILE_PREFIX_RE = re.compile(r"^(?:File|文件|Image|图像|圖像):", re.IGNORECASE)
_LAYOUT_TOKENS = frozenset(
    {
        "thumb",
        "thumbnail",
        "frame",
        "frameless",
        "border",
        "left",
        "right",
        "center",
        "none",
        "upright",
        "缩略图",
        "有框",
        "无框",
        "左",
        "右",
        "居中",
    }
)
_IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif|svg|tiff?)$", re.IGNORECASE)


def split_top_level(params: str, sep: str = "|") -> list[str]:
    """Split only separators outside MediaWiki link/template nesting."""
    parts: list[str] = []
    buf: list[str] = []
    depth_link = 0
    depth_template = 0
    index = 0
    text = str(params or "")
    while index < len(text):
        pair = text[index : index + 2]
        if pair == "[[":
            depth_link += 1
            buf.append(pair)
            index += 2
            continue
        if pair == "]]" and depth_link:
            depth_link -= 1
            buf.append(pair)
            index += 2
            continue
        if pair == "{{":
            depth_template += 1
            buf.append(pair)
            index += 2
            continue
        if pair == "}}" and depth_template:
            depth_template -= 1
            buf.append(pair)
            index += 2
            continue
        char = text[index]
        if char == sep and not depth_link and not depth_template:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(char)
        index += 1
    parts.append("".join(buf))
    return parts


def strip_inline_markup(text: str) -> str:
    """Reduce inline MediaWiki markup to readable source text."""
    out = str(text or "")
    out = re.sub(r"(?is)<ref[^>/]*/>", "", out)
    out = re.sub(r"(?is)<ref[^>]*>.*?</ref>", "", out)
    out = re.sub(r"(?is)<!--.*?-->", "", out)
    for _ in range(6):
        stripped = re.sub(r"\{\{[^{}]*\}\}", "", out)
        if stripped == out:
            break
        out = stripped
    for _ in range(4):
        stripped = re.sub(
            r"\[\[(?![^\]]*?(?:File|文件|Image|图像|圖像):)([^\[\]|]*)(?:\|([^\[\]]*))?\]\]",
            lambda match: (match.group(2) if match.group(2) is not None else match.group(1)) or "",
            out,
        )
        if stripped == out:
            break
        out = stripped
    out = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", out)
    out = re.sub(r"\[https?://[^\]]+\]", "", out)
    out = re.sub(r"'''''|'''|''", "", out)
    out = re.sub(r"(?is)<br\s*/?>", " ", out)
    out = re.sub(r"(?is)<[^>]+>", "", out)
    return re.sub(r"[ \t]+", " ", out).strip()


def file_caption(params: str) -> str:
    """Extract the display caption without layout or dimension directives."""
    for part in reversed([item.strip() for item in split_top_level(params) if item.strip()]):
        lower = part.lower()
        if lower in _LAYOUT_TOKENS or is_image_dimension_token(lower):
            continue
        if re.match(r"^(?:upright|alt|link|lang|page|class)\s*=", lower):
            continue
        caption = strip_inline_markup(part)
        if caption:
            return caption
    return ""


def normalize_file_name(name: str) -> str:
    return _FILE_PREFIX_RE.sub("", str(name or "").strip()).strip().replace(" ", "_")


def is_file_reference(value: str) -> bool:
    return bool(_FILE_PREFIX_RE.match(str(value or "").strip()))


def extract_file_links(text: str) -> list[tuple[str, str, int, int]]:
    """Return file links with raw parameter text and source offsets."""
    rows: list[tuple[str, str, int, int]] = []
    raw = str(text or "")
    start_at = 0
    while True:
        start = raw.find("[[", start_at)
        if start < 0:
            break
        if not is_file_reference(raw[start + 2 : start + 12]):
            start_at = start + 2
            continue
        depth = 1
        end = start + 2
        while end < len(raw) and depth:
            pair = raw[end : end + 2]
            if pair == "[[":
                depth += 1
                end += 2
            elif pair == "]]":
                depth -= 1
                end += 2
            else:
                end += 1
        if depth:
            start_at = start + 2
            continue
        inner = raw[start + 2 : end - 2]
        parts = split_top_level(inner)
        file_name = normalize_file_name(parts[0]) if parts else ""
        params = "|".join(parts[1:]) if len(parts) > 1 else ""
        if file_name:
            rows.append((file_name, params, start, end))
        start_at = end
    return rows


def strip_file_links(text: str) -> str:
    rows = extract_file_links(text)
    if not rows:
        return str(text or "")
    raw = str(text or "")
    parts: list[str] = []
    cursor = 0
    for _name, _params, start, end in rows:
        parts.append(raw[cursor:start])
        cursor = end
    parts.append(raw[cursor:])
    return "".join(parts)


def is_image_file(file_name: str) -> bool:
    return bool(_IMAGE_EXT_RE.search(str(file_name or "")))
