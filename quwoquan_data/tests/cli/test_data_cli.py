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
import shutil
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
for _readonly_dir in ("schema", "sop"):
    _src = DATA_ROOT / _readonly_dir
    _dst = _TMP / _readonly_dir
    if _dst.exists():
        continue
    try:
        _dst.symlink_to(_src, target_is_directory=True)
    except OSError:
        shutil.copytree(_src, _dst)

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.command_packet import build_packet, write_packet  # noqa: E402
from _common.article_package import compute_document_sha256, sha256_text  # noqa: E402
from _common.batch_manifest import write_batch_manifest  # noqa: E402
from _common.io import read_json, read_ndjson, write_json  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_audit_markdown_path,
    batch_audit_summary_path,
    batch_entity_object_dir,
    batch_workflow_state_path,
    ensure_batch_layout,
    ensure_task_layout,
    committed_task_spec,
    committed_task_progress,
    fanout_plan_path,
    fanout_run_matrix_path,
    task_baseline_freeze_packet_path,
    task_catalog,
    task_explore_packet_path,
    task_shared_dir,
)
from data.baseline import handle_baseline  # noqa: E402
from explore.handler import handle_explore  # noqa: E402
from _common import fanout_plan as fp  # noqa: E402
from _common.source_unit import write_source_unit  # noqa: E402
from task import run as run_mod  # noqa: E402
from task import handler as task_handler_mod  # noqa: E402
from task import store  # noqa: E402
from _common import python_runtime  # noqa: E402

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

    env_help = subprocess.run(
        [sys.executable, str(CLI), "env", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert env_help.returncode == 0, env_help.stderr
    for name in ("doctor", "prepare", "preflight", "ready"):
        assert name in env_help.stdout


def test_python_runtime_prefers_data_venv_when_current_lacks_cursor_sdk():
    original_candidates = python_runtime.candidate_pythons
    original_has_modules = python_runtime.python_has_modules
    current = Path("/usr/bin/python3")
    data_python = python_runtime.DATA_VENV_PYTHON
    try:
        python_runtime.candidate_pythons = lambda include_current=True: [current, data_python]

        def _fake_has_modules(python, modules):
            if Path(python) == data_python:
                return True, []
            return False, ["cursor_sdk: No module named 'cursor_sdk'"]

        python_runtime.python_has_modules = _fake_has_modules
        assert python_runtime.resolve_data_agent_python(include_current=True) == data_python
    finally:
        python_runtime.candidate_pythons = original_candidates
        python_runtime.python_has_modules = original_has_modules


def test_environment_preflight_gates_key_runtime_and_network():
    original_runtime_report = python_runtime.runtime_report
    original_network = python_runtime.check_network_endpoints
    old_key = os.environ.pop("CURSOR_API_KEY", None)
    try:
        python_runtime.runtime_report = lambda: {
            "schemaVersion": "quwoquan_data.python_runtime",
            "currentPython": "/usr/bin/python3",
            "resolvedPython": str(python_runtime.DATA_VENV_PYTHON),
            "ready": True,
            "candidates": [],
        }
        missing_key = python_runtime.environment_preflight(check_network=True)
        assert missing_key["ready"] is False
        assert "CURSOR_API_KEY missing" in missing_key["issues"]
        assert missing_key["network"]["skipped"] is True

        os.environ["CURSOR_API_KEY"] = "not-a-cursor-key"
        bad_key = python_runtime.environment_preflight(check_network=True)
        assert bad_key["ready"] is False
        assert "CURSOR_API_KEY format invalid" in bad_key["issues"]
        assert bad_key["network"]["skipped"] is True

        os.environ["CURSOR_API_KEY"] = "crsr_" + ("x" * 32)
        python_runtime.check_network_endpoints = lambda **_kwargs: {
            "checked": True,
            "skipped": False,
            "ready": True,
            "endpoints": [],
            "issues": [],
        }
        ready = python_runtime.environment_preflight(check_network=True)
        assert ready["ready"] is True
        assert ready["network"]["checked"] is True
    finally:
        python_runtime.runtime_report = original_runtime_report
        python_runtime.check_network_endpoints = original_network
        if old_key is None:
            os.environ.pop("CURSOR_API_KEY", None)
        else:
            os.environ["CURSOR_API_KEY"] = old_key


def test_network_probe_falls_back_to_get_when_head_fails():
    original_urlopen = python_runtime.urlrequest.urlopen
    calls: list[str] = []

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _fake_urlopen(request, timeout):  # noqa: ARG001
        calls.append(request.get_method())
        if request.get_method() == "HEAD":
            raise OSError("EOF occurred in violation of protocol")
        return _FakeResponse()

    try:
        python_runtime.urlrequest.urlopen = _fake_urlopen
        row = python_runtime._probe_endpoint("https://api2.cursor.sh/", timeout_seconds=1)
    finally:
        python_runtime.urlrequest.urlopen = original_urlopen

    assert calls == ["HEAD", "GET"]
    assert row["reachable"] is True
    assert row["method"] == "GET"


def test_network_probe_falls_back_to_curl_when_urllib_fails():
    original_urlopen = python_runtime.urlrequest.urlopen
    original_which = python_runtime.shutil.which
    original_run = python_runtime.subprocess.run

    class _FakeProc:
        returncode = 0
        stdout = "200"
        stderr = ""

    try:
        python_runtime.urlrequest.urlopen = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("EOF occurred in violation of protocol")
        )
        python_runtime.shutil.which = lambda name: "/usr/bin/curl" if name == "curl" else None
        python_runtime.subprocess.run = lambda *_args, **_kwargs: _FakeProc()
        row = python_runtime._probe_endpoint("https://api2.cursor.sh/", timeout_seconds=1)
    finally:
        python_runtime.urlrequest.urlopen = original_urlopen
        python_runtime.shutil.which = original_which
        python_runtime.subprocess.run = original_run

    assert row["reachable"] is True
    assert row["method"] == "curl"
    assert row["status"] == 200


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


def test_baseline_allows_dynamic_site_supply_task_without_catalog():
    task_id = _make_task("旅行/主题/网站供给线/百级动态验证", with_baseline=False)
    spec = store.load_spec(task_id)
    spec["taskArchetype"] = "theme_collection"
    spec["organizeBy"] = "主题"
    spec["key"] = "网站供给线"
    spec.setdefault("scope", {})["theme"] = "百级动态验证"
    spec.setdefault("workflowPolicy", {})["siteSupplyDynamicContentPlan"] = True
    store.save_spec(spec)

    handle_baseline(
        argparse.Namespace(
            task=task_id,
            catalog=None,
            spec_doc=None,
            design_doc=None,
            acceptance_doc=None,
            workflow_doc=None,
            command_matrix_doc=None,
            catalog_config=None,
            naming_rules=None,
            geo_band_rules=None,
            schema_files=[],
            config_files=[],
            output=None,
        )
    )

    packet = read_json(task_baseline_freeze_packet_path(task_id))
    report = read_json(task_shared_dir(task_id) / "baseline_report.json")
    assert report["status"] == "passed"
    assert report["issues"] == []
    assert packet["summary"]["siteSupplyDynamicContentPlan"] is True
    assert packet["summary"]["catalogRequired"] is False


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
    # download_plan 由 CLI auto_research 自动完成、build_homepage 由确定性 builder 自动物化，
    # 首个需 Agent 语义介入的暂停点是 content_plan。
    assert state["waitingCheckpoint"] == "content_plan"


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
    # scaled-e2e prepare 走标准 DAG：download_plan/build_homepage 已被 CLI 自动化，
    # prepare 在首个 Agent 语义 checkpoint content_plan 处暂停（不写正文）。
    assert state["waitingCheckpoint"] == "content_plan", state
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
            return ([Path("/tmp/root")], [])

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
    import verify.handler as verify_handler_mod

    called: list[tuple[str, str]] = []
    original = task_handler_mod.gate_verify
    original_sample = verify_handler_mod.handle_sample_drift
    original_golden = verify_handler_mod.handle_goldenset
    try:
        def _fake_gate_verify(*, task=None, batch=None, release=None, scope="current"):
            called.append((task, batch))
            return ([Path("/tmp/root")], [])

        drift_called: list[tuple[str, str, float]] = []
        golden_called = {"count": 0}

        def _fake_sample_drift(args):
            drift_called.append((args.task, args.batch, args.fraction))

        def _fake_goldenset(args):
            golden_called["count"] += 1

        task_handler_mod.gate_verify = _fake_gate_verify
        verify_handler_mod.handle_sample_drift = _fake_sample_drift
        verify_handler_mod.handle_goldenset = _fake_goldenset
        _seed_frozen_plan("plan_verify")
        task_id = "旅行/地域/四川省/plan_verify_task"
        batch_id = "fanout_plan_verify"
        write_json(
            fanout_run_matrix_path("plan_verify"),
            {
                "schemaVersion": "quwoquan_data.fanout_run_matrix",
                "planId": "plan_verify",
                "orchestrators": [{"worker": "part::四川省", "reached": True, "missing": [], "error": None}],
                "workers": [],
                "summary": {"orchestrated": 1, "completed": 1, "failed": 0, "attemptFailures": 0, "startupFailures": 0, "orchestrationFailed": 0},
            },
        )
        write_json(
            batch_workflow_state_path(task_id, batch_id),
            {
                "schemaVersion": "quwoquan.task.workflow_state",
                "taskId": task_id,
                "batchId": batch_id,
                "completed": ["download_plan", "build_homepage", "content_plan", "produce_compose", "produce_author", "review", "release"],
                "waitingCheckpoint": None,
                "status": "succeeded",
                "failedObjects": [],
            },
        )
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
        verify_handler_mod.handle_sample_drift = original_sample
        verify_handler_mod.handle_goldenset = original_golden
    assert called == [("旅行/地域/四川省/plan_verify_task", "fanout_plan_verify")], called
    assert drift_called == [("旅行/地域/四川省/plan_verify_task", "fanout_plan_verify", 1.0)]
    assert golden_called["count"] == 1


def test_task_scaled_e2e_verify_plan_rejects_empty_run():
    import contextlib
    import io
    import verify.handler as verify_handler_mod

    original = task_handler_mod.gate_verify
    original_sample = verify_handler_mod.handle_sample_drift
    original_golden = verify_handler_mod.handle_goldenset
    stderr = io.StringIO()
    try:
        task_handler_mod.gate_verify = lambda **_: ([], [])
        verify_handler_mod.handle_sample_drift = lambda args: None
        verify_handler_mod.handle_goldenset = lambda args: None
        _seed_frozen_plan("plan_empty_verify")
        with contextlib.redirect_stderr(stderr):
            try:
                task_handler_mod.handle_scaled_e2e(
                    argparse.Namespace(
                        scaled_e2e_command="verify",
                        task=None,
                        batch=None,
                        plan="plan_empty_verify",
                    )
                )
            except SystemExit as exc:
                assert int(exc.code) == 1
            else:
                raise AssertionError("empty scaled E2E run should fail")
    finally:
        task_handler_mod.gate_verify = original
        verify_handler_mod.handle_sample_drift = original_sample
        verify_handler_mod.handle_goldenset = original_golden
    captured = stderr.getvalue()
    assert "missing run_matrix.json" in captured
    assert "no current artifacts found" in captured


def _seed_entity_object_for_audit(task_id: str, batch_id: str, *, name: str) -> None:
    from _common.batch_asset_registry import BatchAssetRegistry, allocate_post_asset_id
    from _common.batch_manifest import load_batch_manifest

    ent = batch_entity_object_dir(task_id, batch_id, "地点", "景区", name)
    write_source_unit(
        ent,
        ordinal=1,
        source_id="overview_baike",
        source_md=f"# {name}\n\n概述",
        clean_md=f"# {name}\n\n概述",
        platform="baike",
        source_category="overview_baike",
        url=f"https://example.com/{name}",
        title=f"{name}百科",
        target_ref=f"/entity/地点/景区/{name}",
    )
    write_json(
        ent / "_entity.json",
        {
            "label": name,
            "domain": "地点",
            "type": "景区",
            "sourceTaskId": task_id,
            "conditionProfile": {
                "regions": ["平原都市" if name == "都江堰" else "山地森林"],
                "seasons": ["秋"],
                "evidenceRefs": [
                    {
                        "field": "regions",
                        "value": "平原都市" if name == "都江堰" else "山地森林",
                        "source": "source.md",
                        "path": f"entities/地点/景区/{name}/1.download/sources/01.overview_baike/source.md",
                    }
                ],
            },
        },
    )
    global_seq = int(load_batch_manifest(task_id, batch_id)["globalBatchSeq"])
    registry = BatchAssetRegistry(task_id=task_id, batch_id=batch_id, global_batch_seq=global_seq)
    asset_id = allocate_post_asset_id(
        entity_name=name,
        role="cover",
        ref=f"{name}_主页",
        global_batch_seq=global_seq,
        registry=registry,
    )
    (ent / "page.md").write_text(
        f"# {name}\n\n"
        + (name * 460)
        + f"\n\n{{asset://{asset_id}|wrapRight|{name}配图|width=45%}}\n",
        encoding="utf-8",
    )
    (ent / "assets").mkdir(parents=True, exist_ok=True)
    (ent / "assets" / f"{asset_id}.jpg").write_bytes(b"cover")
    write_json(
        ent / "manifest.json",
        {"assets": [{"assetId": asset_id, "fileName": f"{asset_id}.jpg", "caption": f"{name}配图"}]},
    )
    write_json(
        ent / "2.quality" / "quality_analysis.json",
        {
            "entityRef": f"/entity/地点/景区/{name}",
            "baseDraft": {"sourceRef": f"entities/地点/景区/{name}/1.download/sources/01.overview_baike/source.md"},
            "candidateCount": 1,
            "candidates": [{"sourceRef": f"entities/地点/景区/{name}/1.download/sources/01.overview_baike/source.md", "score": 0.9, "length": 100}],
            "recommendation": "proceed",
            "issues": [],
            "sourcePaths": [f"entities/地点/景区/{name}/1.download/sources/01.overview_baike/source.md"],
        },
    )
    write_json(ent / "3.compose" / "entity_page_input.json", {"payload": {"name": name}})
    (ent / "4.draft").mkdir(parents=True, exist_ok=True)
    (ent / "4.draft" / "page.md").write_text((ent / "page.md").read_text(encoding="utf-8"), encoding="utf-8")
    (ent / "5.review").mkdir(parents=True, exist_ok=True)
    write_json(
        ent / "5.review" / "review.json",
        {
            "decision": "approved",
            "issues": [],
            "fallbackStage": None,
            "checks": {
                "entityPageQuality": {"passed": True, "issues": []},
                "sourceReadiness": {"passed": True, "issues": []},
            },
        },
    )
    write_json(
        ent / "5.review" / "provenance.json",
        {
            "schemaVersion": "quwoquan_data.provenance",
            "ref": f"/entity/地点/景区/{name}",
            "final": {"generator": "agent", "agentRunId": f"run-{name}", "entityRefs": [f"/entity/地点/景区/{name}"], "articleDigest": None},
            "agentInput": {"writingPack": f"entities/地点/景区/{name}/3.compose/entity_page_input.json"},
            "originalSources": [{"path": f"entities/地点/景区/{name}/1.download/sources/01.overview_baike/source.md", "url": f"https://example.com/{name}"}],
            "gateResults": {"decision": "approved", "checks": {"entityPageQuality": True, "sourceReadiness": True}},
            "citedSourcePaths": [f"entities/地点/景区/{name}/1.download/sources/01.overview_baike/source.md"],
        },
    )
    write_json(
        ent / "5.review" / "finalization_report.json",
        {
            "schemaVersion": "quwoquan_data.finalization_report",
            "draftArticleRef": "4.draft/page.md",
            "finalArticleRef": "page.md",
            "draftSha256": compute_document_sha256((ent / "4.draft" / "page.md").read_text(encoding="utf-8")),
            "finalSha256": compute_document_sha256((ent / "page.md").read_text(encoding="utf-8")),
        },
    )


def _seed_verified_post_for_audit(task_id: str, batch_id: str, *, ref: str, title: str, name: str) -> None:
    from _common.content_object import register_content_object

    register_content_object(task_id, batch_id, ref, content_type="article", angle="攻略", title=title)
    from _common.content_object import content_object_dir
    obj = content_object_dir(task_id, batch_id, ref)
    article = (
        f"# {title}\n\n"
        f"第一次去[{name}](/entity/地点/景区/{name})，更适合把行程当成“先看主线工程、再看城内转场、最后处理返程”的顺序题，而不是临场想到哪走到哪。\n\n"
        "## 先定游览顺序\n\n"
        "先去离堆公园一线看鱼嘴、飞沙堰和宝瓶口的关系，再根据体力决定是否补城内步行段，这样路线会更稳，也方便把最重要的视角放在前半天。\n\n"
        "## 交通怎么去\n\n"
        "如果你从成都主城出发，交通上更省心的做法通常是高铁加短驳；自驾也可以，但停车、进出城和景区周边排队都要额外算时间。怎么去并不是小事，它直接决定你上午能不能把核心段走完。\n\n"
        "## 预约与排队怎么取舍\n\n"
        "旺季和节假日一定要先看预约与开放时间，热门时段排队会明显拉长。如果你只想抓住第一次到访的重点，我会建议宁可压缩外围闲逛，也别赶在中午最挤的时候硬冲完整大圈。\n\n"
        "## 什么情况值得调整\n\n"
        "如果你同行里有人更在意拍照，就把河道和城门一线留到光线更稳定的时段；如果更在意工程理解，建议把讲解或导览放在最前面。真正的取舍不是多看一个点，而是避免来回折返，把注意力留给最能解释都江堰价值的那一段。\n\n"
        "## 返程前最后提醒\n\n"
        "返程不要只看景区出口距离，交通切换、停车取车和高铁进站都要留余量。我的建议是把最不确定的一段放在下午后半程之前解决，别赶、别赌临场空窗，这样第一次去都江堰也能把核心体验和返程节奏都兼顾好。\n\n"
        "## 带老人或孩子时怎么改\n\n"
        "如果你是带老人或孩子同行，我会建议把步行最密集的一段缩短，把休息点和补给点放进路线规划里。与其追求一次性走完所有名称最响的点位，不如先保证交通衔接、排队耐受和休整节奏，这样体验反而更完整，也更容易判断哪些段落值得下次再来补足。\n\n"
        "## 为什么这条攻略值得照着执行\n\n"
        "这条写法的重点不是替你做唯一答案，而是帮你先完成第一轮取舍：先后顺序怎么排、交通怎么去、预约与排队要不要避开、返程窗口留多少余量。只要这四件事先想清楚，第一次去都江堰通常就不会因为局部犹豫而把整天节奏拖乱。"
    )
    obj.mkdir(parents=True, exist_ok=True)
    (obj / "article.md").write_text(article, encoding="utf-8")
    (obj / "2.quality").mkdir(parents=True, exist_ok=True)
    (obj / "3.compose").mkdir(parents=True, exist_ok=True)
    (obj / "4.draft").mkdir(parents=True, exist_ok=True)
    (obj / "4.draft" / "draft.article.md").write_text(article, encoding="utf-8")
    (obj / "1.download").mkdir(parents=True, exist_ok=True)
    (obj / "5.review").mkdir(parents=True, exist_ok=True)
    source_ref = f"entities/地点/景区/{name}/1.download/sources/01.overview_baike/source.md"
    source_md = f"# {name}\n\n概述"
    article_digest = compute_document_sha256(article)
    write_json(
        obj / "2.quality" / "quality_analysis.json",
        {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id,
            "batchId": batch_id,
            "step": "quality_analysis",
            "ref": ref,
            "payload": {
                "topicId": ref,
                "qualityScore": 90,
                "recommendation": "proceed",
                "templateId": "travel.route.guide",
                "title": title,
                "sourceUrls": [f"https://example.com/{name}"],
                "sourcePaths": [source_ref],
                "evidenceBundle": {
                    "storySpine": {
                        "mustIncludeFacts": [],
                        "routeEntities": [name],
                    }
                },
            },
        },
    )
    write_json(
        obj / "manifest.json",
        {
            "topicId": ref,
            "contentType": "article",
            "entityRefs": [f"/entity/地点/景区/{name}"],
            "normalizedEntityRefs": [f"entity:景区:{name}"],
            "tagRefs": ["Topic/旅行/景区攻略", "Format/内容角度/攻略"],
            "conditionContext": {"region": "四川"},
            "sourceUrls": [f"https://example.com/{name}"],
            "assets": [],
            "carrier": "article",
            "generator": "agent",
            "generatorModel": "test-agent/audit",
            "citedSourceRefs": [source_ref],
            "reviewDecision": "approved",
            "publishLayout": "article",
            "publishAngle": "攻略",
            "publishTitle": title,
            "publishSeq": 1,
            "createdAt": "2026-06-12T00:00:00Z",
            "updatedAt": "2026-06-12T00:00:00Z",
            "sourceTaskId": task_id,
            "sourceBatchId": batch_id,
            "writingIntent": "planning_consultation",
            "baseSourceRef": source_ref,
            "intersectionHints": [
                {
                    "dimension": "content",
                    "source": "entityRef",
                    "tagRefs": [],
                    "actionType": "view_object",
                    "actionTargetId": f"entity:景区:{name}",
                },
                {
                    "dimension": "interest",
                    "source": "tagRef",
                    "tagRefs": ["Topic/旅行/景区攻略"],
                    "actionType": "join",
                    "actionTargetId": "Topic/旅行/景区攻略",
                },
                {
                    "dimension": "location",
                    "source": "geoTagRef",
                    "tagRefs": [],
                    "actionType": "view_object",
                    "actionTargetId": "四川",
                },
            ],
        },
    )
    write_json(
        obj / "1.download" / "source_refs.json",
        {
            "schemaVersion": "quwoquan_data.source_refs",
            "baseSourceRef": source_ref,
            "citedSourceRefs": [source_ref],
            "sourcePaths": [source_ref],
            "sources": [
                {
                    "sourceRef": source_ref,
                    "sourceUnitRef": f"entities/地点/景区/{name}/1.download/sources/01.overview_baike",
                    "sourceMarkdown": source_md,
                    "sourceMarkdownSha256": sha256_text(source_md),
                }
            ],
        },
    )
    write_json(
        obj / "5.review" / "review.json",
        {
            "topicId": ref,
            "decision": "approved",
            "issues": [],
            "humanReviewRequired": False,
            "generator": "agent",
            "checks": {
                "generatorProvenance": {"passed": True},
                "factTraceability": {"passed": True},
                "baseDraftFidelity": {"passed": True},
                "writingIntentConsistency": {"passed": True},
            },
        },
    )
    write_json(
        obj / "5.review" / "review_gate.json",
        {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "payload": {
                "passed": True,
                "issues": [],
                "status": "green",
            },
        },
    )
    write_json(
        obj / "5.review" / "review_ledger.json",
        {
            "schemaVersion": "quwoquan_data.review_ledger",
            "taskId": task_id,
            "batchId": batch_id,
            "ref": ref,
            "policy": {
                "autoApprove": {"agentMinScore": 3, "requireHumanWhenDoubtful": True, "autoDiscardScoreAtMost": 1},
                "reprocess": {"maxAttempts": 3},
            },
            "article": {
                "kind": "article",
                "target": ref,
                "agentJudgment": "credible",
                "agentScore": 4,
                "humanJudgment": "unjudged",
                "humanScore": None,
                "humanOverride": None,
                "reprocessCount": 0,
                "reasons": [],
                "notes": "",
            },
            "images": [],
            "facts": [],
        },
    )
    write_json(
        obj / "5.review" / "review_entities.json",
        {
            "schemaVersion": "quwoquan_data.review_entities",
            "ref": ref,
            "entities": [
                {
                    "name": name,
                    "domain": "地点",
                    "type": "景区",
                    "ref": f"/entity/地点/景区/{name}",
                    "hasHomepage": True,
                    "generated": False,
                    "evidenceRef": "overview_baike",
                }
            ],
        },
    )
    write_json(
        obj / "5.review" / "provenance.json",
        {
            "schemaVersion": "quwoquan_data.provenance",
            "ref": ref,
            "final": {
                "publishTitle": title,
                "publishSeq": 1,
                "generator": "agent",
                "model": "test-agent/audit",
                "agentRunId": f"run-{ref}",
                "agentId": "agent-audit",
                "sessionTrace": "audit-session",
                "styleFamily": "route-guide",
                "openingStrategy": "scene_immersion",
                "articleDigest": article_digest,
                "entityRefs": [f"/entity/地点/景区/{name}"],
            },
            "agentInput": {
                "writingPack": "3.compose/writing_pack.json",
                "prompt": "4.draft/prompt.md",
                "title": title,
                "styleFamily": "route-guide",
                "promptSha256": "sha256:a",
                "writingPackSha256": "sha256:b",
                "sourceBundleSha256": "sha256:c",
                "draftSha256": "sha256:d",
            },
            "originalSources": [{"path": source_ref, "url": f"https://example.com/{name}"}],
            "gateResults": {"decision": "approved", "checks": {"generatorProvenance": True, "factTraceability": True}},
            "citedSourcePaths": [source_ref],
        },
    )
    write_json(
        obj / "5.review" / "finalization_report.json",
        {
            "schemaVersion": "quwoquan_data.finalization_report",
            "draftArticleRef": "4.draft/draft.article.md",
            "finalArticleRef": "article.md",
            "draftSha256": article_digest,
            "finalSha256": article_digest,
            "composeSnapshotMatchesDraft": True,
            "bodyChanged": False,
            "frontmatterOnlyChange": False,
        },
    )


def test_gate_verify_writes_batch_audit_summary():
    task_id = "旅行/地域/四川省/景区/三景点真实实跑"
    batch_id = "audit_batch"
    ensure_task_layout(task_id)
    ensure_batch_layout(task_id, batch_id, "produce")
    write_batch_manifest(
        task_id,
        batch_id,
        command="produce",
        coverage_targets=[{"entityType": "地点/景区", "name": "都江堰"}],
    )
    _seed_entity_object_for_audit(task_id, batch_id, name="都江堰")
    _seed_verified_post_for_audit(task_id, batch_id, ref="都江堰_攻略", title="都江堰一日游怎么玩", name="都江堰")
    roots, issues = task_handler_mod.gate_verify(task=task_id, batch=batch_id, scope="current")
    assert issues == [], issues
    summary = read_json(batch_audit_summary_path(task_id, batch_id))
    assert summary["schemaVersion"] == "quwoquan_data.batch_audit_summary/1"
    assert summary["scriptGate"]["status"] == "passed"
    assert summary["focusEntity"]["name"] == "都江堰"
    assert summary["samples"]["article"]["exists"] is True
    assert summary["samples"]["entity"]["exists"] is True
    assert summary["manualChecklist"]["minimumHumanSampleCount"] == 1
    md = batch_audit_markdown_path(task_id, batch_id).read_text(encoding="utf-8")
    assert "都江堰文章对象" in md
    assert "都江堰实体对象" in md


def test_task_scaled_e2e_verify_plan_writes_partition_audit_summary():
    import verify.handler as verify_handler_mod

    original_sample = verify_handler_mod.handle_sample_drift
    original_golden = verify_handler_mod.handle_goldenset
    try:
        verify_handler_mod.handle_sample_drift = lambda args: None
        verify_handler_mod.handle_goldenset = lambda args: None

        plan = fp.new_plan(
            "plan_audit",
            "四川三景点真实并发实跑",
            "travel",
            defaults={"entityType": "地点/景区", "taskName": "四川三景点真实并发实跑", "category": "景区"},
        )
        fp.add_partition(plan, "成都平原")
        fp.add_leaves(plan, ["成都平原"], [{"name": "都江堰"}])
        fp.freeze_plan(plan, confirmed=True)
        fp.save_plan(plan)

        task_id = "旅行/地域/成都平原/景区/四川三景点真实并发实跑"
        batch_id = "fanout_plan_audit"
        ensure_task_layout(task_id)
        ensure_batch_layout(task_id, batch_id, "produce")
        write_batch_manifest(
            task_id,
            batch_id,
            command="produce",
            coverage_targets=[{"entityType": "地点/景区", "name": "都江堰"}],
        )
        _seed_entity_object_for_audit(task_id, batch_id, name="都江堰")
        _seed_verified_post_for_audit(task_id, batch_id, ref="都江堰_攻略", title="都江堰一日游怎么玩", name="都江堰")
        write_json(
            fanout_run_matrix_path("plan_audit"),
            {
                "schemaVersion": "quwoquan_data.fanout_run_matrix",
                "planId": "plan_audit",
                "orchestrators": [{"worker": "part::成都平原", "reached": True, "missing": [], "error": None}],
                "workers": [],
                "summary": {"orchestrated": 1, "completed": 1, "failed": 0, "attemptFailures": 0, "startupFailures": 0, "orchestrationFailed": 0},
            },
        )
        write_json(
            batch_workflow_state_path(task_id, batch_id),
            {
                "schemaVersion": "quwoquan.task.workflow_state",
                "taskId": task_id,
                "batchId": batch_id,
                "completed": ["download_plan", "build_homepage", "content_plan", "produce_compose", "produce_author", "review", "release"],
                "waitingCheckpoint": None,
                "status": "succeeded",
                "failedObjects": [],
            },
        )

        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="verify",
                task=None,
                batch=None,
                plan="plan_audit",
            )
        )
    finally:
        verify_handler_mod.handle_sample_drift = original_sample
        verify_handler_mod.handle_goldenset = original_golden

    summary = read_json(batch_audit_summary_path(task_id, batch_id))
    assert summary["focusEntity"]["name"] == "都江堰"
    assert summary["samples"]["article"]["path"].startswith("posts/article/攻略/都江堰一日游怎么玩/1")


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
