"""Source-unit metadata and title derivation for article base drafts."""
from __future__ import annotations
import re
from typing import Any
from core.io import read_json
from core.paths import execution_root
from content.post.article.base_draft import load_base_draft_text

def base_source_unit_meta(execution_id: str, base_source_ref: str | None) -> dict[str, Any]:
    """读取来源单元 meta.json（sourceId/platform/sourceUseMode 等），缺失返回空 dict。

    作为来源单元元信息的唯一读取入口：base_source_use_mode 取权利模式、
    works_gate 取 sourceId/platform 解析来源专业度，共享同一份路径解析，
    避免重复推导来源目录（R25）。
    """
    if not base_source_ref:
        return {}
    candidate = execution_root(execution_id) / str(base_source_ref)
    unit_dir = candidate if candidate.is_dir() else candidate.parent
    meta_path = unit_dir / "meta.json"
    if meta_path.is_file():
        try:
            meta = read_json(meta_path)
        except (OSError, ValueError):
            return {}
        if isinstance(meta, dict):
            return dict(meta)
    return {}

def base_source_use_mode(execution_id: str, base_source_ref: str | None) -> str:
    """读取来源单元权利模式；旧来源默认按事实参考处理，禁止误启用轻改门。"""
    mode = str(base_source_unit_meta(execution_id, base_source_ref).get("sourceUseMode") or "").strip()
    return mode or "factual_reference_only"

SOURCE_TITLE_MIN_CHARS = 4

SOURCE_TITLE_MAX_CHARS = 40

_TITLE_PLATFORM_SUFFIX_RE = re.compile(
    r"[\s_\|｜·–—\-]+("
    r"携程(攻略社区|旅行|旅游)?|马蜂窝|去哪儿(网|旅行)?|途牛(旅游网)?|同程(旅行|旅游)?|"
    r"小红书|知乎(专栏)?|百度(百科|经验|旅游)?|美篇|穷游(网)?|驴妈妈(旅游网)?|飞猪|"
    r"大众点评|新浪(旅游|博客)?|搜狐(旅游|号)?|腾讯(旅游|网|新闻)?|网易(旅游|号)?|"
    r"旅游网|旅行网|景区官网|官方网站|官网|维基百科|wikipedia|wikivoyage|wikitravel"
    r")\s*$",
    re.IGNORECASE,
)

_TITLE_NOISE_RE = re.compile(r"[\u3010\u3008\u300a\[\(（【].*?[\u3011\u3009\u300b\]\)）】]\s*$")

_SOURCE_ID_LIKE_RE = re.compile(r"^[0-9]+[\._-]|_(base|src|source)_?\d*$|^[a-z0-9]+[._][a-z0-9_]+$")

def _clean_source_title(raw: str) -> str:
    title = re.sub(r"\s+", " ", str(raw or "").strip())
    if not title:
        return ""
    # 反复剥离尾部平台/站点后缀（可能链式：`… - 携程攻略社区`）。
    for _ in range(4):
        stripped = _TITLE_PLATFORM_SUFFIX_RE.sub("", title).strip(" _|｜·–—-")
        if stripped == title:
            break
        title = stripped
    # 去掉尾部括注（如「（图）」「【攻略】」）。
    title = _TITLE_NOISE_RE.sub("", title).strip(" _|｜·–—-")
    if len(re.sub(r"\s+", "", title)) > SOURCE_TITLE_MAX_CHARS:
        title = title[:SOURCE_TITLE_MAX_CHARS].rstrip(" _|｜·–—-，,、")
    return title

def _looks_like_source_id(value: str, *, source_id: str = "") -> bool:
    compact = str(value or "").strip()
    if not compact:
        return True
    if source_id and compact == source_id:
        return True
    return bool(_SOURCE_ID_LIKE_RE.search(compact))

def _first_heading_title(body: str) -> str:
    for line in (body or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading = re.match(r"^#{1,4}\s+(.+?)\s*#*$", stripped)
        if heading:
            return heading.group(1).strip()
    return ""

def extract_source_title(execution_id: str, base_source_ref: str | None) -> str:
    """从单一底稿（来源单元）派生发布标题：meta.title → 正文首标题，剥平台痕迹 + 长度约束。

    返回清洗后的可用标题；取不出（空/过短/仅为来源 id）时返回 ""，由上游对 article 源弃稿。
    """
    if not base_source_ref:
        return ""
    meta = base_source_unit_meta(execution_id, base_source_ref)
    source_id = str(meta.get("sourceId") or "").strip()
    candidate = _clean_source_title(str(meta.get("title") or ""))
    if not _looks_like_source_id(candidate, source_id=source_id) and len(
        re.sub(r"\s+", "", candidate)
    ) >= SOURCE_TITLE_MIN_CHARS:
        return candidate
    # 回退：底稿正文首个 markdown 标题。
    body = load_base_draft_text(execution_id, base_source_ref)
    heading = _clean_source_title(_first_heading_title(body))
    if not _looks_like_source_id(heading, source_id=source_id) and len(
        re.sub(r"\s+", "", heading)
    ) >= SOURCE_TITLE_MIN_CHARS:
        return heading
    return ""
