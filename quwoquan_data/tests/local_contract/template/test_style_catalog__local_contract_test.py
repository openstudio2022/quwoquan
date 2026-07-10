"""文风族与开篇策略注册表契约测试 ——「美·开篇不千篇一律」。

覆盖：openingStrategies 库完整、每族 allowedOpenings 多样且引用合法、按所选族语义化检测开篇策略、
writing_pack 下发的开篇引导块、catalog 结构 lint。catalog 为 committed 真相源，按脚本相对路径定位。
可直接运行 python3 quwoquan_data/tests/local_contract/template/test_style_catalog__local_contract_test.py
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

import sys
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.style_catalog import (  # noqa: E402
    detect_opening_strategy,
    family_allowed_openings,
    known_opening_strategy_ids,
    known_style_families,
    opening_guidance,
    opening_strategies,
    opening_strategy_options,
)
from template.registry import TemplateRegistry  # noqa: E402
from template.style import validate_style_catalog  # noqa: E402


def test_opening_strategies_library_complete():
    strategies = opening_strategies()
    assert {"scene_immersion", "personal_motivation", "question_hook", "conclusion_first"} <= set(strategies)
    for sid, meta in strategies.items():
        assert meta.get("label"), sid
        assert meta.get("markers"), sid


def test_each_family_has_diverse_allowed_openings():
    families = known_style_families()
    assert "实用攻略风" in families and "旅途随笔风" in families
    strategy_ids = known_opening_strategy_ids()
    for fam in families:
        allowed = family_allowed_openings(fam)
        assert len(allowed) >= 2, f"{fam} should allow >=2 openings to avoid monotony"
        assert all(sid in strategy_ids for sid in allowed), (fam, allowed)


def test_attack_strategy_specific_per_family():
    # 攻略体偏结论先行、游记体偏场景沉浸/动机：不同体裁开篇策略集合不应完全相同。
    guide = set(family_allowed_openings("实用攻略风"))
    journal = set(family_allowed_openings("旅途随笔风"))
    assert guide != journal
    assert "conclusion_first" in guide
    assert "scene_immersion" in journal


def test_unknown_family_falls_back_to_default_set():
    allowed = family_allowed_openings("不存在的体裁风")
    assert "personal_motivation" in allowed and "scene_immersion" in allowed


def test_detect_opening_strategy_hits_within_family():
    # 旅途随笔风允许 scene_immersion：含"清晨/推开"应命中。
    text = "清晨我推开木门，雾还压在山脊上。"
    assert detect_opening_strategy(text, "旅途随笔风") == "scene_immersion"
    # 攻略体允许 conclusion_first：含"先说结论"应命中。
    assert detect_opening_strategy("先说结论：淡季来最值。", "实用攻略风") == "conclusion_first"


def test_detect_returns_none_for_monotonous_opening():
    # 评审痛点开头：套路化、未落任何策略钩子 → 攻略体下应判 None（门据此拦截）。
    monotonous = "九寨沟的风景，我在屏幕上看了无数遍，总怕亲眼一看会不过如此。"
    assert detect_opening_strategy(monotonous, "实用攻略风") is None


def test_opening_guidance_payload_for_pack():
    guidance = opening_guidance("实用攻略风")
    assert guidance["styleFamily"] == "实用攻略风"
    opts = guidance["openingStrategies"]
    assert opts and all("id" in o and "label" in o and "hint" in o for o in opts)
    # markers 不应下发给 agent（避免诱导填词凑门）。
    assert all("markers" not in o for o in opts)
    assert guidance["styleFamilyCandidates"]
    assert "千篇一律" in guidance["instruction"]


def test_opening_strategy_options_resolves_labels():
    opts = opening_strategy_options("旅途随笔风")
    ids = {o["id"] for o in opts}
    assert "scene_immersion" in ids
    assert all(o["label"] for o in opts)


def test_catalog_structure_is_valid():
    registry = TemplateRegistry.load()
    assert validate_style_catalog(registry) == [], validate_style_catalog(registry)


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"style catalog tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
