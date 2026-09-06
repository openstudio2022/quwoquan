"""轻量 prompt family 的渲染与单产物契约。"""
from __future__ import annotations

import pytest

from core import prompt_render as pr

FAMILIES = pr.declared_prompt_names()
AUTHOR_FAMILIES = ("entity_homepage", "article_author", "image_curation", "video_author")


def _required_dummy(name: str) -> tuple[dict[str, str], dict[str, str]]:
    schema = pr.load_vars_schema(name)
    system_vars = {v: f"<{v}>" for v in schema[pr.SYSTEM_KEY]["required"]}
    task_vars = {v: f"<{v}>" for v in schema[pr.TASK_KEY]["required"]}
    return system_vars, task_vars


def test_declared_prompt_contract_matches_template_triplets():
    discovered: set[str] = set()
    for path in pr.PROMPTS_ROOT.glob("*/*.system.md"):
        name = path.name.removesuffix(".system.md")
        if (path.parent / f"{name}.task.md").is_file() and (path.parent / f"{name}.vars.yaml").is_file():
            discovered.add(name)
    assert discovered == set(FAMILIES)
    assert set(FAMILIES) == {
        "article_author",
        "content_independent_review",
        "entity_homepage",
        "homepage_source_judge",
        "image_curation",
        "video_author",
    }


@pytest.mark.parametrize("name", FAMILIES)
def test_family_renders_with_required_vars(name):
    system_vars, task_vars = _required_dummy(name)
    out = pr.render(name, system_vars=system_vars, task_vars=task_vars)
    assert pr.SECTION_SEPARATOR in out
    assert out.index("<role>") < out.index(pr.SECTION_SEPARATOR)
    assert "{{" not in out and "}}" not in out
    assert "会话模型" not in out


@pytest.mark.parametrize("name", AUTHOR_FAMILIES)
def test_author_prompt_has_minimal_inputs_and_single_output(name):
    schema = pr.load_vars_schema(name)
    assert schema[pr.TASK_KEY]["required"] == [
        "target",
        "retained_evidence_excerpts",
        "selected_blueprint_intent",
        "output_path",
    ]
    system_vars, task_vars = _required_dummy(name)
    out = pr.render(name, system_vars=system_vars, task_vars=task_vars)
    assert "evidence" in out
    assert "selected blueprint" in out
    for stale in ("creativePlan", "selfCritique", "draft_meta.json", "author_self_check.json", "agent_result_envelope.json"):
        assert stale not in out


def test_review_prompt_has_unified_content_review_contract():
    name = "content_independent_review"
    system_vars, task_vars = _required_dummy(name)
    out = pr.render(name, system_vars=system_vars, task_vars=task_vars)
    schema = pr.load_vars_schema(name)
    assert schema[pr.TASK_KEY]["required"] == [
        "draft",
        "claim_evidence_refs",
        "assets_rights_packet",
    ]
    assert schema[pr.TASK_KEY]["optional"] == []
    assert "content_review.json" in out
    assert "approved" in out and "rejected" in out
    assert "dimensions" in out
    assert "blockingIssues" in out
    assert "assetRights" in out
    assert "不修改" in out and "不运行任何命令" in out
    for stale in ("final manifest", "provenance", "objectDir", "executionId"):
        assert stale not in out


def test_article_prompt_keeps_asset_order_boundary_lightweight():
    system_vars, task_vars = _required_dummy("article_author")
    out = pr.render("article_author", system_vars=system_vars, task_vars=task_vars)
    assert "selected_blueprint_intent" in out
    assert "assetRef" in out


def test_missing_required_var_raises():
    schema = pr.load_vars_schema("article_author")
    required = schema[pr.TASK_KEY]["required"]
    partial = {v: "x" for v in required[:-1]}
    with pytest.raises(pr.PromptTemplateError, match="missing required vars"):
        pr.render("article_author", task_vars=partial)


def test_undeclared_var_in_template_raises():
    with pytest.raises(pr.PromptTemplateError, match="undeclared vars"):
        pr._render_section(
            "hello {{ghost}}",
            declared={"required": [], "optional": []},
            values={"ghost": "x"},
            section="task",
            name="probe",
        )


def test_dynamic_source_delimiters_are_neutralized():
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
    with pytest.raises(pr.PromptTemplateError, match="unclosed"):
        pr._render_section(
            "value: {{x}} {{not-allowed}}",
            declared={"required": ["x"], "optional": []},
            values={"x": "ok"},
            section="task",
            name="probe",
        )


def test_template_variables_expands_partials():
    text = pr._read_template_file(pr.system_template_path("article_author"))
    used = pr.template_variables(text)
    assert used == set()
    assert "evidence-conditioned" in pr._expand_partials(text)


def test_fmt_bullets_handles_empty_and_items():
    assert pr.fmt_bullets([]) == "（无）"
    assert pr.fmt_bullets(["a", "", "  ", "b"]) == "- a\n- b"


def _run_all() -> None:
    import sys

    sys.exit(pytest.main([__file__, "-q"]))


if __name__ == "__main__":
    _run_all()
