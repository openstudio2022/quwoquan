"""data 命令族回归：命令树 / explore / baseline / workflow 约束。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="data_cli_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
os.environ["QWQ_RELEASE_ROOT"] = str(_TMP / "release")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.command_packet import build_packet, write_packet  # noqa: E402
from _common.io import read_json, read_ndjson, write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    committed_task_spec,
    committed_task_progress,
    fanout_plan_path,
    task_baseline_freeze_packet_path,
    task_catalog,
    task_explore_packet_path,
    task_shared_dir,
)
from data.baseline import handle_baseline  # noqa: E402
from explore.handler import handle_explore  # noqa: E402
from _common import fanout_plan as fp  # noqa: E402
from task import run as run_mod  # noqa: E402
from task import handler as task_handler_mod  # noqa: E402
from task import store  # noqa: E402

CLI = SCRIPTS_ROOT / "cli.py"


def _make_task(task_id: str = "旅行/地域/四川省/景区/景区精选", *, with_baseline: bool = True) -> str:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="四川省",
        name="景区精选",
        category="景区",
        scope={
            "region": "四川省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": "峨眉山"},
                {"entityType": "地点/景区", "name": "乐山大佛"},
            ],
        },
        created_by="test",
    )
    spec["taskId"] = task_id
    spec["title"] = "四川景区精选"
    store.save_spec(spec)
    store.save_progress(store.init_progress(task_id, remaining=["地点/景区/峨眉山", "地点/景区/乐山大佛"]))
    if with_baseline:
        _seed_baseline(task_id)
    else:
        baseline_packet = task_baseline_freeze_packet_path(task_id)
        if baseline_packet.exists():
            baseline_packet.unlink()
    return task_id


def _seed_baseline(task_id: str) -> None:
    packet = build_packet(
        task_id=task_id,
        command="data baseline",
        object_kind="task",
        object_ref=task_id,
        stage="baseline",
        read_policy=["task.yaml", "progress.json", "catalog.ndjson"],
        stop_if=["taskId mismatch"],
        output_policy=["write task/_shared/baseline_freeze_packet.json"],
        inputs={
            "taskSpecPath": str(committed_task_spec(task_id)),
            "progressPath": str(committed_task_progress(task_id)),
            "catalogPath": str(task_catalog(task_id)),
        },
        outputs={"packetPath": str(task_baseline_freeze_packet_path(task_id))},
        handoff_to="data workflow run",
        evidence={"required": ["baseline_freeze_packet.json"]},
        summary={"coverageTargetCount": 2, "catalogRowCount": 2},
    )
    write_packet(task_baseline_freeze_packet_path(task_id), packet)


def _seed_frozen_plan(plan_id: str = "plan_cli") -> dict:
    plan = fp.new_plan(plan_id, "测试 fanout", "travel", defaults={"entityType": "地点/景区", "taskName": f"{plan_id}_task"})
    fp.add_partition(plan, "四川省")
    fp.add_leaves(plan, ["四川省"], [{"name": "峨眉山"}])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    return plan


def test_cli_has_data_root_and_no_flat_explore():
    ok = subprocess.run(
        [sys.executable, str(CLI), "data", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0, ok.stderr
    assert "baseline" in ok.stdout and "workflow" in ok.stdout

    bad = subprocess.run(
        [sys.executable, str(CLI), "explore", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode != 0
    assert "invalid choice" in bad.stderr or "invalid choice" in bad.stdout

    task_help = subprocess.run(
        [sys.executable, str(CLI), "task", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert task_help.returncode == 0, task_help.stderr
    assert "scaled-e2e" in task_help.stdout


def test_explore_writes_catalog_and_packet():
    task_id = _make_task(with_baseline=False)
    handle_explore(
        argparse.Namespace(
            task=task_id,
            regions="四川省",
            entity_types="地点/景区",
        )
    )
    rows = read_ndjson(task_catalog(task_id))
    assert [row["topic_id"] for row in rows] == ["地点/景区/峨眉山", "地点/景区/乐山大佛"]
    packet = read_json(task_explore_packet_path(task_id))
    assert packet["command"] == "data explore"
    assert packet["summary"]["catalogRowCount"] == 2
    assert packet["handoffTo"] == "data baseline"


def test_baseline_freezes_bundle_and_enforces_catalog_config_pair():
    task_id = _make_task(with_baseline=False)
    handle_explore(
        argparse.Namespace(
            task=task_id,
            regions="四川省",
            entity_types="地点/景区",
        )
    )
    config_dir = _TMP / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    catalog_config = config_dir / "geo_catalog_config.yaml"
    geo_band_rules = config_dir / "geo_band_rules.sichuan.yaml"
    catalog_config.write_text("geo_band_rules_path: geo_band_rules.sichuan.yaml\n", encoding="utf-8")
    geo_band_rules.write_text("schemaVersion: demo\n", encoding="utf-8")

    handle_baseline(
        argparse.Namespace(
            task=task_id,
            catalog=None,
            spec_doc=None,
            design_doc=None,
            acceptance_doc=None,
            workflow_doc=None,
            command_matrix_doc=None,
            catalog_config=str(catalog_config),
            naming_rules=None,
            geo_band_rules=str(geo_band_rules),
            schema_files=[],
            config_files=[],
            output=None,
        )
    )
    packet = read_json(task_baseline_freeze_packet_path(task_id))
    report = read_json(task_shared_dir(task_id) / "baseline_report.json")
    assert packet["command"] == "data baseline"
    assert packet["summary"]["coverageTargetCount"] == 2
    assert report["status"] == "passed"
    assert report["issues"] == []


def test_workflow_run_requires_baseline_packet():
    task_id = _make_task(with_baseline=False)
    try:
        run_mod.handle_run(
            argparse.Namespace(
                task=task_id,
                batch="b1",
                resume=False,
                reset_state=False,
                until=None,
                baseline_packet=None,
            )
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("workflow run should require baseline packet")


def test_workflow_run_records_baseline_packet_when_present():
    task_id = _make_task()
    code = None
    try:
        run_mod.handle_run(
            argparse.Namespace(
                task=task_id,
                batch="b1",
                resume=False,
                reset_state=False,
                until=None,
                baseline_packet=None,
            )
        )
    except SystemExit as exc:
        code = exc.code
    assert code == 10, code
    state = run_mod.load_workflow_state(task_id, "b1")
    assert state["baselinePacketPath"].endswith("baseline_freeze_packet.json")
    assert state["waitingCheckpoint"] == "download_plan"


def test_task_new_persists_explicit_content_quotas():
    task_handler_mod.handle_new(
        argparse.Namespace(
            vertical="travel",
            organize_by="地域",
            key="四川省",
            name="三景点真实实跑",
            category="景区",
            archetype=None,
            title="四川三景点真实实跑",
            parent=None,
            region="四川省",
            regions=None,
            entity_types="地点/景区",
            route=None,
            anchor_entities=None,
            theme=None,
            coverage="地点/景区/都江堰,地点/景区/乐山大佛,地点/景区/峨眉山",
            angles="攻略",
            audiences=None,
            carriers="article,gallery",
            entity_articles=3,
            route_articles=0,
            gallery_posts=3,
            emphasis=None,
            cond_regions=None,
            cond_seasons=None,
            owner="test",
            force=False,
        )
    )
    spec = store.load_raw_spec("旅行/地域/四川省/景区/三景点真实实跑")
    quotas = ((spec.get("content") or {}).get("quotas") or {})
    assert quotas == {"entityArticles": 3, "routeArticles": 0, "galleryPosts": 3}, quotas


def test_task_scaled_e2e_prepare_enters_standard_checkpointed_workflow():
    task_id = _make_task(with_baseline=False)
    try:
        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="prepare",
                task=task_id,
                batch="se1",
                plan="dummy_plan",
                catalog=None,
                reset_state=False,
            )
        )
    except SystemExit as exc:
        assert exc.code == 10
    else:
        raise AssertionError("scaled-e2e prepare should stop at standard workflow checkpoint")
    state = run_mod.load_workflow_state(task_id, "se1")
    assert state["baselinePacketPath"].endswith("baseline_freeze_packet.json"), state
    assert state["waitingCheckpoint"] == "download_plan", state
    packet = read_json(task_explore_packet_path(task_id))
    assert packet["command"] == "data explore"


def test_task_scaled_e2e_fanout_author_delegates_to_run_fanout():
    called: dict = {}
    original = run_mod.handle_run
    try:
        def _fake_handle_run(args):
            called["mode"] = args.mode
            called["plan"] = args.plan
            called["strategy"] = args.strategy
            called["concurrency"] = args.concurrency
            called["batch_size"] = args.batch_size

        run_mod.handle_run = _fake_handle_run
        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="fanout-author",
                plan="plan_x",
                batch="b2",
                strategy="flat-pool",
                concurrency=3,
                batch_size=5,
            )
        )
    finally:
        run_mod.handle_run = original
    assert called == {
        "mode": "fanout",
        "plan": "plan_x",
        "strategy": "flat-pool",
        "concurrency": 3,
        "batch_size": 5,
    }, called


def test_task_scaled_e2e_verify_delegates_to_gate_verify():
    called: dict = {}
    original = task_handler_mod.gate_verify
    try:
        def _fake_gate_verify(*, task=None, batch=None, release=None, scope="current"):
            called["task"] = task
            called["batch"] = batch
            called["scope"] = scope
            return (["/tmp/root"], [])

        task_handler_mod.gate_verify = _fake_gate_verify
        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="verify",
                task="task_x",
                batch="batch_x",
            )
        )
    finally:
        task_handler_mod.gate_verify = original
    assert called == {"task": "task_x", "batch": "batch_x", "scope": "current"}, called


def test_task_scaled_e2e_verify_plan_aggregates_units():
    called: list[tuple[str, str]] = []
    original = task_handler_mod.gate_verify
    try:
        def _fake_gate_verify(*, task=None, batch=None, release=None, scope="current"):
            called.append((task, batch))
            return (["/tmp/root"], [])

        task_handler_mod.gate_verify = _fake_gate_verify
        _seed_frozen_plan("plan_verify")
        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="verify",
                task=None,
                batch=None,
                plan="plan_verify",
            )
        )
    finally:
        task_handler_mod.gate_verify = original
    assert called == [("旅行/地域/四川省/plan_verify_task", "fanout_plan_verify")], called


def test_task_scaled_e2e_finalize_resumes_all_units():
    called: list[tuple[str, str, bool]] = []
    original = run_mod.handle_run
    try:
        def _fake_handle_run(args):
            called.append((args.task, args.batch, args.resume))

        run_mod.handle_run = _fake_handle_run
        _seed_frozen_plan("plan_finalize")
        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="finalize",
                plan="plan_finalize",
            )
        )
    finally:
        run_mod.handle_run = original
    assert called == [("旅行/地域/四川省/plan_finalize_task", "fanout_plan_finalize", True)], called


def test_task_scaled_e2e_finalize_reruns_author_when_produce_author_pauses():
    import types

    calls: list[tuple[str, str, bool]] = []
    original_handle_run = run_mod.handle_run
    original_load_state = run_mod.load_workflow_state
    original_module = sys.modules.get("agent_ops.runners.fanout_runner")
    original_prepare = task_handler_mod._prepare_author_jobs_for_paused_targets
    try:
        attempts = {"count": 0}

        def _fake_handle_run(args):
            calls.append((args.task, args.batch, args.resume))
            if attempts["count"] == 0:
                attempts["count"] += 1
                raise SystemExit(10)

        def _fake_load_state(task_id, batch_id):
            return {"waitingCheckpoint": "produce_author"}

        captured: dict[str, list[str]] = {}

        def _fake_main(argv):
            captured["argv"] = list(argv)
            return 0

        prepared: list[tuple[str, str]] = []

        def _fake_prepare(plan, paused_targets):
            prepared.extend(list(paused_targets))

        run_mod.handle_run = _fake_handle_run
        run_mod.load_workflow_state = _fake_load_state
        sys.modules["agent_ops.runners.fanout_runner"] = types.SimpleNamespace(main=_fake_main)
        task_handler_mod._prepare_author_jobs_for_paused_targets = _fake_prepare
        _seed_frozen_plan("plan_finalize_author")
        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="finalize",
                plan="plan_finalize_author",
                strategy=None,
                concurrency=3,
                max_workers=2,
                runtime="local",
                model="composer-2.5",
                cwd="/repo",
                spend_limit=2.0,
                reset_state=True,
            )
        )
    finally:
        run_mod.handle_run = original_handle_run
        run_mod.load_workflow_state = original_load_state
        task_handler_mod._prepare_author_jobs_for_paused_targets = original_prepare
        if original_module is None:
            del sys.modules["agent_ops.runners.fanout_runner"]
        else:
            sys.modules["agent_ops.runners.fanout_runner"] = original_module
    assert calls == [
        ("旅行/地域/四川省/plan_finalize_author_task", "fanout_plan_finalize_author", True),
        ("旅行/地域/四川省/plan_finalize_author_task", "fanout_plan_finalize_author", True),
    ], calls
    assert captured["argv"] == [
        "--plan", "plan_finalize_author",
        "--concurrency", "3",
        "--max-workers", "2",
        "--runtime", "local",
        "--model", "composer-2.5",
        "--cwd", "/repo",
        "--spend-limit-usd", "2.0",
        "--no-orchestrate",
    ], captured
    assert prepared == [("旅行/地域/四川省/plan_finalize_author_task", "fanout_plan_finalize_author")]


def test_task_scaled_e2e_author_runner_delegates_to_fanout_runner():
    import types

    captured: dict = {}
    def _fake_main(argv):
        captured["argv"] = list(argv)
        return 0

    fake_module = types.SimpleNamespace(main=_fake_main)
    original = sys.modules.get("agent_ops.runners.fanout_runner")
    try:
        sys.modules["agent_ops.runners.fanout_runner"] = fake_module
        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="author-runner",
                plan="plan_run",
                strategy="flat-pool",
                concurrency=2,
                max_workers=4,
                runtime="local",
                model="composer-2.5",
                cwd="/repo",
                spend_limit=1.5,
                refs="route_都江堰",
                force_refs="route_都江堰",
                orchestrate=False,
                no_orchestrate=True,
            )
        )
    finally:
        if original is None:
            del sys.modules["agent_ops.runners.fanout_runner"]
        else:
            sys.modules["agent_ops.runners.fanout_runner"] = original
    assert captured["argv"] == [
        "--plan", "plan_run",
        "--strategy", "flat-pool",
        "--concurrency", "2",
        "--max-workers", "4",
        "--runtime", "local",
        "--model", "composer-2.5",
        "--cwd", "/repo",
        "--spend-limit-usd", "1.5",
        "--refs", "route_都江堰",
        "--force-refs", "route_都江堰",
        "--no-orchestrate",
    ], captured


def test_task_scaled_e2e_author_runner_falls_back_to_venv_python_when_sdk_missing():
    calls: list[list[str]] = []
    original_picker = task_handler_mod._fanout_runner_python
    original_run = task_handler_mod.subprocess.run
    try:
        task_handler_mod._fanout_runner_python = lambda: "/tmp/.venv-fanout/bin/python"

        def _fake_run(argv, check=False):
            calls.append(list(argv))

            class _Result:
                returncode = 0

            return _Result()

        task_handler_mod.subprocess.run = _fake_run
        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="author-runner",
                plan="plan_run_sdkless",
                strategy=None,
                concurrency=None,
                max_workers=None,
                runtime=None,
                model=None,
                cwd=None,
                spend_limit=None,
                refs="route_九寨沟",
                force_refs="route_九寨沟",
                orchestrate=False,
                no_orchestrate=True,
            )
        )
    finally:
        task_handler_mod._fanout_runner_python = original_picker
        task_handler_mod.subprocess.run = original_run
    assert calls == [[
        "/tmp/.venv-fanout/bin/python",
        str((SCRIPTS_ROOT.parent.parent / "agent_ops" / "runners" / "fanout_runner.py").resolve()),
        "--plan",
        "plan_run_sdkless",
        "--refs",
        "route_九寨沟",
        "--force-refs",
        "route_九寨沟",
        "--no-orchestrate",
    ]], calls


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"data cli tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
