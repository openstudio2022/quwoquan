"""简体中文本地化门契约测试（确定性、离线、hermetic）。

覆盖：繁→简折叠、拉丁主导判定、发布字段（标题/正文）简体中文就绪门，
以及 caption 退化门复用同一繁简归一真相源（无第二套阈值/折叠表）。
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.localization import (  # noqa: E402
    fold_to_simplified,
    has_traditional_chars,
    latin_dominant,
    needs_translation_to_simplified,
    simplified_chinese_publish_issues,
)


def test_fold_to_simplified_folds_common_traditional_place_chars():
    assert fold_to_simplified("臺灣國家公園") == "台湾国家公园"
    assert fold_to_simplified("雲峽風景區") == "云峡风景区"
    assert fold_to_simplified("峨眉山，亦作峨嵋山") == "峨眉山，亦作峨嵋山"
    # 已是简体则原样返回。
    assert fold_to_simplified("九寨沟") == "九寨沟"
    assert fold_to_simplified("") == ""


def test_has_traditional_chars():
    assert has_traditional_chars("臺北") is True
    assert has_traditional_chars("台北") is False
    assert has_traditional_chars("Jiuzhaigou") is False


def test_latin_dominant_only_for_foreign_text():
    # 纯英文 → 拉丁主导。
    assert latin_dominant("Jiuzhaigou Valley Scenic Area") is True
    # 中文为主、夹少量拉丁 → 不算外文主导。
    assert latin_dominant("九寨沟风景区（Jiuzhaigou）") is False
    # 纯中文 → 非拉丁主导。
    assert latin_dominant("九寨沟风景区") is False
    # 纯数字/标点（无拉丁字母）→ 非外文。
    assert latin_dominant("2024-06-29") is False


def test_needs_translation_to_simplified():
    assert needs_translation_to_simplified("Mount Emei is a sacred mountain") is True
    assert needs_translation_to_simplified("峨眉山臺") is True  # 含繁体
    assert needs_translation_to_simplified("峨眉山") is False
    assert needs_translation_to_simplified("") is False


def test_simplified_chinese_publish_issues_flags_foreign_and_traditional():
    # 外文标题 → 须先译为简体中文。
    foreign = simplified_chinese_publish_issues(title="Jiuzhaigou Valley", body="九寨沟正文" * 20, label="x")
    assert any("标题为外文" in i for i in foreign), foreign
    # 繁体标题 → 须折叠为简体。
    trad = simplified_chinese_publish_issues(title="九寨溝風景區", body="九寨沟正文" * 20, label="x")
    assert any("标题含繁体" in i for i in trad), trad
    # 外文正文 → 须先译为简体中文。
    body_foreign = simplified_chinese_publish_issues(
        title="九寨沟", body="This is a long English body describing the valley scenery in detail."
    )
    assert any("正文为外文" in i for i in body_foreign), body_foreign
    # 纯简体中文标题 + 正文 → 无问题。
    clean = simplified_chinese_publish_issues(title="九寨沟风景区", body="九寨沟是世界自然遗产，沟内海子层叠。" * 10)
    assert clean == [], clean


def test_caption_gate_reuses_shared_latin_dominant():
    """caption 退化门复用共享 latin_dominant：行为不变（外文 caption 仍退化、中文 caption 通过）。"""
    from core.asset_placement import _caption_is_degraded

    assert _caption_is_degraded("Jiuzhaigou Valley scenic lake view") is True
    assert _caption_is_degraded("九寨沟五花海") is False
    assert _caption_is_degraded("") is True


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"localization simplified-chinese tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
