"""实体标注 ——「文章里把实体标成可点击/可关联的 inline 链接」。

评审痛点：主页与文章正文缺乏实体标注。方案分工（不引入外部模型，遵守 agent-only 契约）：
- NER（哪些是专有实体）由会话 agent 在 compose 阶段完成，落在 draft_meta.extractedEntities。
- 本模块只做确定性的「词典 grounding + inline 机械标注 + ref 闭环强校验」：
  把正文里提到、且在实体库有主页（可关联查看）的实体，首次出现处包成
  `[名称](/entity/{domain}/{type}/{name})`（与端侧既有实体链接语法一致）。

ref 闭环：标注的每个 /entity/ 引用必须
  1) 路径合法（domain/type/name 至少三段）；
  2) 命中候选词典（grounding，不得标注库外实体）；
  3) 登记在 manifest.entityRefs；
  4) 主实体（brief.entityRefs）必须在正文被标注（覆盖）。
"""
from __future__ import annotations

import re
from urllib.parse import unquote
from typing import Any, Mapping

from _common.entity_extract import (
    entity_ref,
    homepage_exists,
    normalize_entity_refs,
    resolve_domain_etype,
)

ENTITY_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(/entity/([^)\s]+)\)")
# 普通 markdown 链接 / 图片（含 asset://、http、/tag/ 等），标注时需整体跳过其文本区。
_MD_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\([^)\n]*\)")
_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.S)


def _iter_markdown_links(text: str) -> list[tuple[int, int, str, str]]:
    """Return markdown inline links, allowing balanced parentheses in hrefs."""
    out: list[tuple[int, int, str, str]] = []
    i = 0
    size = len(text)
    while i < size:
        start = text.find("[", i)
        if start < 0:
            break
        if start > 0 and text[start - 1] == "!":
            link_start = start - 1
        else:
            link_start = start
        close = text.find("](", start + 1)
        if close < 0:
            i = start + 1
            continue
        label = text[start + 1:close]
        if "\n" in label:
            i = start + 1
            continue
        href_start = close + 2
        depth = 1
        pos = href_start
        while pos < size:
            char = text[pos]
            if char == "\n":
                break
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    href = text[href_start:pos]
                    if not any(ch.isspace() for ch in href):
                        out.append((link_start, pos + 1, label, href))
                    i = pos + 1
                    break
            pos += 1
        else:
            i = start + 1
            continue
        if pos >= size or (pos < size and text[pos] == "\n"):
            i = start + 1
    return out


def normalize_link_ref(ref: str) -> str:
    """把 entity 引用统一为 /entity/{domain}/{type}/{name}（容忍带或不带 /entity/ 前缀）。"""
    parts = [p for p in unquote(str(ref).strip()).strip("/").split("/") if p]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    return "/entity/" + "/".join(parts) if parts else ""


def parse_entity_links(article: str) -> list[tuple[str, str]]:
    """解析正文里所有 inline 实体链接 → [(显示文本, 规范化 ref)]。"""
    out: list[tuple[str, str]] = []
    for _start, _end, label, href in _iter_markdown_links(article):
        if href.startswith("/entity/"):
            out.append((label, normalize_link_ref(href)))
    return out


def _split_frontmatter(article: str) -> tuple[str, str]:
    match = _FRONTMATTER_RE.match(article)
    if match:
        return article[: match.end()], article[match.end():]
    return "", article


def _link_spans(body: str) -> list[tuple[int, int]]:
    spans = [(start, end) for start, end, _label, _href in _iter_markdown_links(body)]
    # Keep the legacy regex as a safety net for malformed non-entity links.
    spans.extend((m.start(), m.end()) for m in _MD_LINK_RE.finditer(body))
    return sorted(set(spans))


def _entity_name_from_ref(ref: str) -> str:
    parts = [p for p in normalize_link_ref(ref).replace("/entity/", "").split("/") if p]
    return parts[-1] if len(parts) >= 3 else ""


def _clean_existing_entity_links(body: str, dictionary: Mapping[str, str]) -> str:
    """Normalize existing agent-authored entity links before mechanical annotation.

    The publish gate requires link text to equal the canonical entity name.  If
    the agent wrote an alias link to a grounded ref, canonicalize the label; if
    it linked an entity outside the dictionary, strip the link and keep text.
    """
    if not dictionary or "/entity/" not in body:
        return body
    grounded_refs = {normalize_link_ref(ref) for ref in dictionary.values()}
    links = _iter_markdown_links(body)
    if not links:
        return body
    out: list[str] = []
    cursor = 0
    changed = False
    for start, end, label, href in links:
        out.append(body[cursor:start])
        cursor = end
        if not href.startswith("/entity/"):
            out.append(body[start:end])
            continue
        ref = normalize_link_ref(href)
        if ref not in grounded_refs:
            out.append(label)
            changed = True
            continue
        canonical = _entity_name_from_ref(ref)
        if canonical and label != canonical:
            out.append(f"[{canonical}]({ref})")
            changed = True
        else:
            out.append(body[start:end])
    out.append(body[cursor:])
    return "".join(out) if changed else body


def build_entity_dictionary(
    task_id: str,
    batch_id: str,
    brief: Mapping[str, Any],
    draft_meta: Mapping[str, Any] | None,
) -> tuple[dict[str, str], list[str]]:
    """候选实体词典 {名称: /entity/全路径} + 主实体 required 列表（必须被标注）。

    主实体来自 brief.entityRefs（发布门保证有主页）；附加候选来自 agent NER 的
    extractedEntities 中「实体库已有主页」的那些（grounding：无主页者不进词典、不标注）。
    """
    subject_type = (brief.get("subject") or {}).get("type")
    required = normalize_entity_refs(brief.get("entityRefs"), subject_type)
    dictionary: dict[str, str] = {}
    for ref in required:
        dictionary[ref.split("/")[-1]] = ref
    for ent in (draft_meta or {}).get("extractedEntities") or []:
        if not isinstance(ent, Mapping):
            continue
        name = str(ent.get("name") or "").strip()
        if not name or name in dictionary:
            continue
        domain, etype = resolve_domain_etype(ent.get("type"))
        if homepage_exists(domain, etype, name, task_id, batch_id):
            dictionary[name] = entity_ref(domain, etype, name)
    return dictionary, required


def merge_entity_refs(brief: Mapping[str, Any], draft_meta: Mapping[str, Any] | None) -> list[str]:
    """compose entityRefs = 主实体（brief）∪ 被标注的关联实体（draft_meta.annotatedEntityRefs）。

    让 manifest.entityRefs 登记所有正文标注实体，标注闭环（标注→登记→主页）成立；
    annotate-entities 是必经阶段：被标注的关联实体经 draft_meta.annotatedEntityRefs 并入登记集。
    """
    subject_type = (brief.get("subject") or {}).get("type")
    refs = list(normalize_entity_refs(brief.get("entityRefs"), subject_type))
    for raw in (draft_meta or {}).get("annotatedEntityRefs") or []:
        normalized = normalize_link_ref(raw)
        if normalized and normalized not in refs:
            refs.append(normalized)
    return refs


def annotate_inline(article: str, dictionary: Mapping[str, str]) -> tuple[str, set[str]]:
    """把正文里候选实体首次出现处机械标成 inline 链接（幂等、不动 frontmatter、不嵌套已有链接）。"""
    frontmatter, body = _split_frontmatter(article)
    body = _clean_existing_entity_links(body, dictionary)
    already = {ref for _, ref in parse_entity_links(body)}
    annotated: set[str] = set(already)
    # 长名优先，避免「九寨沟沟口」中先标短名造成嵌套/截断。
    for name in sorted(dictionary, key=len, reverse=True):
        ref = dictionary[name]
        if ref in annotated:
            continue
        spans = _link_spans(body)
        for match in re.finditer(re.escape(name), body):
            if any(start <= match.start() < end for start, end in spans):
                continue
            body = body[: match.start()] + f"[{name}]({ref})" + body[match.end():]
            annotated.add(ref)
            break
    return frontmatter + body, annotated


def annotation_closure_issues(
    article: str,
    *,
    manifest_entity_refs: list[str],
    dictionary: Mapping[str, str],
    required_refs: list[str],
    require_coverage: bool = True,
) -> list[str]:
    """produce 阶段强校验：grounding + manifest 登记 + 文本一致 + 主实体覆盖。"""
    links = parse_entity_links(article)
    dict_refs = set(dictionary.values())
    manifest_set = {normalize_link_ref(r) for r in manifest_entity_refs}
    issues: list[str] = []
    seen: set[str] = set()
    for text, ref in links:
        parts = [p for p in ref.replace("/entity/", "").split("/") if p]
        if len(parts) < 3:
            issues.append(f"entity link ref malformed (need domain/type/name): {ref}")
            continue
        if dictionary and ref not in dict_refs:
            issues.append(f"entity link not grounded in dictionary (库外实体禁止标注): {ref}")
        if manifest_set and ref not in manifest_set:
            issues.append(f"annotated entity not in manifest.entityRefs (未登记): {ref}")
        if text != parts[-1]:
            issues.append(f"entity link text '{text}' != entity name '{parts[-1]}'")
        seen.add(ref)
    if require_coverage:
        for req in required_refs:
            if normalize_link_ref(req) not in seen:
                issues.append(f"primary entity not annotated in body (主实体未标注): {req}")
    return issues


def annotation_publish_issues(article: str, manifest_entity_refs: list[str]) -> list[str]:
    """发布强制门：manifest.entityRefs 每个实体必须在正文 inline 标注，且标注格式合法 + 登记闭环。"""
    links = parse_entity_links(article)
    manifest_set = {normalize_link_ref(r) for r in manifest_entity_refs}
    linked: set[str] = set()
    issues: list[str] = []
    for text, ref in links:
        parts = [p for p in ref.replace("/entity/", "").split("/") if p]
        if len(parts) < 3:
            issues.append(f"entity link ref malformed: {ref}")
            continue
        if ref not in manifest_set:
            issues.append(f"annotated entity not in manifest.entityRefs: {ref}")
        if text != parts[-1]:
            issues.append(f"entity link text '{text}' != entity name '{parts[-1]}'")
        linked.add(ref)
    for required in manifest_set:
        if required not in linked:
            issues.append(f"entity not annotated in body (manifest 实体必须正文标注): {required}")
    return issues


__all__ = [
    "ENTITY_LINK_RE",
    "normalize_link_ref",
    "parse_entity_links",
    "build_entity_dictionary",
    "merge_entity_refs",
    "annotate_inline",
    "annotation_closure_issues",
    "annotation_publish_issues",
]
