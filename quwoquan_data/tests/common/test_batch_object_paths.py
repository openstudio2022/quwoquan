"""批次对象同构目录与编号阶段、相对路径 helper 契约 (T1)。

冻结 docs/pipeline_directory_layout_spec.md 的目录真相源：
- 实体/内容对象目录与 publish DataRoot 同构。
- 过程阶段统一编号（1.download/2.quality/3.compose/4.draft/5.review）；成品落对象根。
- 来源是来源单元（编号 + source_id），图片不散落对象级 images/。
- citedSourceRefs/sourceAssetRef 用相对 batch 根的 POSIX 路径，禁绝对路径。

可直接运行：python3 quwoquan_data/tests/common/test_batch_object_paths.py
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

sys.path.insert(0, str(SCRIPTS_ROOT))

os.environ.setdefault("QWQ_RUNTIME_ROOT", tempfile.mkdtemp())

from _common.entity_object import collect_task_entity_objects, batch_entity_type_conflicts  # noqa: E402
from _common.io import write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    OBJECT_STAGES,
    STAGE_DOWNLOAD,
    STAGE_COMPOSE,
    STAGE_REVIEW,
    batch_entity_object_dir,
    batch_entity_stage_dir,
    batch_entity_page_input_path,
    batch_manifest_path,
    batch_post_object_dir,
    batch_post_stage_dir,
    batch_root,
    batch_source_unit_dir,
    batch_shared_dir,
    batch_workflow_packet_path,
    batches_root,
    iter_task_batch_dirs,
    publish_data,
    relative_batch_ref,
    task_discriminator,
    task_intent_label,
)

TASK = "旅行/地域/四川省/景区/景区全覆盖"
BATCH = "pilot_layout"


def test_entity_object_dir_is_isomorphic_with_publish():
    obj = batch_entity_object_dir(TASK, BATCH, "地点", "景区", "海螺沟")
    pub = publish_data().entity_dir("地点", "景区", "海螺沟")
    assert obj.relative_to(batch_root(TASK, BATCH)).as_posix() == "entities/地点/景区/海螺沟"
    assert pub.relative_to(pub.parents[3]).as_posix() == "entities/地点/景区/海螺沟"


def test_post_object_dir_is_isomorphic_with_publish():
    obj = batch_post_object_dir(TASK, BATCH, "article", "环线攻略", "海螺沟两天", 2)
    rel = obj.relative_to(batch_root(TASK, BATCH)).as_posix()
    assert rel == "posts/article/环线攻略/海螺沟两天/2", rel


def test_stage_dirs_are_numbered_and_ordered():
    assert OBJECT_STAGES == (
        "1.download",
        "2.quality",
        "3.compose",
        "4.draft",
        "5.review",
    )
    ent_dl = batch_entity_stage_dir(TASK, BATCH, "地点", "景区", "海螺沟", STAGE_DOWNLOAD)
    assert ent_dl.name == "1.download"
    ent_compose = batch_entity_stage_dir(TASK, BATCH, "地点", "景区", "海螺沟", STAGE_COMPOSE)
    assert ent_compose.name == "3.compose"
    post_review = batch_post_stage_dir(TASK, BATCH, "article", "环线攻略", "海螺沟两天", 1, STAGE_REVIEW)
    assert post_review.name == "5.review"


def test_object_input_and_workflow_packet_paths_are_object_first():
    inp = batch_entity_page_input_path(TASK, BATCH, "地点", "景区", "海螺沟")
    assert inp.relative_to(batch_root(TASK, BATCH)).as_posix() == "entities/地点/景区/海螺沟/3.compose/entity_page_input.json", inp
    packet = batch_workflow_packet_path(TASK, BATCH, "build_homepage")
    assert packet.relative_to(batch_root(TASK, BATCH)).as_posix() == "_shared/workflow_packets/build_homepage.json", packet


def test_source_unit_is_numbered_and_holds_assets_not_loose_images():
    unit = batch_source_unit_dir(TASK, BATCH, "su_fixture")
    rel = unit.relative_to(batch_root(TASK, BATCH)).as_posix()
    assert rel == "sources/su_fixture", rel
    # 来源单元自带 assets/，对象级别只保存 source_refs.json。
    assert (unit / "assets").parent == unit


def test_batch_common_info_is_hoisted_to_batch_root():
    assert batch_manifest_path(TASK, BATCH).parent == batch_root(TASK, BATCH)
    assert batch_shared_dir(TASK, BATCH).parent == batch_root(TASK, BATCH)


def test_relative_batch_ref_is_posix_relative_no_absolute():
    src = batch_source_unit_dir(TASK, BATCH, "su_fixture") / "source.md"
    ref = relative_batch_ref(src, TASK, BATCH)
    assert ref == "sources/su_fixture/source.md", ref
    assert not ref.startswith("/"), ref
    assert "/Users/" not in ref, ref
    assert os.sep != "\\" or "\\" not in ref


def test_collect_task_entity_objects_can_filter_approved_only():
    approved = batch_entity_object_dir(TASK, "approved_batch", "地点", "景区", "都江堰")
    approved.mkdir(parents=True, exist_ok=True)
    (approved / "page.md").write_text("# 都江堰\n", encoding="utf-8")
    write_json(approved / "_entity.json", {"label": "都江堰", "domain": "地点", "type": "景区"})
    (approved / "5.review").mkdir(parents=True, exist_ok=True)
    write_json(approved / "5.review" / "review.json", {"decision": "approved"})

    rejected = batch_entity_object_dir(TASK, "rejected_batch", "地点", "景区", "青城山")
    rejected.mkdir(parents=True, exist_ok=True)
    (rejected / "page.md").write_text("# 青城山\n", encoding="utf-8")
    write_json(rejected / "_entity.json", {"label": "青城山", "domain": "地点", "type": "景区"})
    (rejected / "5.review").mkdir(parents=True, exist_ok=True)
    write_json(rejected / "5.review" / "review.json", {"decision": "rejected"})

    rows = collect_task_entity_objects(TASK, approved_only=True)
    refs = {row["entityRel"] for row in rows}
    assert "entities/地点/景区/都江堰" in refs
    assert "entities/地点/景区/青城山" not in refs


def test_collect_task_entity_objects_blocks_dual_scenic_location_trees():
    scenic = batch_entity_object_dir(TASK, "dual_tree_batch", "地点", "景区", "都江堰")
    scenic.mkdir(parents=True, exist_ok=True)
    (scenic / "page.md").write_text("# 都江堰景区\n", encoding="utf-8")
    write_json(scenic / "_entity.json", {"label": "都江堰", "domain": "地点", "type": "景区"})

    spot = batch_entity_object_dir(TASK, "dual_tree_batch", "地点", "打卡地", "都江堰")
    spot.mkdir(parents=True, exist_ok=True)
    (spot / "page.md").write_text("# 都江堰打卡地\n", encoding="utf-8")
    write_json(spot / "_entity.json", {"label": "都江堰", "domain": "地点", "type": "打卡地"})

    conflicts = batch_entity_type_conflicts(TASK, "dual_tree_batch")
    assert conflicts and conflicts[0]["name"] == "都江堰", conflicts
    try:
        collect_task_entity_objects(TASK, batch_id="dual_tree_batch", enforce_type_consistency=True)
    except ValueError as exc:
        assert "dual trees coexist" in str(exc)
    else:
        raise AssertionError("expected dual scenic-location tree conflict")


def test_top_level_batch_dir_disambiguates_same_name_tasks_sharing_batch():
    """fanout 同名分区任务共享 batchId 时，顶层批次目录必须靠 taskHash 消歧、不得塌缩。

    回归 `runtime/batches/<intentLabel>__<batch>` 单凭人读标签时，
    `四川省/.../全国景点主页` 与 `云南省/.../全国景点主页` 共享 `fanout_demo`
    会塌缩到同一目录、内容对象互相串扰。
    """
    t1 = "旅行/地域/四川省/景区/全国景点主页"
    t2 = "旅行/地域/云南省/景区/全国景点主页"
    b = "fanout_demo"
    d1 = batch_root(t1, b)
    d2 = batch_root(t2, b)
    assert d1 != d2, (d1, d2)
    assert d1.parent == d2.parent == batches_root()
    # 人读前缀（intentLabel）相同（同名任务）；taskHash 不同 → 目录唯一。
    assert task_intent_label(t1) == task_intent_label(t2), (t1, t2)
    assert task_discriminator(t1) != task_discriminator(t2), (t1, t2)
    # 首个 __ 之后必须还原出共享 batchId。
    assert d1.name.split("__", 1)[1] == b == d2.name.split("__", 1)[1], (d1.name, d2.name)


def test_iter_task_batch_dirs_filters_same_name_tasks_by_manifest_taskid():
    """同名任务的批次互不串扰：iter_task_batch_dirs 仅返回本任务批次（前缀任务唯一 + manifest.taskId）。"""
    from _common.io import write_json as _write_json

    t1 = "旅行/地域/四川省/景区/同名覆盖"
    t2 = "旅行/地域/贵州省/景区/同名覆盖"
    b = "fanout_same"
    for tid in (t1, t2):
        d = batch_root(tid, b)
        d.mkdir(parents=True, exist_ok=True)
        _write_json(d / "batch_manifest.json", {"taskId": tid, "batchId": b})
    dirs1 = iter_task_batch_dirs(t1)
    dirs2 = iter_task_batch_dirs(t2)
    assert [d.name for d in dirs1] == [batch_root(t1, b).name], dirs1
    assert [d.name for d in dirs2] == [batch_root(t2, b).name], dirs2
    assert set(dirs1).isdisjoint(set(dirs2))


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"batch object path tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
