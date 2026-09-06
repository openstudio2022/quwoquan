"""轻量提示词模板 lint。

只检查声明 family 的三件套存在、变量声明一致、可渲染、无残留占位符、
system/task 行数合理。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core import prompt_render as pr  # noqa: E402

FAMILIES = pr.declared_prompt_names()



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




def main() -> int:
    errors: list[str] = []
    for name in FAMILIES:
        _check_family(name, errors)
    if errors:
        print("FAIL verify_prompt_templates:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"PASS verify_prompt_templates: {len(FAMILIES)} families, existence + placeholders + render + budgets OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
