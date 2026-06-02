"""任务工程 CLI/store/lint/ops 契约。

隔离：committed/runtime/publish 指向临时目录（SOP 仍用真实 DATA_ROOT 提供实体类型真相源）。
可直接运行：python3 quwoquan_data/tests/test_task_cli.py
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="task_cli_"))
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _common.io import read_json, write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    COMMITTED_TASKS_ROOT,
    PUBLISH_ROOT,
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
        content=content or {"angles": ["体验", "攻略"], "audiences": [], "carriers": ["article"],
                            "conditionAxes": {"regions": ["高原"], "seasons": ["夏"]}},
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


def test_resume_reports_gaps():
    spec = _mk(name="景区缺口")
    gaps = ops.compute_gaps(spec["taskId"])
    assert set(gaps["remainingEntities"]) == {"地点/景区/九寨沟", "地点/景区/黄龙"}
    assert len(gaps["missingConditionCells"]) == 1  # 高原×夏


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


def _write_defaults(rel_dir: str, content: dict) -> None:
    """在 committed tasks 路径前缀写 _defaults.yaml（rel_dir 如 '旅行' 或 '旅行/地域/四川省'）。"""
    path = COMMITTED_TASKS_ROOT
    for seg in rel_dir.split("/"):
        path = path / seg
    store.write_yaml(path / store.DEFAULTS_FILENAME,
                     {"schemaVersion": store.DEFAULTS_VERSION, "content": content})


# 与 13 个真实任务一致的垂类/地域菜单（供继承解析用例）
_TRAVEL_DEFAULTS = {"angles": ["体验", "美图", "攻略"], "audiences": ["通用"], "carriers": ["article"],
                    "conditionAxes": {"seasons": ["春", "夏", "秋", "冬"]}}
_SICHUAN_REGIONS = ["高原", "雪山", "山地森林", "平原都市", "乡村田园"]


def test_inheritance_resolve_fills_effective():
    """瘦身 task（不写 angles/conditionAxes）经继承解析后 effective 含垂类 angles + 地域全谱。"""
    _write_defaults("旅行", _TRAVEL_DEFAULTS)
    _write_defaults("旅行/地域/四川省", {"conditionAxes": {"regions": _SICHUAN_REGIONS}})
    spec = store.scaffold_spec(
        vertical="travel", organize_by="地域", key="四川省", category="景区", name="景区继承",
        scope={"region": "四川省", "entityTypes": ["地点/景区"],
               "coverageTargets": [{"entityType": "地点/景区", "name": "稻城亚丁"}]},
        content={"emphasis": ["自然风光"]},
    )
    store.save_spec(spec)
    # 原始 spec 不内联 angles/conditionAxes（靠继承）
    raw_content = spec.get("content") or {}
    assert "angles" not in raw_content and "conditionAxes" not in raw_content
    eff = store.load_spec(spec["taskId"])["content"]
    assert eff["angles"] == ["体验", "美图", "攻略"]
    assert eff["conditionAxes"]["seasons"] == ["春", "夏", "秋", "冬"]
    assert eff["conditionAxes"]["regions"] == _SICHUAN_REGIONS
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
    _write_defaults("旅行/地域/重庆市", {"conditionAxes": {"regions": ["山地森林", "平原都市"]}})
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


def test_lint_blocks_condition_axes_out_of_menu():
    """task 显式 conditionAxes.regions 越出继承地形全谱 → 报错。"""
    _write_defaults("旅行", _TRAVEL_DEFAULTS)
    _write_defaults("旅行/地域/江苏省", {"conditionAxes": {"regions": ["平原都市", "沿海海岛"]}})
    spec = store.scaffold_spec(
        vertical="travel", organize_by="地域", key="江苏省", category="园林", name="园林越界",
        scope={"region": "江苏省", "entityTypes": ["地点/景区"],
               "coverageTargets": [{"entityType": "地点/景区", "name": "拙政园"}]},
        content={"conditionAxes": {"regions": ["高原"], "seasons": ["春"]}},  # 高原不在菜单
    )
    store.save_spec(spec)
    _, results, _ = lint_mod.lint_all(spec["taskId"])
    assert any("高原" in e and "全谱" in e for e in results.get(spec["taskId"], [])), results


def _write_entity_profile(ref: str, profile: dict) -> None:
    domain, etype, name = ref.split("/", 2)
    write_json(PUBLISH_ROOT / "entities" / domain / etype / name / "_entity.json",
               {"label": name, "conditionProfile": profile})


def test_l3_entity_condition_profile_read():
    """实体 _entity.json 的 conditionProfile 被 L3 读取（regions/seasons/海拔），支持 /entity/ 前缀。"""
    from plan import brief as brief_mod
    ref = "地点/景区/稻城亚丁试点"
    _write_entity_profile(ref, {"regions": ["高原", "雪山"], "seasons": ["秋", "夏"], "altitudeMeters": 4700})
    prof = brief_mod._entity_condition_profile("/entity/" + ref)
    assert prof and prof["regions"][0] == "高原" and prof["altitudeMeters"] == 4700


def test_l3_inject_uses_entity_profile_when_request_blank():
    """request 未给 region/season 时，由实体 conditionProfile 主值精确注入，source=entityProfile。"""
    import types

    from plan import brief as brief_mod
    ref = "地点/景区/L3注入景区"
    _write_entity_profile(ref, {"regions": ["高原"], "seasons": ["秋"], "altitudeMeters": 4000})
    registry = types.SimpleNamespace(catalogs={
        "region_catalog": {"regions": {"高原": {
            "label": "高原/高海拔", "conditionFacts": ["海拔与高反风险"], "imageHints": ["雪山垭口"],
            "tagRefs": ["Topic/自然风光/高原风光"], "packing": ["红景天"], "riskNotes": ["高原反应"]}}},
        "season_catalog": {"seasons": {"秋": {
            "label": "秋季", "conditionFacts": ["红叶窗口"], "imageHints": ["彩林红叶"],
            "tagRefs": ["Topic/时间/四季/秋季"], "packing": [], "crowdNotes": ["红叶季拥挤"]}}},
    })
    blueprint = {"conditionAxes": {"region": {"applicable": True, "slot": "地形适应"},
                                   "season": {"applicable": True, "slot": "季节体验"}}}
    request = types.SimpleNamespace(subject_kind="entity", subject_type="景区",
                                    region=None, season=None, audience="通用", intent="体验")
    res = brief_mod._resolve_condition(registry, blueprint, request, entity_refs=[ref])
    ctx = res["context"]
    assert ctx["region"]["name"] == "高原" and ctx["region"]["source"] == "entityProfile"
    assert ctx["season"]["name"] == "秋" and ctx["season"]["source"] == "entityProfile"
    assert ctx["entityProfile"]["altitudeMeters"] == 4000
    assert "海拔与高反风险" in res["facts"] and "红叶窗口" in res["facts"]


def test_l3_fallback_when_no_profile():
    """实体无 conditionProfile 且 request 未给条件 → 不注入 region，记 entityProfileFallback。"""
    import types

    from plan import brief as brief_mod
    registry = types.SimpleNamespace(catalogs={"region_catalog": {"regions": {}}, "season_catalog": {"seasons": {}}})
    blueprint = {"conditionAxes": {"region": {"applicable": True}, "season": {"applicable": True}}}
    request = types.SimpleNamespace(subject_kind="entity", subject_type="景区",
                                    region=None, season=None, audience="通用", intent="体验")
    res = brief_mod._resolve_condition(registry, blueprint, request, entity_refs=["地点/景区/无画像景区"])
    assert "region" not in res["context"]
    assert "entityProfileFallback" in res["context"]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"task cli tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
