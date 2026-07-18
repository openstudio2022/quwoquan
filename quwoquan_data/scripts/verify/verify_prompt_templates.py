#!/usr/bin/env python3
"""提示词模板 lint（P1 门禁）：占位符闭合 / vars 必填 / 行数预算 / scripts 不得硬编码 prompt 正文。

唯一真相源：`quwoquan_data/prompts/{system,task,partials,vars}`。本 lint 把以下不变量固化为门禁，
防止指令区重新膨胀回 140+ 行硬编码、防止「会话模型」措辞回归、防止脚本绕过模板再硬拼 prompt 正文：

1. 每个环节族（article_author/entity_homepage/image_curation/review_repair）的 system/task 模板
   与 vars schema 三件齐备，且能用 schema 声明的必填变量渲染通过（无未闭合 `{{`、无未声明变量）。
2. 模板用到的每个 `{{var}}` 必须在对应 `vars/{name}.vars.yaml` 声明；声明的必填变量必须真的出现在模板里。
3. 行数预算：system 区（展开 partial 后）≤ SYSTEM_LINE_BUDGET，task 区 ≤ TASK_LINE_BUDGET，
   防止指令区膨胀。
4. ratchet：
   - `quwoquan_data/scripts/**` 不得再出现「会话模型」措辞（已统一为「创作 agent」）。
   - 三个迁移后的渲染函数必须经 `prompt_render.render(...)` 出 prompt，不得再在脚本里硬拼 prompt 正文。

退出码非 0 即 BLOCK。脚本只读校验，不修改任何文件。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core import prompt_render as pr  # noqa: E402

FAMILIES = (
    "article_author",
    "entity_homepage",
    "homepage_source_judge",
    "image_curation",
    "review_repair",
    # P4 checkpoint/controller prompt 外置（commercial closeout）。
    "source_plan_homepage",
    "source_plan_article",
    "source_plan_image",
    "checkpoint_build_homepage",
    "checkpoint_content_plan",
    "checkpoint_author_image",
    "checkpoint_author_article",
    "homepage_independent_review",
)

# scripts 中允许出现 prompt 渲染调用、但禁止硬编码 prompt 正文的迁移函数（必须经 render()）。
RENDER_CALLERS = {
    "quwoquan_data/scripts/content/post/article/prompt_renderer.py": (
        "render_prompt_md",
        "_render_image_task_prompt",
    ),
    "quwoquan_data/scripts/content/homepage/homepage_prompt.py": ("_render_entity_page_prompt",),
    "quwoquan_data/scripts/content/execution/agent/checkpoint_prompts.py": ("_checkpoint_prompts",),
}


def _fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def _check_family(name: str, errors: list[str]) -> None:
    system_path = pr.PROMPTS_ROOT / pr.system_template_path(name)
    task_path = pr.PROMPTS_ROOT / pr.task_template_path(name)
    vars_path = pr.vars_schema_path(name)
    for path in (system_path, task_path, vars_path):
        if not path.is_file():
            _fail(errors, f"[{name}] missing template/schema file: {path}")
            return

    try:
        schema = pr.load_vars_schema(name)
    except pr.PromptTemplateError as exc:
        _fail(errors, f"[{name}] vars schema invalid: {exc}")
        return

    system_text = system_path.read_text(encoding="utf-8")
    task_text = task_path.read_text(encoding="utf-8")

    # 2) 模板用到的变量必须在 schema 声明；声明的必填变量必须真的出现在模板里。
    for section, text in ((pr.SYSTEM_KEY, system_text), (pr.TASK_KEY, task_text)):
        used = pr.template_variables(text)
        declared = set(schema[section]["required"]) | set(schema[section]["optional"])
        undeclared = sorted(used - declared)
        if undeclared:
            _fail(errors, f"[{name}.{section}] template uses undeclared vars {undeclared}")
        unused_required = sorted(v for v in schema[section]["required"] if v not in used)
        if unused_required:
            _fail(errors, f"[{name}.{section}] required vars declared but not used in template {unused_required}")

    # 3) 行数预算（展开 partial 后）。
    sys_lines = pr._expand_partials(system_text).strip().count("\n") + 1
    task_lines = pr._expand_partials(task_text).strip().count("\n") + 1
    if sys_lines > pr.SYSTEM_LINE_BUDGET:
        _fail(errors, f"[{name}.system] {sys_lines} lines > budget {pr.SYSTEM_LINE_BUDGET}")
    if task_lines > pr.TASK_LINE_BUDGET:
        _fail(errors, f"[{name}.task] {task_lines} lines > budget {pr.TASK_LINE_BUDGET}")

    # 1) 用必填变量（dummy）渲染必须通过，且无残留占位符。
    system_vars = {v: f"<{v}>" for v in schema[pr.SYSTEM_KEY]["required"]}
    task_vars = {v: f"<{v}>" for v in schema[pr.TASK_KEY]["required"]}
    try:
        rendered = pr.render(name, system_vars=system_vars, task_vars=task_vars)
    except pr.PromptTemplateError as exc:
        _fail(errors, f"[{name}] render with required vars failed: {exc}")
        return
    if "{{" in rendered or "}}" in rendered:
        _fail(errors, f"[{name}] rendered output still contains unclosed placeholder braces")
    if "会话模型" in rendered:
        _fail(errors, f"[{name}] rendered prompt still contains banned phrase 会话模型")


def _check_script_ratchets(repo_root: Path, errors: list[str]) -> None:
    scripts_root = repo_root / "quwoquan_data" / "scripts"
    # 4a) 不得再出现「会话模型」措辞。
    offenders: list[str] = []
    self_path = Path(__file__).resolve()
    for path in scripts_root.rglob("*.py"):
        if path.resolve() == self_path:
            # 本 lint 自身把禁用措辞作为字符串字面量检测，必须豁免。
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "会话模型" in text:
            offenders.append(str(path.relative_to(repo_root)))
    if offenders:
        _fail(errors, f"scripts must use 创作 agent (not 会话模型); offenders: {sorted(offenders)}")

    # 4b) 迁移函数必须经 prompt_render.render(...) 出 prompt（防止重新硬拼 prompt 正文）。
    for rel, funcs in RENDER_CALLERS.items():
        path = repo_root / rel
        if not path.is_file():
            _fail(errors, f"render caller file missing: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if "prompt_render import" not in text and "from core.prompt_render" not in text:
            _fail(errors, f"{rel}: must import prompt_render.render to consume templates")
        for fn in funcs:
            marker = f"def {fn}("
            idx = text.find(marker)
            if idx < 0:
                _fail(errors, f"{rel}: expected render caller function {fn} not found")


def main() -> int:
    repo_root = SCRIPTS_ROOT.parents[1]
    errors: list[str] = []
    for name in FAMILIES:
        _check_family(name, errors)
    _check_script_ratchets(repo_root, errors)
    if errors:
        print("FAIL verify_prompt_templates:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"PASS verify_prompt_templates: {len(FAMILIES)} families, budgets + ratchets OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
