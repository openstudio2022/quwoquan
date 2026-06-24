"""任务工程 CLI/store/lint/ops 契约。

隔离：committed/runtime/publish 指向临时目录（SOP 仍用真实 DATA_ROOT 提供实体类型真相源）。
可直接运行：python3 quwoquan_data/tests/task/test_task_cli.py
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

import datetime as _dt
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="task_cli_"))
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import read_json, write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    COMMITTED_TASKS_ROOT,
    PUBLISH_ROOT,
    batch_root,
    committed_task_notes,
    committed_task_root,
    task_id_from_committed_path,
    task_lock_path,
)
from task import lint as lint_mod  # noqa: E402
from task import ops, store  # noqa: E402


def _mk(vertical="travel", organize_by="地域", key="四川省", name="景区全覆盖",
        category="景区", archetype=None, scope=None, content=None):
    spec = store.scaffold_spec(
        vertical=vertical, organize_by=organize_by, key=key, name=name, category=category,
        archetype=archetype,
        scope=scope or {"region": key, "entityTypes": ["地点/景区"],
                        "coverageTargets": [{"entityType": "地点/景区", "name": "九寨沟"},
                                            {"entityType": "地点/景区", "name": "黄龙"}]},
        content=content or {"angles": ["体验", "攻略"], "audiences": [], "carriers": ["article"]},
    )
    store.save_spec(spec)
    remaining = [f"{t['entityType']}/{t['name']}" for t in spec["scope"].get("coverageTargets", [])]
    store.save_progress(store.init_progress(spec["taskId"], remaining=remaining))
    return spec


def test_build_task_id_uses_chinese_label():
    tid = store.build_task_id("travel", "地域", "四川省", "景区", "景区全覆盖")
    assert tid == "旅行/地域/四川省/景区/景区全覆盖", tid
    assert store.build_task_id("campus", "地域", "全国", "高校", "x").startswith("校园/")


def test_id_path_roundtrip():
    spec = _mk(name="景区往返")
    derived = task_id_from_committed_path(committed_task_root(spec["taskId"]))
    assert derived == spec["taskId"], derived


def test_scaffold_and_lint_ok():
    _mk(name="景区合法")
    total, results, _ = lint_mod.lint_all("旅行/地域/四川省/景区/景区合法")
    assert total == 0, results


def test_lint_detects_missing_scope():
    spec = store.scaffold_spec(vertical="travel", organize_by="地域", key="云南省",
                               name="省域总览", archetype="province_overview", scope={})
    store.save_spec(spec)
    total, results, _ = lint_mod.lint_all(spec["taskId"])
    assert total > 0
    assert any("scope.region" in e for e in results.get(spec["taskId"], []))


def test_lint_detects_unknown_entity_type():
    spec = store.scaffold_spec(vertical="travel", organize_by="地域", key="海南省", name="不存在类型",
                               category="飞碟", scope={"region": "海南省", "entityTypes": ["地点/飞碟基地"]})
    store.save_spec(spec)
    total, results, _ = lint_mod.lint_all(spec["taskId"])
    assert any("飞碟基地" in e for e in results.get(spec["taskId"], [])), results


def test_lint_blocks_intent_label_too_long_or_dirty():
    """intentLabel 超 16 字或含路径分隔符 → BLOCK（顶层批次目录前缀人读标签须干净）。"""
    spec = _mk(name="标签校验")
    spec["intentLabel"] = "四川/景区超长意图标签abcdefghij"  # 含 / 且 >16 字
    store.save_spec(spec)
    _, results, _ = lint_mod.lint_all(spec["taskId"])
    errs = results.get(spec["taskId"], [])
    assert any("intentLabel" in e and "分隔符" in e for e in errs), errs
    assert any("intentLabel" in e and "16" in e for e in errs), errs


def test_lint_accepts_clean_intent_label():
    spec = _mk(name="标签干净")
    spec["intentLabel"] = "四川景区精选"
    store.save_spec(spec)
    total, results, _ = lint_mod.lint_all(spec["taskId"])
    assert total == 0, results.get(spec["taskId"])


def test_lint_blocks_dual_scenic_location_types_for_same_name():
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="四川省",
        name="类型漂移",
        category="景区",
        scope={
            "region": "四川省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": "都江堰"},
                {"entityType": "地点/打卡地", "name": "都江堰"},
            ],
        },
    )
    store.save_spec(spec)
    total, results, _ = lint_mod.lint_all(spec["taskId"])
    assert total > 0
    assert any("双树共存" in e or "同时声明为" in e for e in results.get(spec["taskId"], [])), results


def test_resume_reports_gaps():
    spec = _mk(name="景区缺口")
    gaps = ops.compute_gaps(spec["taskId"])
    assert set(gaps["remainingEntities"]) == {"地点/景区/九寨沟", "地点/景区/黄龙"}


def test_record_run_updates_progress():
    spec = _mk(name="景区记账")
    ops.record_run(spec["taskId"], owner="t", summary="跑九寨沟", entities_added=1, posts_added=4,
                   mark_done=["地点/景区/九寨沟"], next_suggested=["补黄龙"])
    prog = store.load_progress(spec["taskId"])
    ent = prog["coverage"]["entities"]
    assert "地点/景区/九寨沟" in ent["done"]
    assert "地点/景区/九寨沟" not in ent["remaining"]
    assert prog["counts"]["posts"] == 4
    assert prog["lastRunId"] is not None
    runs = list((committed_task_root(spec["taskId"]) / "runs").glob("*.json"))
    assert len(runs) == 1


def test_reflection_recorded_resumed_and_noted():
    """反思账本：record-run 写 run.reflections + notes 沉淀 + openGaps；recent_reflections 加载。"""
    spec = _mk(name="景区反思")
    tid = spec["taskId"]
    ops.record_run(
        tid, owner="t", summary="稻城亚丁源不足",
        reflections=[{"query": "稻城亚丁 牛奶海 海拔", "attribution": "证据不足", "decision": "换检索词补权威源"}],
        open_gaps=["地点/景区/牛奶海 待补主页"],
    )
    run = read_json(sorted((committed_task_root(tid) / "runs").glob("run_*.json"))[-1])
    assert len(run["reflections"]) == 1 and run["reflections"][0]["attribution"] == "证据不足"
    prog = store.load_progress(tid)
    assert "地点/景区/牛奶海 待补主页" in prog["openGaps"]
    notes = committed_task_notes(tid).read_text(encoding="utf-8")
    assert "反思账本" in notes and "证据不足" in notes
    recent = ops.recent_reflections(tid)
    assert recent and recent[0]["decision"] == "换检索词补权威源"


def test_lock_mutex_and_release():
    spec = _mk(name="景区锁")
    ok, _ = store.acquire_lock(spec["taskId"], "A")
    assert ok
    ok2, msg = store.acquire_lock(spec["taskId"], "B")
    assert not ok2 and "locked by A" in msg
    assert store.release_lock(spec["taskId"])
    ok3, _ = store.acquire_lock(spec["taskId"], "C")
    assert ok3
    store.release_lock(spec["taskId"])


def test_stale_lock_is_reclaimable():
    spec = _mk(name="景区陈旧锁")
    old = (_dt.datetime.now().astimezone() - _dt.timedelta(hours=12)).isoformat(timespec="seconds")
    write_json(task_lock_path(spec["taskId"]), {"taskId": spec["taskId"], "owner": "ghost", "pid": 1, "ts": old})
    ok, _ = store.acquire_lock(spec["taskId"], "fresh")  # 陈旧锁可被夺取
    assert ok
    store.release_lock(spec["taskId"])


def test_trace_by_source_task_id(capsys=None):
    spec = _mk(name="景区溯源")
    tid = spec["taskId"]
    mf = PUBLISH_ROOT / "posts" / "article" / "体验" / "九寨沟纪行" / "1" / "manifest.json"
    write_json(mf, {"topicId": "九寨沟纪行", "contentType": "article", "sourceTaskId": tid,
                    "entityRefs": ["/entity/地点/景区/九寨沟"], "tagRefs": []})
    other = PUBLISH_ROOT / "posts" / "article" / "体验" / "别的" / "1" / "manifest.json"
    write_json(other, {"topicId": "别的", "contentType": "article", "sourceTaskId": "旅行/地域/其它/x",
                       "entityRefs": [], "tagRefs": []})
    hits = [p for p, d in ops._iter_publish_manifests() if d.get("sourceTaskId") == tid]
    assert len(hits) == 1, hits


def test_latest_post_outputs_points_to_runtime_article():
    spec = _mk(name="景区产物发现")
    tid = spec["taskId"]
    # 顶层批次布局：成品落 runtime/batches/<intentLabel>__b1/posts/...，articlePath 相对批次根。
    post_dir = batch_root(tid, "b1") / "posts" / "article" / "九寨沟纪行" / "1"
    write_json(post_dir / "manifest.json", {
        "contentType": "article",
        "publishTitle": "九寨沟纪行",
        "sourceBatchId": "b1",
    })
    (post_dir / "article.md").write_text("# 九寨沟纪行\n", encoding="utf-8")
    outputs = ops.latest_post_outputs(tid)
    assert outputs and outputs[0]["title"] == "九寨沟纪行"
    assert outputs[0]["articlePath"] == "posts/article/九寨沟纪行/1/article.md", outputs[0]
    assert outputs[0]["sourceBatchId"] == "b1", outputs[0]


def _write_defaults(rel_dir: str, content: dict) -> None:
    """在 committed tasks 路径前缀写 _defaults.yaml（rel_dir 如 '旅行' 或 '旅行/地域/四川省'）。"""
    path = COMMITTED_TASKS_ROOT
    for seg in rel_dir.split("/"):
        path = path / seg
    store.write_yaml(path / store.DEFAULTS_FILENAME,
                     {"schemaVersion": store.DEFAULTS_VERSION, "content": content})


# 与真实任务一致的垂类菜单（供继承解析用例）
_TRAVEL_DEFAULTS = {"angles": ["体验", "美图", "攻略"], "audiences": ["通用"], "carriers": ["article"]}


def test_inheritance_resolve_fills_effective():
    """瘦身 task（不写 angles）经继承解析后 effective 含垂类 angles，task 特化保留。"""
    _write_defaults("旅行", _TRAVEL_DEFAULTS)
    spec = store.scaffold_spec(
        vertical="travel", organize_by="地域", key="四川省", category="景区", name="景区继承",
        scope={"region": "四川省", "entityTypes": ["地点/景区"],
               "coverageTargets": [{"entityType": "地点/景区", "name": "稻城亚丁"}]},
        content={"emphasis": ["自然风光"]},
    )
    store.save_spec(spec)
    # 原始 spec 不内联 angles（靠继承）
    raw_content = spec.get("content") or {}
    assert "angles" not in raw_content
    eff = store.load_spec(spec["taskId"])["content"]
    assert eff["angles"] == ["体验", "美图", "攻略"]
    assert eff["emphasis"] == ["自然风光"]  # task 特化保留
    total, results, _ = lint_mod.lint_all(spec["taskId"])
    assert total == 0, results.get(spec["taskId"])


def test_lint_blocks_history_source_tasks():
    spec = _mk(name="景区遗留history")
    spec.setdefault("provenance", {})["historySourceTasks"] = ["四川旅行_v5"]
    store.save_spec(spec)
    _, results, _ = lint_mod.lint_all(spec["taskId"])
    assert any("historySourceTasks" in e for e in results.get(spec["taskId"], [])), results


def test_lint_warns_redundant_content():
    """task content.angles 与继承默认完全相同 → PR_WARN 建议删除（不阻断）。"""
    _write_defaults("旅行", _TRAVEL_DEFAULTS)
    spec = store.scaffold_spec(
        vertical="travel", organize_by="地域", key="重庆市", category="古镇", name="古镇冗余",
        scope={"region": "重庆市", "entityTypes": ["地点/景区"],
               "coverageTargets": [{"entityType": "地点/景区", "name": "磁器口"}]},
        content={"angles": ["体验", "美图", "攻略"]},  # 与垂类默认完全相同 → 冗余
    )
    store.save_spec(spec)
    total, _, warnings = lint_mod.lint_all(spec["taskId"])
    assert total == 0
    assert any("content.angles" in w for w in warnings.get(spec["taskId"], [])), warnings


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"task cli tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
