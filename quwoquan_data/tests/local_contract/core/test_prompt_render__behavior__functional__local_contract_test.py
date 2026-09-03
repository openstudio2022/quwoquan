"""P1 契约：提示词模板渲染器（core.prompt_render）。

固化「提示词膨胀且未分区 / 会话模型措辞 / review gate 硬门复述」复盘后的不变量：
- 四个环节族都能用必填变量渲染通过，输出 = 系统区(静态) + 物理分隔 + 任务区(动态)；
- 渲染器对缺必填变量 / 模板用到未声明变量 / 渲染后残留占位符，均抛 PromptTemplateError；
- partial 复用与自包含死循环防护；fmt_bullets 动态数据块构造器行为稳定；
- 渲染产物不得出现「会话模型」措辞；article 任务区必须带回 figure / figuregroup 占位契约。
"""
from __future__ import annotations

import pytest

from core import prompt_render as pr

FAMILIES = pr.declared_prompt_names()


def test_declared_prompt_contract_matches_template_triplets():
    discovered: set[str] = set()
    for path in pr.PROMPTS_ROOT.glob("*/*.system.md"):
        name = path.name.removesuffix(".system.md")
        if (path.parent / f"{name}.task.md").is_file() and (
            path.parent / f"{name}.vars.yaml"
        ).is_file():
            discovered.add(name)
    assert discovered == set(FAMILIES)


def _required_dummy(name: str) -> tuple[dict, dict]:
    schema = pr.load_vars_schema(name)
    system_vars = {v: f"<{v}>" for v in schema[pr.SYSTEM_KEY]["required"]}
    task_vars = {v: f"<{v}>" for v in schema[pr.TASK_KEY]["required"]}
    return system_vars, task_vars


@pytest.mark.parametrize("name", FAMILIES)
def test_family_renders_with_required_vars(name):
    system_vars, task_vars = _required_dummy(name)
    out = pr.render(name, system_vars=system_vars, task_vars=task_vars)
    # 系统区在前、任务区在后，中间有物理分隔。
    assert pr.SECTION_SEPARATOR in out
    assert out.index("<role>") < out.index(pr.SECTION_SEPARATOR)
    # 无残留占位符，无禁用措辞。
    assert "{{" not in out and "}}" not in out
    assert "会话模型" not in out


def test_article_task_carries_figure_group_contract():
    system_vars, task_vars = _required_dummy("article_author")
    out = pr.render("article_author", system_vars=system_vars, task_vars=task_vars)
    # P2 连续图合并占位契约：AI 必须原样带回 figure / figuregroup 占位。
    assert "<figure_contract>" in out
    assert ":::figure" in out
    assert ":::figuregroup" in out


def test_missing_required_var_raises():
    schema = pr.load_vars_schema("article_author")
    required = schema[pr.TASK_KEY]["required"]
    assert required, "article_author 任务区应有必填变量"
    partial = {v: "x" for v in required[:-1]}  # 故意漏最后一个必填
    with pytest.raises(pr.PromptTemplateError) as exc:
        pr.render("article_author", task_vars=partial)
    assert "missing required vars" in str(exc.value)


def test_undeclared_var_in_template_raises():
    # 直接对内部 section 渲染器喂一个用到未声明变量的模板，必须报未声明。
    with pytest.raises(pr.PromptTemplateError) as exc:
        pr._render_section(
            "hello {{ghost}}",
            declared={"required": [], "optional": []},
            values={"ghost": "x"},
            section="task",
            name="probe",
        )
    assert "undeclared vars" in str(exc.value)


def test_dynamic_source_delimiters_are_neutralized():
    # 真实网页/脚本片段可能含 `{{...}}`，动态数据应中性化而不是误判为模板残留。
    out = pr._render_section(
        "value: {{x}}",
        declared={"required": ["x"], "optional": []},
        values={"x": "leftover {{y}}"},
        section="task",
        name="probe",
    )
    assert "{{" not in out and "}}" not in out
    assert "leftover { {y} }" in out


def test_unclosed_static_placeholder_after_render_raises():
    # 模板自身的非法占位符仍然是契约错误。
    with pytest.raises(pr.PromptTemplateError) as exc:
        pr._render_section(
            "value: {{x}} {{not-allowed}}",
            declared={"required": ["x"], "optional": []},
            values={"x": "ok"},
            section="task",
            name="probe",
        )
    assert "unclosed" in str(exc.value)


def test_template_variables_expands_partials():
    # 任务模板里通过 partial 引入的变量也应被识别为模板变量。
    text = pr._read_template_file(pr.task_template_path("article_author"))
    used = pr.template_variables(text)
    assert "title" in used
    assert "must_include_facts_block" in used


def test_fmt_bullets_handles_empty_and_items():
    assert pr.fmt_bullets([]) == "（无）"
    assert pr.fmt_bullets(["a", "", "  ", "b"]) == "- a\n- b"


def _run_all() -> None:  # 允许直跑（与其它本地契约测试一致）。
    import sys

    sys.exit(pytest.main([__file__, "-q"]))


if __name__ == "__main__":
    _run_all()
