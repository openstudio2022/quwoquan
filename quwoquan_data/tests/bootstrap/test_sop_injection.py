"""sop few-shot 注入契约：build_writing_pack 读 sopExampleRef 指向的 example+guide，render_prompt_md 注入。

sop 是全局单一真相源（按实体类型），produce 只读注入做 few-shot。
隔离：DATA_ROOT 指向临时 sop 根；可直接运行 python3 quwoquan_data/tests/bootstrap/test_sop_injection.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="sop_inject_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common import paths  # noqa: E402
from _common.base_draft import FIDELITY_MAX, FIDELITY_MIN  # noqa: E402
from _common.writing_pack import _load_sop_fewshot, build_writing_pack, render_prompt_md  # noqa: E402

_EXAMPLE_MARK = "峨眉山金顶四大奇观示范段落"
_GUIDE_MARK = "禁止罗列清单的范式约束"


def _seed_sop(ref: str = "sop/主页/地点/景区/example.md") -> str:
    ex = paths.DATA_ROOT / ref
    ex.parent.mkdir(parents=True, exist_ok=True)
    ex.write_text(f"# 范例\n\n{_EXAMPLE_MARK}\n", encoding="utf-8")
    (ex.parent / "guide.md").write_text(f"# 规范\n\n{_GUIDE_MARK}\n", encoding="utf-8")
    return ref


def _build(brief: dict, ref: str = "entity-x") -> dict:
    return build_writing_pack(
        ref=ref,
        kind="entity",
        brief=brief,
        evidence_bundle={},
        assets=[],
        carrier="article",
        byline="资深旅行作者",
        publish_layout="entity",
        section_intents=["开篇动机"],
        source_urls=[],
        source_paths=[],
    )


def test_load_sop_fewshot_reads_example_and_guide():
    ref = _seed_sop()
    fs = _load_sop_fewshot(ref)
    assert fs is not None
    assert _EXAMPLE_MARK in fs["example"]
    assert _GUIDE_MARK in fs["guide"]


def test_load_sop_fewshot_missing_returns_none():
    assert _load_sop_fewshot(None) is None
    assert _load_sop_fewshot("sop/主页/地点/不存在类型/example.md") is None


def test_build_pack_injects_sop_into_prompt():
    ref = _seed_sop()
    pack = _build({"sopExampleRef": ref, "titleHint": "峨眉山"})
    assert pack["sopExampleRef"] == ref
    assert "sopFewshot" not in pack
    prompt = render_prompt_md(pack)
    assert "写作范例与规范" in prompt
    assert _EXAMPLE_MARK in prompt
    assert _GUIDE_MARK in prompt


def test_render_prompt_without_sop_does_not_crash():
    pack = _build({"titleHint": "无 sop"}, ref="entity-no-sop")
    assert "sopFewshot" not in pack
    prompt = render_prompt_md(pack)
    assert "写作范例与规范" not in prompt
    assert "## 必须覆盖的事实" in prompt


def test_render_prompt_unauthorized_base_uses_moderate_polish_retention():
    """版权风险全面放开：未授权底稿与授权底稿统一走「以底稿为基础适度润色、大面积保留」。

    不再有「事实参考材料 / 独立表达」分叉；贴合度门对所有来源生效。
    """
    pack = _build(
        {
            "titleHint": "峨眉山",
            "baseSourceRef": "entities/地点/景区/峨眉山/1.download/sources/01.base/source.md",
        },
        ref="entity-unauthorized-base",
    )
    pack["baseDraftText"] = "# 底稿\n\n这是一段底稿正文。"
    prompt = render_prompt_md(pack)
    assert f"{int(FIDELITY_MIN * 100)}%~{int(FIDELITY_MAX * 100)}%" in prompt
    assert "适度润色" in prompt
    assert "大面积保留" in prompt
    # 旧 factual 范式词汇必须消失
    assert "事实参考材料" not in prompt
    assert "独立表达" not in prompt
    assert "`draft.article.md`" in prompt


def test_sop_fewshot_passthrough_unchanged_for_all_sources():
    """全面放开后 few-shot 不再按来源模式降噪，example/guide 原样透传。"""
    pack = _build(
        {
            "titleHint": "峨眉山",
            "baseSourceRef": "entities/地点/景区/峨眉山/1.download/sources/01.base/source.md",
        },
        ref="entity-fewshot-passthrough",
    )
    pack["baseDraftText"] = "# 底稿\n\n这是一段底稿正文。"
    pack["sopFewshot"] = {
        "example": "以百科底稿为基础适度加工（轻改）。",
        "guide": "保留必要事实，去语病与错字，私人信息脱敏替代。",
    }
    prompt = render_prompt_md(pack)
    assert "以百科底稿为基础适度加工（轻改）。" in prompt
    assert "保留必要事实，去语病与错字，私人信息脱敏替代。" in prompt


def test_render_prompt_licensed_adaptation_uses_runtime_fidelity_range_and_draft_filename():
    pack = _build(
        {
            "titleHint": "峨眉山",
            "baseSourceRef": "entities/地点/景区/峨眉山/1.download/sources/01.base/source.md",
            "sourceUseMode": "licensed_adaptation",
        },
        ref="entity-fidelity",
    )
    pack["baseDraftText"] = "# 底稿\n\n这是一段底稿正文。"
    prompt = render_prompt_md(pack)
    assert f"{int(FIDELITY_MIN * 100)}%~{int(FIDELITY_MAX * 100)}%" in prompt
    assert "`draft.article.md`" in prompt
    assert "`article.md`" not in prompt


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"sop injection tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
