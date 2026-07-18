"""成品资产命名稳定性/可读性/解析契约。"""
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

SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import pytest

from core.article_package import compute_post_asset_id, parse_post_asset_id, post_asset_id
from core.asset_identity import caption_file_token


def test_post_asset_id_uses_entity_role_caption_batch_hash():
    aid = compute_post_asset_id(
        entity_name="稻城亚丁",
        role="cover",
        execution_sequence=42,
        ref="地点_景区__稻城亚丁",
        caption="牛奶海秋色",
    )
    assert aid.startswith("稻城亚丁_cover_牛奶海秋色_42_")
    parsed = parse_post_asset_id(aid)
    assert parsed.entity_name == "稻城亚丁"
    assert parsed.role == "cover"
    assert parsed.caption_token == "牛奶海秋色"
    assert parsed.execution_sequence == 42
    assert len(parsed.digest) == 8


def test_caption_token_cleaning_and_truncation():
    # 清洗：折叠标点/空格；截断 ≤16 字符。
    token = caption_file_token("金顶：云海之上（清晨拍摄，光线最佳，值得早起）", entity_name="峨眉山")
    assert len(token) <= 16
    assert token.startswith("金顶_云海之上")
    aid = compute_post_asset_id(
        entity_name="峨眉山",
        role="detail",
        execution_sequence=42,
        ref="地点_景区__峨眉山",
        caption="金顶：云海之上（清晨拍摄，光线最佳，值得早起）",
    )
    parsed = parse_post_asset_id(aid)
    assert parsed.caption_token == token


def test_caption_degrades_to_section_then_ordinal_then_entity():
    # 图注退化（占位词）→ sectionSlug
    assert (
        caption_file_token("图片", section_slug="交通与到达", ordinal=3, entity_name="峨眉山")
        == "交通与到达"
    )
    # 图注 + section 均退化 → 图{ordinal}
    assert caption_file_token("", section_slug="1", ordinal=3, entity_name="峨眉山") == "图3"
    # 全部退化且无序号 → 实体名
    assert caption_file_token("", section_slug="", ordinal=0, entity_name="峨眉山") == "峨眉山"
    # 与实体同名的图注视为退化
    assert caption_file_token("峨眉山", section_slug="", ordinal=2, entity_name="峨眉山") == "图2"


def test_caption_not_in_hash_seed():
    common = dict(entity_name="洛绒牛场", role="node", ref="地点_景区__洛绒牛场", execution_sequence=42)
    a = post_asset_id(**common, caption="海子倒影")
    b = post_asset_id(**common, caption="雪山近景")
    assert a.rsplit("_", 1)[1] == b.rsplit("_", 1)[1], "caption 不进 seed，digest 必须一致"
    assert a != b


def test_post_asset_id_stable_for_same_batch_seed():
    kwargs = dict(
        entity_name="洛绒牛场",
        role="node",
        execution_sequence=42,
        ref="地点_景区__洛绒牛场",
        caption="海子倒影",
    )
    assert post_asset_id(**kwargs) == post_asset_id(**kwargs)


def test_post_asset_id_changes_across_batch_seq():
    common = dict(entity_name="洛绒牛场", role="node", ref="地点_景区__洛绒牛场", caption="海子倒影")
    a = post_asset_id(**common, execution_sequence=42)
    b = post_asset_id(**common, execution_sequence=43)
    assert a != b


def test_parse_post_asset_id_right_anchors_entity_name():
    aid = compute_post_asset_id(
        entity_name="稻城亚丁_高反提醒",
        role="detail",
        execution_sequence=10000000,
        ref="地点_景区__稻城亚丁",
        caption="垭口风雪",
    )
    parsed = parse_post_asset_id(aid)
    assert parsed.entity_name == "稻城亚丁_高反提醒"
    assert parsed.role == "detail"
    assert parsed.caption_token == "垭口风雪"
    assert parsed.execution_sequence == 10000000
    assert parsed.raw == aid


def test_parse_accepts_caption_with_underscore_and_digits():
    aid = compute_post_asset_id(
        entity_name="峨眉山",
        role="detail",
        execution_sequence=42,
        ref="r",
        caption="夜景 2026",
    )
    parsed = parse_post_asset_id(aid)
    assert parsed.caption_token == "夜景_2026"
    assert parsed.execution_sequence == 42


def test_parse_rejects_asset_id_without_caption_segment():
    with pytest.raises(ValueError, match="invalid post asset id"):
        parse_post_asset_id("峨眉山_cover_42_a1b2c3d4")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"asset id stability tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
