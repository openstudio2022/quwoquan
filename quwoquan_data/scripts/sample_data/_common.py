"""示例数据标准化生成器 — v5

提供实体三件套 + post manifest 的标准化生成函数，
强制四分组前缀、必含 geoTagRef、旅行类实体必含 Topic/旅行/* tagRef。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common.paths import NOW_ISO  # noqa: E402

VALID_PREFIXES = ("Topic/", "Audience/", "Format/", "Entity/")
TRAVEL_ENTITY_TYPES = {"景区", "主题乐园", "古镇", "住宿", "遗址", "自然景观", "打卡地"}

_ENTITY_PAGE_MIN_CHARS = 800
_POST_ARTICLE_MIN_CHARS = 300


def validate_tag_refs(tag_refs: list[str], context: str = ""):
    """校验 tagRefs 四分组前缀。"""
    for ref in tag_refs:
        if not any(ref.startswith(p) for p in VALID_PREFIXES):
            raise ValueError(f"tagRef 前缀非法: '{ref}' (context: {context})")


def validate_entity(entity: dict, context: str = ""):
    """校验实体必含 geoTagRef 和 tagRefs。"""
    if "geoTagRef" not in entity or not entity["geoTagRef"]:
        raise ValueError(f"实体缺少 geoTagRef (context: {context})")
    if not entity["geoTagRef"].startswith("Topic/地理/行政区/"):
        raise ValueError(
            f"geoTagRef 必须以 Topic/地理/行政区/ 开头: '{entity['geoTagRef']}' (context: {context})"
        )
    validate_tag_refs(entity.get("tagRefs", []), context)


def validate_travel_post(manifest: dict, entity_type: str, context: str = ""):
    """校验旅行类实体的 post 必含 Topic/旅行/* tagRef。"""
    if entity_type in TRAVEL_ENTITY_TYPES:
        tag_refs = manifest.get("tagRefs", [])
        has_travel = any(r.startswith("Topic/旅行/") for r in tag_refs)
        if not has_travel:
            raise ValueError(f"旅行类实体 post 缺少 Topic/旅行/* tagRef (context: {context})")
    validate_tag_refs(manifest.get("tagRefs", []), context)


def make_entity(
    name: str,
    label_en: str,
    description: str,
    domain: str,
    etype: str,
    geo_tag_ref: str,
    tag_refs: list[str],
    **extra,
) -> dict:
    """创建标准实体 JSON。"""
    entity = {
        "label": name,
        "labelEn": label_en,
        "description": description,
        "geoTagRef": geo_tag_ref,
        "tagRefs": tag_refs,
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }
    entity.update(extra)
    validate_entity(entity, f"{domain}/{etype}/{name}")
    return entity


def _pad_markdown(md: str, min_len: int, pad_paragraph: str) -> str:
    out = md
    n = 0
    while len(out) < min_len:
        n += 1
        out += f"\n\n{pad_paragraph}（补充段落 {n}）"
    return out


def make_entity_page(
    name: str, domain: str, etype: str, description: str, highlights: list[str]
) -> str:
    """生成实体主页 markdown。"""
    lines = [f"# {name}\n"]
    lines.append(f"> {description}\n")
    lines.append(f"类型：[/entity/{domain}/{etype}/{name}](/entity/{domain}/{etype}/{name})\n")
    lines.append("## 亮点\n")
    for h in highlights:
        lines.append(f"- {h}")
    lines.append("")
    lines.append(f"相关标签：[/tag/Topic/旅行](/tag/Topic/旅行)\n")
    lines.append(f"封面图：asset://images/{domain}/{etype}/{name}/cover.jpg\n")
    lines.append("\n## 行前规划与串联建议\n")
    lines.append(
        f"本页聚合 **{name}** 的公开信息口径，便于与同路线节点一起做日程拼装。建议同时对照行政地理标签与交通标签，"
        "核对预约政策、开放时间、闭馆维护与季节性风险（高原反应、冰雪路况、雨季滑坡等）。"
        "内容占位图统一使用 `asset://`，后续可替换为完成权属与授权核验的正式素材。\n"
    )
    lines.append(
        "若你把本实体作为行程中枢，请把周边用餐、住宿与接驳写进同一张时间表里，避免到现场再临时改线。"
        "对亲子、银发与独行等人群，优先把无障碍与应急联络路径写出来，降低信息摩擦。\n"
    )
    body = "\n".join(lines)
    pad = (
        f"关于 **{name}**（{domain}/{etype}）的规划提示：请用 [/entity/{domain}/{etype}/{name}](/entity/{domain}/{etype}/{name}) "
        f"作为主引用，并用 [/tag/Topic/旅行](/tag/Topic/旅行) 聚合主题。封面占位：`asset://images/{domain}/{etype}/{name}/cover.jpg`。"
    )
    return _pad_markdown(body, _ENTITY_PAGE_MIN_CHARS, pad)


def make_entity_manifest(
    name: str, domain: str, etype: str, tag_refs: list[str], entity_refs: list[str] | None = None
) -> dict:
    """创建实体 manifest JSON。"""
    validate_tag_refs(tag_refs, f"manifest:{domain}/{etype}/{name}")
    manifest = {
        "entityRefs": entity_refs or [],
        "assets": [],
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }
    return manifest


def make_post_manifest(
    title: str, entity_ref: str, tag_refs: list[str], content_type: str = "article"
) -> dict:
    """创建 post manifest JSON。"""
    validate_tag_refs(tag_refs, f"post:{title}")
    return {
        "contentType": content_type,
        "entityRefs": [entity_ref],
        "tagRefs": tag_refs,
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }


def make_post_article(
    title: str,
    entity_name: str,
    domain: str,
    etype: str,
    angle: str,
    body_paragraphs: list[str],
) -> str:
    """生成 post 文章 markdown。"""
    lines = [f"# {title}\n"]
    lines.append(
        f"实体引用：[/entity/{domain}/{etype}/{entity_name}](/entity/{domain}/{etype}/{entity_name})\n"
    )
    for p in body_paragraphs:
        lines.append(f"{p}\n")
    lines.append(f"标签引用：[/tag/Format/内容角度/{angle}](/tag/Format/内容角度/{angle})\n")
    lines.append(f"封面图：asset://images/posts/{title}/cover.jpg\n")
    lines.append("\n## 小结与延伸阅读\n")
    lines.append(
        "本文用于 v5 示例数据的结构验证：正文段落可替换为真实采编内容；"
        "引用链需保持 `/entity/`、`/tag/` 与 `asset://` 三类线索同时存在，便于后续 produce/publish 管线做一致性校验。\n"
    )
    body = "\n".join(lines)
    pad = (
        f"（段落补充）**{title}** 关联实体 [/entity/{domain}/{etype}/{entity_name}](/entity/{domain}/{etype}/{entity_name})，"
        f"角度标签 [/tag/Format/内容角度/{angle}](/tag/Format/内容角度/{angle})，封面 `asset://images/posts/{title}/cover.jpg`。"
    )
    return _pad_markdown(body, _POST_ARTICLE_MIN_CHARS, pad)


def write_entity(
    task_root: Path,
    domain: str,
    etype: str,
    name: str,
    entity_json: dict,
    page_md: str,
    manifest_json: dict,
):
    """写入实体三件套到 task 目录。

    其中 `_entity.json` 是事实源，`manifest.json` 只保存发布/索引元数据。
    """
    edir = task_root / "entities" / domain / etype / name
    edir.mkdir(parents=True, exist_ok=True)
    (edir / "_entity.json").write_text(
        json.dumps(entity_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (edir / "page.md").write_text(page_md, encoding="utf-8")
    (edir / "manifest.json").write_text(
        json.dumps(manifest_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_post(
    task_root: Path,
    content_type: str,
    angle: str,
    title: str,
    seq: int,
    article_md: str,
    manifest_json: dict,
):
    """写入 post 到 task 目录。

    目录角度仅使用最后一段（如 `攻略`），与 tagRefs 中 `Format/内容角度/攻略` 全路径区分。
    """
    pdir = task_root / "posts" / content_type / angle / title / str(seq)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "article.md").write_text(article_md, encoding="utf-8")
    (pdir / "manifest.json").write_text(
        json.dumps(manifest_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_task_manifest(task_root: Path, task_id: str, entity_count: int, post_count: int):
    """写入 task_manifest.json。"""
    manifest = {
        "taskId": task_id,
        "operationType": "add",
        "status": "published",
        "entityCount": entity_count,
        "postCount": post_count,
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }
    (task_root / "task_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
