"""M3a 内容对象路由：ref → posts/{type}/{angle}/{title}/{seq}/ + _shared 路由索引。

规格 §2.4/§2.5/§15：内容对象坐标 compose 阶段即确定；ref→coords 路由是批次内唯一真相，
供 draft_io / stage 写入 / materialize / 读取端一致解析。
可直接运行 python3 quwoquan_data/tests/common/test_content_object_router.py
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

_TMP = Path(tempfile.mkdtemp(prefix="content_obj_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common import content_object as co  # noqa: E402
from _common.paths import batch_root  # noqa: E402

_TASK = "旅行/地域/四川省/景区/景区全覆盖"
_BATCH = "co_b1"


def test_compute_coords_from_brief_is_deterministic():
    brief = {"titleHint": "峨眉山·攻略", "templateId": "景区_深度_体验"}
    c = co.compute_content_coords(brief, "article")
    assert c["contentType"] == "article"
    assert c["title"] == "峨眉山·攻略"
    assert c["angle"] == "深度探险", c  # templateId 含「深度」→ 深度探险


def test_compute_coords_rejects_empty_title_hint():
    try:
        co.compute_content_coords({"titleHint": "   ", "templateId": "景区环线攻略"}, "article")
    except ValueError as exc:
        assert "titleHint missing or empty" in str(exc)
        return
    raise AssertionError("expected ValueError for empty titleHint")


def test_register_and_resolve_object_dirs():
    brief = {"titleHint": "峨眉山·攻略", "templateId": "景区环线攻略"}
    ref = "地点_景区__峨眉山"
    coords = co.register_from_brief(_TASK, _BATCH, ref, brief)
    assert coords["seq"] == 1
    assert coords["angle"] == "环线攻略"
    # 路由索引落 _shared
    idx = co.index_path(_TASK, _BATCH)
    assert idx.parent.name == "_shared"
    assert idx.parent.parent == batch_root(_TASK, _BATCH)
    # 对象目录 = posts/{type}/{angle}/{title}/{seq}
    obj = co.content_object_dir(_TASK, _BATCH, ref)
    rel = obj.relative_to(batch_root(_TASK, _BATCH)).as_posix()
    assert rel == "posts/article/环线攻略/峨眉山·攻略/1", rel
    # 阶段目录带序号
    assert co.content_object_stage_dir(_TASK, _BATCH, ref, "3.compose").name == "3.compose"
    assert co.content_object_stage_dir(_TASK, _BATCH, ref, "4.draft").parent == obj


def test_register_idempotent_keeps_seq():
    brief = {"titleHint": "稻城亚丁·攻略", "templateId": "环线"}
    ref = "地点_景区__稻城亚丁"
    c1 = co.register_from_brief(_TASK, _BATCH, ref, brief)
    c2 = co.register_from_brief(_TASK, _BATCH, ref, brief)
    assert c1 == c2 and c1["seq"] == 1


def test_same_title_collision_gets_stable_seq():
    # 罕见：同 (type,angle,title) 多 ref → 按 ref 排序稳定递增。
    brief = {"titleHint": "同名·攻略", "templateId": "环线"}
    a = co.register_from_brief(_TASK, _BATCH, "ref_b", brief)
    b = co.register_from_brief(_TASK, _BATCH, "ref_a", brief)
    seqs = {"ref_a": co.content_coords(_TASK, _BATCH, "ref_a")["seq"],
            "ref_b": co.content_coords(_TASK, _BATCH, "ref_b")["seq"]}
    assert sorted(seqs.values()) == [1, 2], seqs
    assert seqs["ref_a"] == 1 and seqs["ref_b"] == 2  # 按 ref 排序


def test_unregistered_ref_raises():
    try:
        co.content_object_dir(_TASK, _BATCH, "ref_never")
    except KeyError:
        return
    raise AssertionError("expected KeyError for unregistered ref")


def test_register_content_object_rejects_empty_title():
    try:
        co.register_content_object(_TASK, _BATCH, "bad_ref", content_type="article", angle="攻略", title=" ")
    except ValueError as exc:
        assert "title missing or empty" in str(exc)
        return
    raise AssertionError("expected ValueError for empty title")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content object router tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
