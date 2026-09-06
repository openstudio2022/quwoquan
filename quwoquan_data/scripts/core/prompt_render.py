"""轻量提示词模板渲染器。

模板正文位于 `quwoquan_data/prompts/**`；本模块只负责 family 映射、partial 展开、
占位符校验和 system/task 拼接，不承担生产 caller 注册或业务编排。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping

from core.paths import _REPO_DATA_ROOT

PROMPTS_ROOT = Path(os.environ.get("QWQ_PROMPTS_ROOT", _REPO_DATA_ROOT / "prompts"))

SYSTEM_KEY = "system"
TASK_KEY = "task"
PARTIALS_DIR = "_shared/partials"
_PROMPT_FAMILY = {
    "article_author": "article",
    "content_independent_review": "_shared",
    "entity_homepage": "homepage",
    "homepage_source_judge": "homepage",
    "image_curation": "image",
    "video_author": "video",
}

# 系统/任务区行数预算（lint 与渲染契约共用：防止指令区重新膨胀回 140+ 行）。
SYSTEM_LINE_BUDGET = 80
TASK_LINE_BUDGET = 120

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_INCLUDE_RE = re.compile(r"\{\{\s*>\s*([a-zA-Z0-9_./-]+)\s*\}\}")
_OPEN_BRACE_RE = re.compile(r"\{\{")

# 物理分隔：系统提示词（静态）与任务上下文（动态）之间的可读边界。
SECTION_SEPARATOR = "\n\n---\n\n"


class PromptTemplateError(ValueError):
    """模板渲染契约违例（占位符未闭合 / 未声明变量 / 缺必填变量 / 模板缺失）。"""


def _read_template_file(rel_path: str) -> str:
    path = PROMPTS_ROOT / rel_path
    if not path.is_file():
        raise PromptTemplateError(f"prompt template not found: {rel_path} (under {PROMPTS_ROOT})")
    return path.read_text(encoding="utf-8")


def system_template_path(name: str) -> str:
    return f"{prompt_family(name)}/{name}.system.md"


def task_template_path(name: str) -> str:
    return f"{prompt_family(name)}/{name}.task.md"


def vars_schema_path(name: str) -> Path:
    return PROMPTS_ROOT / prompt_family(name) / f"{name}.vars.yaml"


def prompt_family(name: str) -> str:
    """Return the declared content family for a prompt, fail closed on drift."""
    try:
        return _PROMPT_FAMILY[name]
    except KeyError as exc:
        raise PromptTemplateError(f"prompt family is not declared: {name}") from exc


def declared_prompt_names() -> tuple[str, ...]:
    """Return the complete prompt contract surface in deterministic order."""
    return tuple(sorted(_PROMPT_FAMILY))


def _expand_partials(text: str, *, _seen: tuple[str, ...] = ()) -> str:
    """递归展开 `_shared/partials` 引用（防自包含死循环）。"""

    def _replace(match: re.Match[str]) -> str:
        rel = match.group(1)
        if not rel.startswith(f"{PARTIALS_DIR}/"):
            rel = f"{PARTIALS_DIR}/{rel}"
        if rel in _seen:
            raise PromptTemplateError(f"partial include cycle detected at {rel}")
        body = _read_template_file(rel)
        return _expand_partials(body, _seen=_seen + (rel,))

    return _INCLUDE_RE.sub(_replace, text)


def template_variables(text: str) -> set[str]:
    """模板（已展开 partial 后）声明的全部 `{{var}}` 名称。"""
    expanded = _expand_partials(text)
    return set(_VAR_RE.findall(expanded))


def load_vars_schema(name: str) -> dict[str, dict[str, list[str]]]:
    """读取内容类型目录中的变量 schema，声明 system/task 所需变量。"""
    path = vars_schema_path(name)
    if not path.is_file():
        raise PromptTemplateError(f"vars schema not found: {path}")
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise PromptTemplateError(f"vars schema must be a mapping: {path}")
    out: dict[str, dict[str, list[str]]] = {}
    for section in (SYSTEM_KEY, TASK_KEY):
        block = data.get(section) or {}
        if not isinstance(block, dict):
            raise PromptTemplateError(f"vars schema {path}: section {section} must be a mapping")
        out[section] = {
            "required": [str(x) for x in (block.get("required") or [])],
            "optional": [str(x) for x in (block.get("optional") or [])],
        }
    return out


def _neutralize_dynamic_delimiters(value: Any) -> str:
    """动态 source 文本可能含网页/脚本模板 `{{...}}`，插入 prompt 前中性化。

    模板本身仍由 `_render_section` 做严格占位符校验；这里仅防止抓取文本被误判成模板残留。
    """

    return str(value).replace("{{", "{ {").replace("}}", "} }")


def _fill(text: str, values: Mapping[str, Any]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return _neutralize_dynamic_delimiters(values.get(key, ""))

    return _VAR_RE.sub(_replace, text)


def _render_section(
    template_text: str,
    *,
    declared: dict[str, list[str]],
    values: Mapping[str, Any],
    section: str,
    name: str,
) -> str:
    expanded = _expand_partials(template_text)
    used_vars = set(_VAR_RE.findall(expanded))
    declared_all = set(declared["required"]) | set(declared["optional"])
    # 模板里用到的每个变量都必须在 vars schema 声明（防漂移/拼写错）。
    undeclared = sorted(used_vars - declared_all)
    if undeclared:
        raise PromptTemplateError(
            f"{name}.{section}: template uses undeclared vars {undeclared} (declare in vars/{name}.vars.yaml)"
        )
    static_without_declared_placeholders = _VAR_RE.sub("", expanded)
    if _OPEN_BRACE_RE.search(static_without_declared_placeholders) or "}}" in static_without_declared_placeholders:
        raise PromptTemplateError(
            f"{name}.{section}: unclosed/unknown placeholder remains after render"
        )
    # 必填变量必须由调用方提供（即使是空串也要显式给 key，避免静默漏块）。
    missing = sorted(v for v in declared["required"] if v not in values)
    if missing:
        raise PromptTemplateError(
            f"{name}.{section}: missing required vars {missing}"
        )
    rendered = _fill(expanded, values)
    if _OPEN_BRACE_RE.search(rendered):
        raise PromptTemplateError(
            f"{name}.{section}: unclosed/unknown placeholder remains after render"
        )
    return rendered.rstrip() + "\n"


def render(
    name: str,
    *,
    system_vars: Mapping[str, Any] | None = None,
    task_vars: Mapping[str, Any] | None = None,
) -> str:
    """渲染某环节 prompt：系统提示词（静态）+ 物理分隔 + 任务上下文（动态）。

    name: 模板族名（如 article_author / entity_homepage / content_independent_review）。
    """
    schema = load_vars_schema(name)
    system_text = _read_template_file(system_template_path(name))
    task_text = _read_template_file(task_template_path(name))
    system_block = _render_section(
        system_text, declared=schema[SYSTEM_KEY], values=system_vars or {}, section=SYSTEM_KEY, name=name
    )
    task_block = _render_section(
        task_text, declared=schema[TASK_KEY], values=task_vars or {}, section=TASK_KEY, name=name
    )
    return system_block.rstrip() + SECTION_SEPARATOR + task_block.rstrip() + "\n"


def fmt_bullets(items: Any, *, bullet: str = "-", empty: str = "（无）") -> str:
    """把列表渲染成 markdown bullet 块（动态数据块的统一构造器）。"""
    rows = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not rows:
        return empty
    return "\n".join(f"{bullet} {x}" for x in rows)


__all__ = [
    "PROMPTS_ROOT",
    "SYSTEM_LINE_BUDGET",
    "TASK_LINE_BUDGET",
    "SECTION_SEPARATOR",
    "PromptTemplateError",
    "SYSTEM_KEY",
    "TASK_KEY",
    "render",
    "template_variables",
    "load_vars_schema",
    "system_template_path",
    "task_template_path",
    "vars_schema_path",
    "prompt_family",
    "fmt_bullets",
]
