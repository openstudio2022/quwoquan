from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_managed_preflight_codex_provider_filters_cursor_bridge_and_key_requirement(monkeypatch):
    preflight_calls: list[dict] = []

    def _preflight(**kwargs):
        preflight_calls.append(dict(kwargs))
        return {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        }

    monkeypatch.setattr("_common.python_runtime.environment_preflight", _preflight)
    monkeypatch.setattr(
        run_mod,
        "_managed_local_workspace_conflicts",
        lambda _workspace: [
            {
                "kind": "cursor_sdk_bridge",
                "pid": 1234,
                "pgid": 1234,
                "command": "cursor-sdk-bridge --workspace /tmp/quwoquan",
            }
        ],
    )
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_codex_provider",
        spec,
        argparse.Namespace(
            runtime="local",
            baseline_packet=None,
            until=None,
            force_clean_workspace_agent_state=False,
            agent_provider="codex_cli",
        ),
    )

    assert issues == []
    assert preflight_calls[-1]["require_cursor_key"] is False
    assert not batch_root(task_id, "preflight_codex_provider").exists()

def test_managed_workspace_conflicts_detects_orphan_agent_worker(monkeypatch):
    workspace = Path("/tmp/quwoquan")
    monkeypatch.setattr(run_mod, "_current_process_family_pids", lambda _rows=None: {100})
    monkeypatch.setattr(
        run_mod,
        "_process_rows",
        lambda: [
            {"pid": 100, "ppid": 10, "pgid": 100, "command": "current test process"},
            {
                "pid": 200,
                "ppid": 1,
                "pgid": 200,
                "command": (
                    "/opt/homebrew/Cellar/python@3.11/3.11.13/Frameworks/"
                    "Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python -c "
                    "from task.run import _managed_agent_worker_main; "
                    "_managed_agent_worker_main() "
                    "/tmp/qwq-managed-agent/input.json /tmp/qwq-managed-agent/output.json"
                ),
            },
            {
                "pid": 300,
                "ppid": 10,
                "pgid": 300,
                "command": "rg cursor-sdk-bridge|_managed_agent_worker_main|quwoquan_data/scripts/cli.py task run",
            },
        ],
    )

    conflicts = run_mod._managed_local_workspace_conflicts(workspace)

    assert conflicts == [
        {
            "kind": "managed_agent_worker",
            "pid": 200,
            "ppid": 1,
            "pgid": 200,
            "command": (
                "/opt/homebrew/Cellar/python@3.11/3.11.13/Frameworks/"
                "Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python -c "
                "from task.run import _managed_agent_worker_main; "
                "_managed_agent_worker_main() "
                "/tmp/qwq-managed-agent/input.json /tmp/qwq-managed-agent/output.json"
            ),
        }
    ]

def test_managed_preflight_rejects_missing_key_without_creating_batch():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"
    spec.setdefault("content", {})["quotas"] = {
        "entityArticlesPerTarget": 2,
        "imageWorksPerTarget": 2,
        "entityHomepagesPerTarget": 1,
        "routeArticles": 0,
    }
    old_key = os.environ.pop("CURSOR_API_KEY", None)
    try:
        issues = run_mod._managed_preflight(
            task_id,
            "preflight_no_key",
            spec,
            argparse.Namespace(runtime="local", baseline_packet=None),
        )
    finally:
        if old_key is not None:
            os.environ["CURSOR_API_KEY"] = old_key
    assert "CURSOR_API_KEY missing" in issues
    assert not batch_root(task_id, "preflight_no_key").exists()

def test_managed_preflight_blocks_workspace_conflicts(monkeypatch):
    monkeypatch.setattr(
        "_common.python_runtime.environment_preflight",
        lambda **_kwargs: {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        },
    )
    monkeypatch.setattr(
        run_mod,
        "_managed_local_workspace_conflicts",
        lambda _workspace: [
            {
                "kind": "data_cli",
                "pid": 1234,
                "pgid": 1234,
                "command": "python quwoquan_data/scripts/cli.py task run --managed --runtime local",
            }
        ],
    )
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_workspace_conflict",
        spec,
        argparse.Namespace(
            runtime="local",
            baseline_packet=None,
            until=None,
            force_clean_workspace_agent_state=False,
        ),
    )

    assert any("managed local workspace has active" in issue for issue in issues)
    assert not batch_root(task_id, "preflight_workspace_conflict").exists()

def test_managed_preflight_force_cleans_workspace_conflicts(monkeypatch):
    monkeypatch.setattr(
        "_common.python_runtime.environment_preflight",
        lambda **_kwargs: {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        },
    )
    calls: list[list[dict]] = []
    conflict = [
        {
            "kind": "cursor_sdk_bridge",
            "pid": 5678,
            "pgid": 5678,
            "command": "cursor-sdk-bridge --workspace /tmp/quwoquan",
        }
    ]

    def _conflicts(_workspace):
        return conflict if not calls else []

    def _cleanup(rows):
        calls.append(list(rows))
        return {
            "schemaVersion": "quwoquan_data.managed_workspace_cleanup",
            "mode": "force_clean_workspace_agent_state",
            "requestedConflictCount": len(rows),
            "remainingConflicts": [],
        }

    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", _conflicts)
    monkeypatch.setattr(run_mod, "_cleanup_managed_local_workspace_conflicts", _cleanup)
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"

    args = argparse.Namespace(
        runtime="local",
        baseline_packet=None,
        until=None,
        force_clean_workspace_agent_state=True,
    )
    issues = run_mod._managed_preflight(
        task_id,
        "preflight_workspace_force_clean",
        spec,
        args,
    )

    assert not any("managed local workspace has active" in issue for issue in issues)
    assert calls == [conflict]
    assert getattr(args, "_managed_workspace_cleanup_report")["requestedConflictCount"] == 1
    assert not batch_root(task_id, "preflight_workspace_force_clean").exists()

def test_managed_preflight_active_controller_blocks_force_clean(monkeypatch):
    from _common import ops_governance as og

    monkeypatch.setattr(
        "_common.python_runtime.environment_preflight",
        lambda **_kwargs: {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        },
    )
    cleanup_calls: list[list[dict]] = []
    conflict = [
        {
            "kind": "data_cli",
            "pid": 9012,
            "pgid": 9012,
            "command": "python quwoquan_data/scripts/cli.py task run --managed --task same --batch same",
        }
    ]
    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", lambda _workspace: conflict)
    monkeypatch.setattr(
        run_mod,
        "_cleanup_managed_local_workspace_conflicts",
        lambda rows: cleanup_calls.append(list(rows)) or {
            "schemaVersion": "quwoquan_data.managed_workspace_cleanup",
            "mode": "force_clean_workspace_agent_state",
        },
    )
    task_id = _make_task()
    batch_id = "preflight_active_controller_force_clean"
    spec = store.load_spec(task_id)
    spec["status"] = "active"
    args = argparse.Namespace(
        runtime="local",
        baseline_packet=None,
        until=None,
        force_clean_workspace_agent_state=True,
    )

    with og.controller_lease(task_id, batch_id):
        issues = run_mod._managed_preflight(task_id, batch_id, spec, args)

    assert any("GATE_BLOCK controller lease active" in issue for issue in issues)
    assert cleanup_calls == []
    assert not hasattr(args, "_managed_workspace_cleanup_report")

def test_managed_preflight_force_clean_observes_cross_task_data_cli(monkeypatch):
    monkeypatch.setattr(
        "_common.python_runtime.environment_preflight",
        lambda **_kwargs: {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        },
    )
    calls: list[list[dict]] = []
    conflict = [
        {
            "kind": "data_cli",
            "pid": 5678,
            "pgid": 5678,
            "command": "python quwoquan_data/scripts/cli.py task run --task 其它任务 --batch other --managed",
        }
    ]
    monkeypatch.setattr("task.run._managed_local_workspace_conflicts", lambda _workspace: conflict)
    monkeypatch.setattr("task.run._cleanup_managed_local_workspace_conflicts", lambda rows: calls.append(list(rows)) or {})
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"

    args = argparse.Namespace(
        runtime="local",
        baseline_packet=None,
        until=None,
        force_clean_workspace_agent_state=True,
    )
    issues = run_mod._managed_preflight(
        task_id,
        "preflight_workspace_force_clean_cross_task",
        spec,
        args,
    )

    assert not any("managed local workspace has active" in issue for issue in issues)
    assert calls == []
    report = getattr(args, "_managed_workspace_cleanup_report")
    assert report["mode"] == "force_clean_workspace_agent_state_observed_cross_task"
    assert report["crossTaskConflictCount"] == 1

def test_managed_preflight_force_clean_still_cleans_non_cross_conflicts(monkeypatch):
    monkeypatch.setattr(
        "_common.python_runtime.environment_preflight",
        lambda **_kwargs: {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        },
    )
    calls: list[list[dict]] = []
    cross_task = {
        "kind": "data_cli",
        "pid": 5678,
        "pgid": 5678,
        "command": "python quwoquan_data/scripts/cli.py task run --task 其它任务 --batch other --managed",
    }
    bridge = {
        "kind": "cursor_sdk_bridge",
        "pid": 6789,
        "pgid": 6789,
        "command": "cursor-sdk-bridge --workspace /tmp/quwoquan",
    }

    def _conflicts(_workspace):
        return [cross_task, bridge] if not calls else [cross_task]

    def _cleanup(rows):
        calls.append(list(rows))
        return {
            "schemaVersion": "quwoquan_data.managed_workspace_cleanup",
            "mode": "force_clean_workspace_agent_state",
            "requestedConflictCount": len(rows),
            "remainingConflicts": [],
        }

    monkeypatch.setattr("task.run._managed_local_workspace_conflicts", _conflicts)
    monkeypatch.setattr("task.run._cleanup_managed_local_workspace_conflicts", _cleanup)
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"

    args = argparse.Namespace(
        runtime="local",
        baseline_packet=None,
        until=None,
        force_clean_workspace_agent_state=True,
    )
    issues = run_mod._managed_preflight(
        task_id,
        "preflight_workspace_force_clean_mixed",
        spec,
        args,
    )

    assert not any("managed local workspace has active" in issue for issue in issues)
    assert calls == [[bridge]]
    report = getattr(args, "_managed_workspace_cleanup_report")
    assert report["mode"] == "force_clean_workspace_agent_state"

def test_managed_preflight_force_clean_removes_destructive_cross_task_loop(monkeypatch):
    monkeypatch.setattr(
        "_common.python_runtime.environment_preflight",
        lambda **_kwargs: {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        },
    )
    calls: list[list[dict]] = []
    destructive = {
        "kind": "destructive_data_cli",
        "pid": 7788,
        "pgid": 7788,
        "command": (
            "zsh -c \"pkill -KILL -f '其它批次'; "
            "quwoquan_data/scripts/cli.py task run --task 其它任务 --batch other --managed\""
        ),
    }

    def _conflicts(_workspace):
        return [destructive] if not calls else []

    def _cleanup(rows):
        calls.append(list(rows))
        return {
            "schemaVersion": "quwoquan_data.managed_workspace_cleanup",
            "mode": "force_clean_workspace_agent_state",
            "requestedConflictCount": len(rows),
            "remainingConflicts": [],
        }

    monkeypatch.setattr("task.run._managed_local_workspace_conflicts", _conflicts)
    monkeypatch.setattr("task.run._cleanup_managed_local_workspace_conflicts", _cleanup)
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"

    args = argparse.Namespace(
        runtime="local",
        baseline_packet=None,
        until=None,
        force_clean_workspace_agent_state=True,
    )
    issues = run_mod._managed_preflight(
        task_id,
        "preflight_workspace_force_clean_destructive",
        spec,
        args,
    )

    assert not any("managed local workspace has active" in issue for issue in issues)
    assert calls == [[destructive]]

def test_managed_workspace_guard_force_cleans_same_batch_conflicts_inside_lock(monkeypatch):
    monkeypatch.setenv(
        "QWQ_MANAGED_LOCAL_LOCK_DIR",
        str(Path(tempfile.mkdtemp(prefix="managed_guard_lock_"))),
    )
    task_id = _make_task()
    batch_id = "workspace_guard_force_clean"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    ctx.runtime = "local"
    ctx.force_clean_workspace_agent_state = True
    conflict = [
        {
            "kind": "data_cli",
            "pid": 2468,
            "pgid": 2468,
            "command": (
                "python quwoquan_data/scripts/cli.py task run "
                f"--task {task_id} --batch {batch_id} --managed --runtime local"
            ),
        }
    ]
    calls: list[list[dict]] = []

    def _conflicts(_workspace):
        return conflict if not calls else []

    def _cleanup(rows):
        calls.append(list(rows))
        return {
            "schemaVersion": "quwoquan_data.managed_workspace_cleanup",
            "mode": "force_clean_workspace_agent_state",
            "requestedConflictCount": len(rows),
            "remainingConflicts": [],
        }

    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", _conflicts)
    monkeypatch.setattr(run_mod, "_cleanup_managed_local_workspace_conflicts", _cleanup)

    with run_mod._managed_local_workspace_guard(ctx):
        pass

    assert calls == [conflict]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["workspaceCleanupReports"][-1]["requestedConflictCount"] == 1

def test_managed_workspace_guard_observes_cross_task_data_cli_after_lock(monkeypatch):
    monkeypatch.setenv(
        "QWQ_MANAGED_LOCAL_LOCK_DIR",
        str(Path(tempfile.mkdtemp(prefix="managed_guard_lock_cross_"))),
    )
    task_id = _make_task()
    batch_id = "workspace_guard_cross_after_lock"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    ctx.runtime = "local"
    ctx.force_clean_workspace_agent_state = True
    conflict = [
        {
            "kind": "data_cli",
            "pid": 9753,
            "pgid": 9753,
            "command": "python quwoquan_data/scripts/cli.py task run --task 其它任务 --batch other --managed",
        }
    ]
    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", lambda _workspace: conflict)
    monkeypatch.setattr(
        run_mod,
        "_cleanup_managed_local_workspace_conflicts",
        lambda _rows: (_ for _ in ()).throw(AssertionError("cross-task must not be cleaned")),
    )

    with run_mod._managed_local_workspace_guard(ctx):
        pass

    state = run_mod.load_workflow_state(task_id, batch_id)
    report = state["workspaceCleanupReports"][-1]
    assert report["mode"] == "force_clean_workspace_agent_state_observed_cross_task_after_lock"
    assert report["crossTaskConflictCount"] == 1

def test_managed_preflight_blocks_unproven_open_license_image_scale(monkeypatch):
    monkeypatch.setattr(
        "_common.python_runtime.environment_preflight",
        lambda **_kwargs: {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        },
    )
    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", lambda _workspace: [])
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": f"景区{i}"}
        for i in range(100)
    ]
    spec["acceptance"] = {"minEntities": 100, "requiredAngles": ["image"]}
    spec.setdefault("content", {})["research"] = {
        "lanes": ["homepage", "article", "image"],
        "allowAiImages": False,
        "imageAssetStrategy": "open_license_publish",
    }
    spec["content"]["quotas"] = {
        "entityArticlesPerTarget": 4,
        "imageWorksPerTarget": 2,
        "entityHomepagesPerTarget": 1,
        "routeArticles": 0,
    }

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_open_license_scale",
        spec,
        argparse.Namespace(runtime="local", baseline_packet="baseline.json", until="download_plan"),
    )

    assert any("openLicenseScaleProof" in issue for issue in issues), issues
    assert not batch_root(task_id, "preflight_open_license_scale").exists()

def test_managed_preflight_allows_site_supply_dynamic_packet_without_entity_line_quotas(monkeypatch):
    from _common.content_object import write_brief_object

    monkeypatch.setattr(
        "_common.python_runtime.environment_preflight",
        lambda **_kwargs: {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        },
    )
    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", lambda _workspace: [])
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"
    spec.setdefault("scope", {})["coverageTargets"] = []
    spec.setdefault("content", {})["research"] = {
        "lanes": ["article"],
        "allowAiImages": False,
        "imageAssetStrategy": "open_license_publish",
    }
    spec["content"]["quotas"] = {
        "entityArticlesPerTarget": 0,
        "imageWorksPerTarget": 0,
        "entityHomepagesPerTarget": 0,
        "routeArticles": 0,
    }
    spec.setdefault("workflowPolicy", {})["siteSupplyDynamicContentPlan"] = True
    batch_id = "site_supply_dynamic_managed_preflight"
    root = batch_root(task_id, batch_id)
    shared = root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "evidence.md").write_text("动态景区甲真实站点候选证据。", encoding="utf-8")
    ref = "candidate_dynamic_managed_1"
    entity_ref = "/entity/地点/景区/动态景区甲"
    write_brief_object(
        task_id,
        batch_id,
        ref,
        {
            "schemaVersion": "quwoquan.compose.brief",
            "templateId": "景区_攻略",
            "titleHint": "动态景区甲行前指南",
            "entityRefs": [entity_ref],
            "evidenceRefs": ["_shared/evidence.md"],
            "writingIntent": "planning_consultation",
            "mustIncludeFacts": ["动态景区甲"],
        },
        content_type="article",
    )
    write_json(
        shared / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": batch_id,
            "generatedBy": "site_supply_content_plan_bridge",
            "sourceSite": {"vertical": "travel", "siteId": "qunar_guide", "batchId": "real_100"},
            "items": [
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": "动态景区甲行前指南",
                    "entityRefs": [entity_ref],
                    "evidenceRefs": ["_shared/evidence.md"],
                    "rationale": "site supply dynamic packet target",
                    "writingIntent": "planning_consultation",
                }
            ],
        },
    )

    issues = run_mod._managed_preflight(
        task_id,
        batch_id,
        spec,
        argparse.Namespace(runtime="local", baseline_packet=None, until="produce_author"),
    )

    assert issues == []

