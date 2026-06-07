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
    task_baseline_freeze_packet_path,
    task_catalog,
    task_explore_packet_path,
    task_shared_dir,
)
from data.baseline import handle_baseline  # noqa: E402
from explore.handler import handle_explore  # noqa: E402
from task import run as run_mod  # noqa: E402
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


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"data cli tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
