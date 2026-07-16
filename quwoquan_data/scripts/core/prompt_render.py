"""提示词模板渲染器（P1 核心）：把 prompt 正文从 .py 字符串拼接迁出到 md 模板。

设计原则（参照 claude code / codex 业界系统提示词最佳实践）：
- **真相源外置**：所有 prompt 正文落 `quwoquan_data/prompts/{homepage,article,image,video,_shared}/*.md`，
  `.py` 只负责「加载模板 + 计算动态数据块 + 校验占位符 + 组装」，禁止再在脚本里硬编码 prompt 正文。
- **业界格式骨架**：系统提示词用 XML 标签分区（`<role>/<capabilities>/<constraints>(always/never)/
  <output_format>`），任务区承载动态上下文（`<documents>` + 底稿/素材），静态在前、动态在后，
  对齐 prompt caching（重复 author/rewind 共享前缀）。
- **占位符 + 校验**：模板用 `{{var}}` 占位、`{{> _shared/partials/x.md}}` 复用片段；
  渲染器按内容类型目录中的变量声明校验后填充；渲染后不得残留未闭合 `{{`/`}}`。

prompts 是受版本控制的契约真相源，跟代码仓库走（`_REPO_DATA_ROOT/prompts`），不随运行时
`QWQ_DATA_ROOT` 漂移；仅 `QWQ_PROMPTS_ROOT` 可显式覆盖（供测试）。
"""
from __future__ import annotations

import os
import re
import hashlib
from pathlib import Path
from typing import Any, Mapping

from core.paths import _REPO_DATA_ROOT

PROMPTS_ROOT = Path(os.environ.get("QWQ_PROMPTS_ROOT", _REPO_DATA_ROOT / "prompts"))

SYSTEM_KEY = "system"
TASK_KEY = "task"
PARTIALS_DIR = "_shared/partials"
_PROMPT_FAMILY = {
    "article_author": "article",
    "checkpoint_author_article": "article",
    "source_plan_article": "article",
    "checkpoint_author_image": "image",
    "image_curation": "image",
    "source_plan_image": "image",
    "checkpoint_build_homepage": "homepage",
    "checkpoint_content_plan": "homepage",
    "entity_homepage": "homepage",
    "homepage_independent_review": "homepage",
    "homepage_source_judge": "homepage",
    "source_plan_homepage": "homepage",
    "review_repair": "_shared",
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

    name: 模板族名（如 article_author / entity_homepage / image_curation / review_repair）。
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


def render_partial(name: str) -> str:
    """渲染单个 partial 正文（无变量填充；供 .py 做「按运行时条件二选一」装配）。

    正文真相源仍在 prompts/_shared/partials/**；调用方只做选择，不得拼接硬编码 prompt 正文。
    """
    rel = name if name.startswith(f"{PARTIALS_DIR}/") else f"{PARTIALS_DIR}/{name}"
    body = _expand_partials(_read_template_file(rel))
    if _VAR_RE.search(body):
        raise PromptTemplateError(f"partial {rel} must not use variables when rendered standalone")
    return body.strip() + "\n"


def prompt_template_material(name: str) -> dict[str, Any]:
    """返回可重放 Prompt 的模板组成，不包含任何运行时凭据。"""
    system_ref = system_template_path(name)
    task_ref = task_template_path(name)
    system_text = _read_template_file(system_ref)
    task_text = _read_template_file(task_ref)
    partial_refs: set[str] = set()

    def _collect(text: str) -> None:
        for match in _INCLUDE_RE.finditer(text):
            rel = match.group(1)
            if not rel.startswith(f"{PARTIALS_DIR}/"):
                rel = f"{PARTIALS_DIR}/{rel}"
            if rel in partial_refs:
                continue
            partial_refs.add(rel)
            _collect(_read_template_file(rel))

    _collect(system_text)
    _collect(task_text)
    partial_rows = [
        {"ref": rel, "sha256": f"sha256:{hashlib.sha256(_read_template_file(rel).encode('utf-8')).hexdigest()}"}
        for rel in sorted(partial_refs)
    ]
    return {
        "system": {
            "ref": system_ref,
            "sha256": f"sha256:{hashlib.sha256(system_text.encode('utf-8')).hexdigest()}",
        },
        "task": {
            "ref": task_ref,
            "sha256": f"sha256:{hashlib.sha256(task_text.encode('utf-8')).hexdigest()}",
        },
        "partials": partial_rows,
    }


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
    "render_partial",
    "prompt_template_material",
    "template_variables",
    "load_vars_schema",
    "system_template_path",
    "task_template_path",
    "vars_schema_path",
    "prompt_family",
    "fmt_bullets",
]
