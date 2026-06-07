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

from _common.article_package import asset_id_from_object_key, compute_post_asset_id, parse_post_asset_id, post_asset_id


def test_legacy_object_key_helper_no_long_underscore_run():
    object_key = "asset-seed/post/稻城亚丁_体验/detail_1.jpg"
    aid = asset_id_from_object_key(object_key)
    assert "________" not in aid
    assert "___" not in aid  # 连续非法字符折叠为单个 _


def test_post_asset_id_uses_entity_role_batch_hash():
    aid = compute_post_asset_id(
        entity_name="稻城亚丁",
        role="cover",
        global_batch_seq=42,
        ref="地点_景区__稻城亚丁",
    )
    assert aid.startswith("稻城亚丁_cover_42_")
    parsed = parse_post_asset_id(aid)
    assert parsed["entityName"] == "稻城亚丁"
    assert parsed["role"] == "cover"
    assert parsed["globalBatchSeq"] == 42
    assert len(parsed["digest"]) == 8


def test_post_asset_id_stable_for_same_batch_seed():
    kwargs = dict(
        entity_name="洛绒牛场",
        role="node",
        global_batch_seq=42,
        ref="地点_景区__洛绒牛场",
    )
    assert post_asset_id(**kwargs) == post_asset_id(**kwargs)


def test_post_asset_id_changes_across_batch_seq():
    common = dict(entity_name="洛绒牛场", role="node", ref="地点_景区__洛绒牛场")
    a = post_asset_id(**common, global_batch_seq=42)
    b = post_asset_id(**common, global_batch_seq=43)
    assert a != b


def test_parse_post_asset_id_right_anchors_entity_name():
    aid = compute_post_asset_id(
        entity_name="稻城亚丁_高反提醒",
        role="detail",
        global_batch_seq=10000000,
        ref="地点_景区__稻城亚丁",
    )
    parsed = parse_post_asset_id(aid)
    assert parsed["entityName"] == "稻城亚丁_高反提醒"
    assert parsed["role"] == "detail"
    assert parsed["globalBatchSeq"] == 10000000
    assert parsed["raw"] == aid


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"asset id stability tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
