from __future__ import annotations

import argparse
import os
import sys
import types

import pytest

from _common import creative_brief as cb


from support.task_workflow_fixtures import *  # noqa: F401,F403


@pytest.fixture(autouse=True)
def _commercial_execution_branch(monkeypatch):
    monkeypatch.setattr(
        "_common.execution_branch.current_git_branch",
        lambda **_kwargs: "feature/homepage-commercial-lane",
    )


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
    assert preflight_calls[-1]["check_cursor_startup"] is False
    assert not batch_root(task_id, "preflight_codex_provider").exists()

def test_cleanup_reclaims_same_pgid_orphan_bridge_by_pid_tree(monkeypatch):
    """WP5 契约：同进程组的孤儿 cursor bridge（ppid=1，上游 runner 子进程退出后
    reparent 到 launchd 仍保留旧 pgid）必须按 pid 树精准回收，否则同组后续
    managed preflight 永久 BLOCK；非孤儿的同组进程仍必须跳过（防自杀）。"""
    current_pgid = os.getpgrp()
    monkeypatch.setattr(run_mod, "_current_process_family_pids", lambda _rows=None: {100})
    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", lambda _ws: [])
    killed: list[int] = []
    monkeypatch.setattr(run_mod, "_terminate_pid_tree_if_alive", lambda pid: killed.append(pid))

    report = run_mod._cleanup_managed_local_workspace_conflicts(
        [
            {
                "kind": "cursor_sdk_bridge",
                "pid": 4321,
                "ppid": 1,
                "pgid": current_pgid,
                "command": "cursor-sdk-bridge --workspace /tmp/quwoquan",
            },
            {
                "kind": "cursor_sdk_bridge",
                "pid": 4322,
                "ppid": 999,
                "pgid": current_pgid,
                "command": "cursor-sdk-bridge --workspace /tmp/quwoquan",
            },
        ]
    )

    assert killed == [4321], killed
    scopes = {row.get("scope") for row in report["terminated"]}
    assert "orphan_pid_tree_same_pgid" in scopes, report["terminated"]
    reasons = {row.get("reason") for row in report["skipped"]}
    assert "current process group" in reasons, report["skipped"]


def test_managed_workspace_conflicts_detects_orphan_agent_worker(monkeypatch):
    workspace = Path("/tmp/quwoquan")
    monkeypatch.setattr(run_mod, "_current_process_family_pids", lambda _rows=None: {100})
    monkeypatch.setattr(
        run_mod,
        "_process_cwd",
        lambda pid: "/tmp/quwoquan" if pid == 200 else "",
    )
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
            "cwd": "/tmp/quwoquan",
            "command": (
                "/opt/homebrew/Cellar/python@3.11/3.11.13/Frameworks/"
                "Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python -c "
                "from task.run import _managed_agent_worker_main; "
                "_managed_agent_worker_main() "
                "/tmp/qwq-managed-agent/input.json /tmp/qwq-managed-agent/output.json"
            ),
        }
    ]


def test_managed_workspace_conflicts_detects_same_workspace_cursor_bridge(monkeypatch):
    workspace = Path("/tmp/quwoquan")
    monkeypatch.setattr(run_mod, "_current_process_family_pids", lambda _rows=None: {100})
    monkeypatch.setattr(run_mod, "_process_cwd", lambda _pid: "")
    monkeypatch.setattr(
        run_mod,
        "_process_rows",
        lambda: [
            {"pid": 100, "ppid": 10, "pgid": 100, "command": "current test process"},
            {
                "pid": 200,
                "ppid": 1,
                "pgid": 200,
                "command": "cursor-sdk-bridge --workspace /tmp/quwoquan --tool-callback-url http://127.0.0.1:1/",
            },
        ],
    )

    conflicts = run_mod._managed_local_workspace_conflicts(workspace)

    assert [item["kind"] for item in conflicts] == ["cursor_sdk_bridge"]
    assert conflicts[0]["pid"] == 200


def test_managed_workspace_conflicts_ignores_foreign_cursor_bridge_under_repo_venv(monkeypatch):
    workspace = Path("/Users/zhaoyuxi/Projects/quwoquan")
    monkeypatch.setattr(run_mod, "_current_process_family_pids", lambda _rows=None: {100})
    monkeypatch.setattr(run_mod, "_process_cwd", lambda _pid: "/tmp/qwq_mfw_real_e2e_20260704")
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
                    "/Users/zhaoyuxi/Projects/quwoquan/quwoquan_data/.venv/lib/python3.13/site-packages/"
                    "cursor_sdk/_vendor/bridge/bin/cursor-sdk-bridge "
                    "--workspace /tmp/qwq_mfw_real_e2e_20260704/workspace_mfw_e2e_current "
                    "--tool-callback-url http://127.0.0.1:1/"
                ),
            },
        ],
    )

    assert run_mod._managed_local_workspace_conflicts(workspace) == []


def test_managed_workspace_conflicts_filters_foreign_data_cli(monkeypatch):
    workspace = Path("/tmp/quwoquan-a")
    monkeypatch.setattr(run_mod, "_current_process_family_pids", lambda _rows=None: {100})
    monkeypatch.setattr(
        run_mod,
        "_process_cwd",
        lambda pid: {
            200: "/tmp/quwoquan-a",
            300: "/tmp/quwoquan-b",
        }.get(pid, ""),
    )
    monkeypatch.setattr(
        run_mod,
        "_process_rows",
        lambda: [
            {"pid": 100, "ppid": 10, "pgid": 100, "command": "current test process"},
            {
                "pid": 200,
                "ppid": 1,
                "pgid": 200,
                "command": "python quwoquan_data/scripts/cli.py task run --task A --batch 1",
            },
            {
                "pid": 300,
                "ppid": 1,
                "pgid": 300,
                "command": "python quwoquan_data/scripts/cli.py task run --task B --batch 2",
            },
        ],
    )

    conflicts = run_mod._managed_local_workspace_conflicts(workspace)

    assert conflicts == [
        {
            "kind": "data_cli",
            "pid": 200,
            "ppid": 1,
            "pgid": 200,
            "cwd": "/tmp/quwoquan-a",
            "command": "python quwoquan_data/scripts/cli.py task run --task A --batch 1",
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
    old_key_file = os.environ.pop("QWQ_CURSOR_API_KEY_FILE", None)
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
        if old_key_file is not None:
            os.environ["QWQ_CURSOR_API_KEY_FILE"] = old_key_file
    assert "CURSOR_API_KEY missing" in issues
    assert not batch_root(task_id, "preflight_no_key").exists()

def test_managed_preflight_allows_cloud_runtime(monkeypatch):
    preflight_calls: list[dict] = []

    def _preflight(**kwargs):
        preflight_calls.append(dict(kwargs))
        return {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        }

    monkeypatch.setattr("_common.python_runtime.environment_preflight", _preflight)
    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", lambda _workspace: [])
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_cloud_runtime",
        spec,
        argparse.Namespace(
            runtime="cloud",
            baseline_packet="baseline.json",
            until=None,
            force_clean_workspace_agent_state=False,
            agent_provider="cursor_sdk",
            model="composer",
        ),
    )

    assert issues == []
    assert preflight_calls[-1]["require_cursor_key"] is True
    assert preflight_calls[-1]["check_cursor_cloud_api"] is True
    assert preflight_calls[-1]["check_cursor_startup"] is True
    assert preflight_calls[-1]["cursor_startup_model"] == "composer"
    assert preflight_calls[-1]["cursor_startup_runtime"] == "cloud"
    assert not batch_root(task_id, "preflight_cloud_runtime").exists()


def test_managed_preflight_allows_image_only_quota_without_article_or_homepage(monkeypatch):
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
    spec.setdefault("content", {})["carriers"] = ["image"]
    spec["content"].setdefault("research", {})["lanes"] = ["image"]
    spec["content"]["quotas"] = {
        "entityArticlesPerTarget": 0,
        "imageWorksPerTarget": 1,
        "entityHomepagesPerTarget": 0,
        "routeArticles": 0,
    }

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_image_only_quota",
        spec,
        argparse.Namespace(
            runtime="cloud",
            baseline_packet=None,
            until=None,
            agent_provider="cursor_sdk",
        ),
    )

    assert issues == []
    assert not batch_root(task_id, "preflight_image_only_quota").exists()


def test_managed_preflight_allows_homepage_only_quota_lanes(monkeypatch):
    monkeypatch.setenv("QWQ_HOMEPAGE_ONLY_EXECUTION_BRANCH", "feature/homepage-commercial-lane")
    monkeypatch.setattr(
        "_common.execution_branch.current_git_branch",
        lambda **_kwargs: "feature/homepage-commercial-lane",
    )
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
    spec.setdefault("content", {}).setdefault("research", {})["lanes"] = ["homepage"]
    spec["content"]["quotas"] = {
        "entityArticlesPerTarget": 0,
        "imageWorksPerTarget": 0,
        "entityHomepagesPerTarget": 1,
        "routeArticles": 0,
    }

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_homepage_only_quota",
        spec,
        argparse.Namespace(
            runtime="cloud",
            baseline_packet=None,
            until=None,
            agent_provider="cursor_sdk",
        ),
    )

    assert issues == []
    assert not batch_root(task_id, "preflight_homepage_only_quota").exists()


def test_managed_preflight_rejects_zero_content_quota(monkeypatch):
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
    spec["content"]["quotas"] = {
        "entityArticlesPerTarget": 0,
        "imageWorksPerTarget": 0,
        "entityHomepagesPerTarget": 0,
        "routeArticles": 0,
    }

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_zero_content_quota",
        spec,
        argparse.Namespace(
            runtime="cloud",
            baseline_packet=None,
            until=None,
            agent_provider="cursor_sdk",
        ),
    )

    assert any("at least one content quota must be >= 1" in issue for issue in issues)
    assert not batch_root(task_id, "preflight_zero_content_quota").exists()


def test_image_only_homepage_stages_are_deterministic_skips():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["content"]["carriers"] = ["image"]
    spec["content"]["quotas"] = {
        "entityArticlesPerTarget": 0,
        "imageWorksPerTarget": 1,
        "entityHomepagesPerTarget": 0,
        "routeArticles": 0,
    }
    store.save_spec(spec)
    ctx = _ctx(task_id, "image_only_homepage_skip")

    prepare = run_mod._run_build_prepare(ctx)
    homepage = run_mod._checkpoint_build_homepage(ctx)
    validate = run_mod._run_build_validate(ctx)

    assert prepare.status == "done"
    assert homepage.status == "done"
    assert validate.status == "done"
    assert "跳过主页" in prepare.message
    assert "无需主页" in homepage.message


def test_managed_preflight_retries_cloud_bridge_startup_once(monkeypatch):
    preflight_calls: list[dict] = []
    reports = iter(
        [
            {
                "schemaVersion": "quwoquan_data.env_preflight",
                "ready": False,
                "issues": ["Bridge request failed: ConnectError: [Errno 61] Connection refused"],
                "cursorStartup": {
                    "ready": False,
                    "status": "error",
                    "errorClass": "NetworkError",
                    "error": "Bridge request failed: ConnectError: [Errno 61] Connection refused",
                },
            },
            {
                "schemaVersion": "quwoquan_data.env_preflight",
                "ready": True,
                "issues": [],
                "cursorStartup": {
                    "ready": True,
                    "status": "finished",
                },
            },
        ]
    )

    def _preflight(**kwargs):
        preflight_calls.append(dict(kwargs))
        return dict(next(reports))

    monkeypatch.setattr("_common.python_runtime.environment_preflight", _preflight)
    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", lambda _workspace: [])
    monkeypatch.setenv("QWQ_MANAGED_PREFLIGHT_RETRY_DELAY_SECONDS", "0")
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"
    args = argparse.Namespace(
        runtime="cloud",
        baseline_packet="baseline.json",
        until=None,
        force_clean_workspace_agent_state=False,
        agent_provider="cursor_sdk",
        model="composer",
    )

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_cloud_bridge_retry",
        spec,
        args,
    )

    assert issues == []
    assert len(preflight_calls) == 2
    report = getattr(args, "_env_preflight_report")
    assert len(report["managedPreflightAttempts"]) == 2
    assert report["managedPreflightAttempts"][0]["cursorStartupErrorClass"] == "NetworkError"


def test_managed_preflight_local_cursor_runtime_runs_real_startup_probe(monkeypatch):
    preflight_calls: list[dict] = []

    def _preflight(**kwargs):
        preflight_calls.append(dict(kwargs))
        return {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
            "cursorStartup": {
                "ready": True,
                "status": "finished",
            },
        }

    monkeypatch.setattr("_common.python_runtime.environment_preflight", _preflight)
    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", lambda _workspace: [])
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_local_startup_gate",
        spec,
        argparse.Namespace(
            runtime="local",
            baseline_packet="baseline.json",
            until=None,
            force_clean_workspace_agent_state=False,
            agent_provider="cursor_sdk",
            model="composer",
        ),
    )

    assert issues == []
    assert len(preflight_calls) == 1
    assert preflight_calls[0]["check_cursor_cloud_api"] is True
    assert preflight_calls[0]["check_cursor_startup"] is True
    assert preflight_calls[0]["cursor_startup_runtime"] == "local"
    assert preflight_calls[0]["cursor_startup_model"] == "composer"


def test_managed_preflight_does_not_retry_cursor_auth_or_plan_blocker(monkeypatch):
    preflight_calls: list[dict] = []

    def _preflight(**kwargs):
        preflight_calls.append(dict(kwargs))
        return {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": False,
            "issues": ["plan_required: paid plan required"],
            "cursorStartup": {
                "ready": False,
                "status": "error",
                "errorClass": "CursorAgentError",
                "error": "plan_required: paid plan required",
            },
        }

    monkeypatch.setattr("_common.python_runtime.environment_preflight", _preflight)
    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", lambda _workspace: [])
    monkeypatch.setenv("QWQ_MANAGED_PREFLIGHT_RETRY_DELAY_SECONDS", "0")
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_cloud_plan_block",
        spec,
        argparse.Namespace(
            runtime="cloud",
            baseline_packet="baseline.json",
            until=None,
            force_clean_workspace_agent_state=False,
            agent_provider="cursor_sdk",
            model="composer",
        ),
    )

    assert len(preflight_calls) == 1
    assert issues == ["plan_required: paid plan required"]

def test_default_managed_agent_runner_uses_cloud_options(monkeypatch):
    import types

    captured: dict[str, object] = {}

    class _CursorAgentError(Exception):
        pass

    class _Client:
        @staticmethod
        def launch_bridge(**kwargs):
            captured["bridge"] = kwargs
            return types.SimpleNamespace(
                _owned_bridge=types.SimpleNamespace(endpoint=None, process=None),
                close=lambda: None,
            )

    class _Run:
        @staticmethod
        def events():
            return iter(())

        @staticmethod
        def wait():
            return types.SimpleNamespace(
                status="finished",
                result="READY",
                agent_id="agent-cloud",
                id="run-cloud",
                duration_ms=12,
            )

    class _Agent:
        # 新 SDK 契约：Agent.create(options, client=) -> send(prompt) -> events()/wait() -> close()
        @classmethod
        def create(cls, opts, client=None):  # noqa: ARG003
            captured["opts"] = opts
            return cls()

        def send(self, _prompt):  # noqa: ARG002
            return _Run()

        def close(self):
            pass

    def _AgentOptions(**kwargs):
        captured["agentOptions"] = kwargs
        return kwargs

    def _CloudAgentOptions(**kwargs):
        captured["cloudOptions"] = kwargs
        return ("cloud", kwargs)

    def _LocalAgentOptions(**kwargs):
        captured["localOptions"] = kwargs
        return ("local", kwargs)

    fake_cursor_sdk = types.SimpleNamespace(
        Agent=_Agent,
        AgentOptions=_AgentOptions,
        CloudAgentOptions=_CloudAgentOptions,
        Client=_Client,
        CursorAgentError=_CursorAgentError,
        LocalAgentOptions=_LocalAgentOptions,
    )
    monkeypatch.setitem(sys.modules, "cursor_sdk", fake_cursor_sdk)
    monkeypatch.setenv("CURSOR_API_KEY", "crsr_" + ("x" * 32))
    monkeypatch.setattr(run_mod, "_terminate_pid_tree_if_alive", lambda _pid: None)

    ctx = run_mod.PipelineContext(
        task_id="旅行/地域/测试省/景区/云端托管",
        batch_id="cloud_runtime",
        entity_ids=["测试景区甲"],
        spec={},
        managed=True,
        runtime="cloud",
        model="composer",
        agent_provider="cursor_sdk",
    )

    report = run_mod._default_managed_agent_runner(ctx, "probe")

    assert report["started"] is True
    assert report["status"] == "finished"
    assert captured["cloudOptions"] == {"repos": []}
    assert "localOptions" not in captured
    assert captured["agentOptions"]["cloud"] == ("cloud", {"repos": []})


def test_default_managed_agent_runner_extracts_cursor_usage(monkeypatch):
    captured: dict[str, object] = {}

    class _CursorAgentError(Exception):
        pass

    class _Client:
        @staticmethod
        def launch_bridge(**kwargs):
            captured["bridge"] = kwargs
            return types.SimpleNamespace(
                _owned_bridge=types.SimpleNamespace(endpoint=None, process=None),
                close=lambda: None,
            )

    class _Run:
        @staticmethod
        def events():
            return iter(())

        @staticmethod
        def wait():
            return types.SimpleNamespace(
                status="finished",
                result="READY",
                agent_id="agent-local",
                id="run-local",
                duration_ms=15,
                usage={"prompt_tokens": 120, "completion_tokens": 30, "cost_usd": 0.42},
            )

    class _Agent:
        @classmethod
        def create(cls, opts, client=None):  # noqa: ARG003
            captured["opts"] = opts
            return cls()

        def send(self, _prompt):  # noqa: ARG002
            return _Run()

        def close(self):
            pass

    def _AgentOptions(**kwargs):
        return kwargs

    def _CloudAgentOptions(**kwargs):
        return ("cloud", kwargs)

    def _LocalAgentOptions(**kwargs):
        return ("local", kwargs)

    fake_cursor_sdk = types.SimpleNamespace(
        Agent=_Agent,
        AgentOptions=_AgentOptions,
        CloudAgentOptions=_CloudAgentOptions,
        Client=_Client,
        CursorAgentError=_CursorAgentError,
        LocalAgentOptions=_LocalAgentOptions,
    )
    monkeypatch.setitem(sys.modules, "cursor_sdk", fake_cursor_sdk)
    monkeypatch.setenv("CURSOR_API_KEY", "crsr_" + ("x" * 32))
    monkeypatch.setattr(run_mod, "_terminate_pid_tree_if_alive", lambda _pid: None)

    ctx = run_mod.PipelineContext(
        task_id="旅行/地域/测试省/景区/本地用量提取",
        batch_id="local_usage_extract",
        entity_ids=["测试景区甲"],
        spec={},
        managed=True,
        runtime="local",
        model="composer",
        agent_provider="cursor_sdk",
    )

    report = run_mod._default_managed_agent_runner(ctx, "probe")

    assert report["started"] is True
    assert report["status"] == "finished"
    assert report["usedTokens"] == 150
    assert report["costUsd"] == 0.42
    assert report["usageMeasurementMode"] == "usage"


def test_default_managed_agent_runner_retries_on_same_warm_bridge(monkeypatch):
    captured = {"bridgeCalls": 0, "promptCalls": 0}

    class _CursorAgentError(Exception):
        def __init__(
            self,
            message: str,
            *,
            code: str = "internal",
            status: int = 500,
            is_retryable: bool = False,
        ) -> None:
            super().__init__(message)
            self.message = message
            self.code = code
            self.status = status
            self.is_retryable = is_retryable
            self.request_id = None

    class _Client:
        @staticmethod
        def launch_bridge(**kwargs):
            captured["bridgeCalls"] += 1
            captured["bridge"] = kwargs
            return types.SimpleNamespace(
                _owned_bridge=types.SimpleNamespace(endpoint=None, process=None),
                close=lambda: None,
            )

    class _Run:
        @staticmethod
        def events():
            return iter(())

        @staticmethod
        def wait():
            return types.SimpleNamespace(
                status="finished",
                result="READY",
                agent_id="agent-warm",
                id="run-warm",
                duration_ms=20,
                usage={"prompt_tokens": 10, "completion_tokens": 2, "cost_usd": 0.01},
            )

    class _Agent:
        @classmethod
        def create(cls, opts, client=None):  # noqa: ARG003
            captured["opts"] = opts
            return cls()

        def send(self, _prompt):  # noqa: ARG002
            captured["promptCalls"] += 1
            if int(captured["promptCalls"]) < 3:
                raise _CursorAgentError("internal error", code="internal", status=500)
            return _Run()

        def close(self):
            pass

    def _AgentOptions(**kwargs):
        return kwargs

    def _CloudAgentOptions(**kwargs):
        return ("cloud", kwargs)

    def _LocalAgentOptions(**kwargs):
        return ("local", kwargs)

    fake_cursor_sdk = types.SimpleNamespace(
        Agent=_Agent,
        AgentOptions=_AgentOptions,
        CloudAgentOptions=_CloudAgentOptions,
        Client=_Client,
        CursorAgentError=_CursorAgentError,
        LocalAgentOptions=_LocalAgentOptions,
    )
    monkeypatch.setitem(sys.modules, "cursor_sdk", fake_cursor_sdk)
    monkeypatch.setenv("CURSOR_API_KEY", "crsr_" + ("x" * 32))
    monkeypatch.setenv("QWQ_CURSOR_WARM_ATTEMPTS", "3")
    monkeypatch.setattr(run_mod, "_terminate_pid_tree_if_alive", lambda _pid: None)
    monkeypatch.setattr(run_mod.time, "sleep", lambda _secs: None)

    ctx = run_mod.PipelineContext(
        task_id="旅行/地域/测试省/景区/本地暖桥重试",
        batch_id="local_warm_bridge_retry",
        entity_ids=["测试景区甲"],
        spec={},
        managed=True,
        runtime="local",
        model="composer",
        agent_provider="cursor_sdk",
    )

    report = run_mod._default_managed_agent_runner(ctx, "probe")

    assert report["started"] is True
    assert report["status"] == "finished"
    assert report["usedTokens"] == 12
    assert report["costUsd"] == 0.01
    assert captured["bridgeCalls"] == 1
    assert captured["promptCalls"] == 3


def test_build_token_ledger_payload_prefers_managed_authoritative_usage():
    task_id = _make_task()
    batch_id = "managed_usage_ledger_batch"
    ctx = run_mod.PipelineContext(
        task_id=task_id,
        batch_id=batch_id,
        entity_ids=["测试景区甲"],
        spec={},
        managed=True,
        runtime="local",
        model="composer",
        agent_provider="cursor_sdk",
    )
    ledger = run_mod._build_token_ledger_payload(
        ctx,
        {
            "agentRunHistory": [
                {
                    "stage": "build_homepage",
                    "finishedAt": "2026-07-05T00:00:00Z",
                    "outcomes": [
                        {
                            "started": True,
                            "status": "finished",
                            "usedTokens": 321,
                            "costUsd": 1.23,
                            "usageMeasurementMode": "usage",
                            "jobIndex": 0,
                            "timing": {"finishedAt": "2026-07-05T00:00:00Z"},
                        }
                    ],
                }
            ]
        },
        estimated_entries=[
            {
                "jobId": "artifact:fixture",
                "usedTokens": 999,
                "costUsd": 0.0,
            }
        ],
        default_budget=12000,
    )

    assert ledger["measurementMode"] == "cursor_sdk_result_usage"
    assert ledger["summary"]["usedTokens"] == 321
    assert ledger["summary"]["costUsd"] == 1.23


def test_token_ledger_homepage_batch_estimates_from_entity_drafts_when_usage_unavailable():
    """homepage 批次 token_ledger 兜底计量契约（pilot entries=0 根因）。

    当前 Cursor SDK 本地 bridge 不回传 usage（result 无 usage 字段、事件流无
    turn-ended usage），outcomes 的 usedTokens 全为 0；homepage 实体又不在
    content refs 索引里。此时 ledger 不得为空账本：必须按实体 4.draft
    prompt/page 产物落 estimated 条目（measurementMode=estimated_from_artifacts）。
    """
    task_id = _make_task()
    batch_id = "homepage_ledger_estimated"
    ctx = run_mod.PipelineContext(
        task_id=task_id,
        batch_id=batch_id,
        entity_ids=["测试景区甲"],
        spec=store.load_spec(task_id),
        managed=True,
        runtime="local",
        model="composer",
        agent_provider="cursor_sdk",
    )
    entity = batch_root(task_id, batch_id) / "entities" / "地点" / "景区" / "测试景区甲"
    (entity / "4.draft").mkdir(parents=True, exist_ok=True)
    (entity / "page.md").write_text("# 测试景区甲\n\n主页正文段落，包含足够字符用于估算。", encoding="utf-8")
    (entity / "4.draft" / "prompt.md").write_text("请基于底稿轻润色生成实体主页三段结构。", encoding="utf-8")
    (entity / "4.draft" / "page.md").write_text("# 测试景区甲\n\n作者产出正文。", encoding="utf-8")
    write_json(entity / "_entity.json", {"label": "测试景区甲", "domain": "地点", "type": "景区"})
    # bridge 无 usage：outcomes 存在但 usedTokens=0、usageMeasurementMode 空。
    state = {
        "startedAt": store.now_iso(),
        "agentRunHistory": [
            {
                "stage": "build_homepage",
                "finishedAt": "2026-07-06T00:00:00Z",
                "outcomes": [
                    {
                        "started": True,
                        "status": "finished",
                        "usedTokens": 0,
                        "costUsd": 0.0,
                        "usageMeasurementMode": "",
                        "jobIndex": 0,
                        "timing": {"finishedAt": "2026-07-06T00:00:00Z"},
                    }
                ],
            }
        ],
    }

    run_mod._write_workflow_execution_metrics(ctx, state)

    ledger = read_json(batch_root(task_id, batch_id) / "_shared" / "token_ledger.json")
    assert ledger["measurementMode"] == "estimated_from_artifacts"
    assert ledger["summary"]["entryCount"] >= 1
    assert ledger["summary"]["usedTokens"] > 0
    job_ids = [str(entry.get("jobId") or "") for entry in ledger["entries"]]
    assert any("测试景区甲" in job_id for job_id in job_ids)
    # 4.draft 等 stage 子目录（含 page.md）不得被误判为实体重复入账。
    assert not any("4.draft" in job_id for job_id in job_ids)
    assert ledger["summary"]["entryCount"] == 1


def test_write_workflow_execution_metrics_counts_homepage_only_outputs():
    task_id = _make_task()
    batch_id = "homepage_only_metrics"
    ctx = run_mod.PipelineContext(
        task_id=task_id,
        batch_id=batch_id,
        entity_ids=["测试景区甲"],
        spec=store.load_spec(task_id),
        managed=True,
        runtime="local",
        model="composer",
        agent_provider="cursor_sdk",
        max_workers=3,
    )
    entity = batch_root(task_id, batch_id) / "entities" / "地点" / "景区" / "测试景区甲"
    (entity / "page.md").parent.mkdir(parents=True, exist_ok=True)
    (entity / "page.md").write_text("# 测试景区甲\n\n主页正文", encoding="utf-8")
    write_json(entity / "_entity.json", {"label": "测试景区甲", "domain": "地点", "type": "景区"})
    write_json(entity / "manifest.json", {"assets": []})
    write_json(entity / "4.draft" / "draft_meta.json", {"generator": "agent", "agentRunId": "run-home-1"})
    write_json(entity / "5.review" / "review.json", {"decision": "approved", "issues": []})
    write_json(
        entity / "5.review" / "finalization_report.json",
        {
            "schemaVersion": "quwoquan_data.finalization_report",
            "status": "passed",
            "draftArticleRef": "4.draft/page.md",
            "finalArticleRef": "page.md",
        },
    )
    state = {
        "startedAt": store.now_iso(),
        "agentRunHistory": [
            {
                "stage": "build_homepage",
                "plannedJobCount": 1,
                "finishedCount": 1,
                "infrastructureFailures": 0,
                "scheduler": {
                    "elapsedSeconds": 90,
                    "effectiveWorkerCount": 2,
                    "startedAt": "2026-07-05T00:00:00Z",
                },
                "finishedAt": "2026-07-05T00:01:30Z",
                "outcomes": [
                    {
                        "started": True,
                        "status": "finished",
                        "runId": "run-home-1",
                        "usedTokens": 210,
                        "costUsd": 0.42,
                        "usageMeasurementMode": "usage",
                        "jobIndex": 0,
                        "result": "**测试景区甲** checkpoint 已完成。",
                        "timing": {"finishedAt": "2026-07-05T00:01:30Z"},
                    }
                ],
            }
        ],
    }

    run_mod._write_workflow_execution_metrics(ctx, state)

    assert state["throughput"]["postCount"] == 0
    assert state["throughput"]["homepageCount"] == 1
    assert state["throughput"]["publishedObjectCount"] == 1
    assert state["throughput"]["objectsPerHour"] > 0
    assert state["throughput"]["agentActive"]["sourceStage"] == "build_homepage"
    assert state["quality"]["firstPassRate"] == 1.0
    assert state["quality"]["reviewedRefs"] == 1
    assert state["quality"]["repairedRefs"] == 0
    assert state["quality"]["homepageReviewedRefs"] == 1
    assert state["quality"]["homepageRepairedRefs"] == 0
    assert state["quality"]["homepageMeasurementMode"] == "build_homepage_agent_run_history"
    ledger = read_json(batch_root(task_id, batch_id) / "_shared" / "token_ledger.json")
    assert ledger["measurementMode"] == "cursor_sdk_result_usage"
    assert ledger["summary"]["usedTokens"] == 210


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

def test_managed_preflight_auto_reclaims_orphan_cursor_bridges(monkeypatch):
    """孤儿 bridge（ppid=1）无归属：未指定 force-clean 也必须自动回收，不 BLOCK。

    历史：pilot 批次 resume 循环被孤儿 cursor_sdk_bridge 反复 BLOCK 直至崩溃。
    """
    monkeypatch.setattr(
        "_common.python_runtime.environment_preflight",
        lambda **_kwargs: {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        },
    )
    cleanup_calls: list[list[dict]] = []
    orphan = {
        "kind": "cursor_sdk_bridge",
        "pid": 4242,
        "ppid": 1,
        "pgid": 4242,
        "command": "node cursor-sdk-bridge --workspace /tmp/quwoquan",
    }

    def _conflicts(_workspace):
        return [] if cleanup_calls else [dict(orphan)]

    def _cleanup(rows):
        cleanup_calls.append([dict(row) for row in rows])
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
        force_clean_workspace_agent_state=False,
    )

    issues = run_mod._managed_preflight(task_id, "preflight_orphan_bridge", spec, args)

    assert not any("managed local workspace has active" in issue for issue in issues)
    assert cleanup_calls and cleanup_calls[0][0]["pid"] == 4242
    report = getattr(args, "_managed_orphan_bridge_cleanup_report")
    assert report["mode"] == "auto_reclaimed_orphan_cursor_bridges"


def test_managed_preflight_does_not_auto_reclaim_owned_bridge(monkeypatch):
    """有活父进程的 bridge（ppid≠1）仍按既有冲突语义 BLOCK，防误杀他人任务。"""
    monkeypatch.setattr(
        "_common.python_runtime.environment_preflight",
        lambda **_kwargs: {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": True,
            "issues": [],
        },
    )
    owned = {
        "kind": "cursor_sdk_bridge",
        "pid": 4243,
        "ppid": 999,
        "pgid": 4243,
        "command": "node cursor-sdk-bridge --workspace /tmp/quwoquan",
    }
    monkeypatch.setattr(
        run_mod, "_managed_local_workspace_conflicts", lambda _workspace: [dict(owned)]
    )

    def _unexpected_cleanup(rows):
        raise AssertionError("有归属的 bridge 不得被自动回收")

    monkeypatch.setattr(run_mod, "_cleanup_managed_local_workspace_conflicts", _unexpected_cleanup)
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"

    issues = run_mod._managed_preflight(
        task_id,
        "preflight_owned_bridge",
        spec,
        argparse.Namespace(
            runtime="local",
            baseline_packet=None,
            until=None,
            force_clean_workspace_agent_state=False,
        ),
    )

    assert any("managed local workspace has active" in issue for issue in issues)


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


def test_cross_task_conflicts_include_foreign_managed_agent_worker():
    rows = [
        {
            "kind": "managed_agent_worker",
            "pid": 1234,
            "pgid": 1234,
            "command": (
                "python -c 'from task.run import _managed_agent_worker_main; _managed_agent_worker_main()' "
                "/tmp/input.json /tmp/output.json --qwq-task-id 其它任务 --qwq-batch-id other"
            ),
        },
        {
            "kind": "managed_agent_worker",
            "pid": 5678,
            "pgid": 5678,
            "command": (
                "python -c 'from task.run import _managed_agent_worker_main; _managed_agent_worker_main()' "
                "/tmp/input.json /tmp/output.json --qwq-task-id 旅行/地域/测试省/景区/多模态 --qwq-batch-id b1"
            ),
        },
    ]
    conflicts = run_mod._cross_task_managed_data_cli_conflicts(
        rows,
        task_id="旅行/地域/测试省/景区/多模态",
        batch_id="b1",
    )
    assert [item["pid"] for item in conflicts] == [1234]

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


def test_managed_preflight_allows_site_supply_dynamic_image_packet_with_image_lane(monkeypatch):
    from _common.content_object import write_brief_object
    from PIL import Image

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
        "lanes": ["image"],
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
    batch_id = "site_supply_dynamic_image_preflight"
    root = batch_root(task_id, batch_id)
    shared = root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "evidence.md").write_text("动态景区乙 Pinterest 图片候选证据。", encoding="utf-8")
    assets_dir = shared / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    asset_path = assets_dir / "001_dynamic_pinterest.jpg"
    Image.new("RGB", (960, 640), (80, 120, 180)).save(asset_path, format="JPEG")
    write_json(
        assets_dir / "index.json",
        {
            "assets": [
                {
                    "fileName": asset_path.name,
                    "sourceCollectionId": "pin_1234567890",
                }
            ]
        },
    )
    write_json(
        shared / "meta.json",
        {
            "schemaVersion": "quwoquan.source_meta",
            "researchLane": "image",
        },
    )
    ref = "candidate_dynamic_image_1"
    entity_ref = "/entity/地点/景区/动态景区乙"
    write_brief_object(
        task_id,
        batch_id,
        ref,
        {
            "schemaVersion": "quwoquan.compose.brief",
            "templateId": "景区_画报",
            "titleHint": "动态景区乙·Pinterest 来源画报",
            "entityRefs": [entity_ref],
            "evidenceRefs": ["_shared/evidence.md"],
            "writingIntent": "visual_editorial",
            "mustIncludeFacts": ["动态景区乙"],
        },
        content_type="image",
    )
    write_json(
        shared / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": batch_id,
            "generatedBy": "site_supply_content_plan_bridge",
            "sourceSite": {"vertical": "photography", "siteId": "pinterest", "batchId": "real_pin_100"},
            "items": [
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "image",
                    "researchLane": "image",
                    "title": "动态景区乙·Pinterest 来源画报",
                    "entityRefs": [entity_ref],
                    "evidenceRefs": ["_shared/evidence.md"],
                    "rationale": "site supply dynamic image packet target",
                    "caption": "Pinterest 公开图来源",
                    "assetRefs": ["_shared/assets/001_dynamic_pinterest.jpg"],
                    "sourceCollectionId": "pin_1234567890",
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


def _image_meta_payload(*, title: str | None, caption: str | None) -> dict:
    return {
        "generator": "image_evidence_pack",
        "title": title,
        "caption": caption,
        "creativePlan": {
            "concepts": ["plan_a", "plan_b"],
            "selectedPlanId": "plan_a",
            "selectionReason": "保真保留可用文本，噪声留空。",
        },
        "selfCritique": {field: "ok" for field in cb.SELF_CRITIQUE_FIELDS},
    }


def test_managed_image_meta_allows_empty_title_and_caption_for_platform_noise():
    issues = run_mod._managed_image_author_meta_issues(
        _image_meta_payload(title="", caption=""),
        writing_pack={
            "title": "Pins by you",
            "caption": "Discover your own Pins on Pinterest",
        },
        require_agent_run=False,
    )

    assert "draft_meta.title missing while source title exists" not in issues
    assert "draft_meta.caption missing while source caption exists" not in issues


def test_managed_image_meta_allows_empty_caption_when_source_caption_only_repeats_title():
    issues = run_mod._managed_image_author_meta_issues(
        _image_meta_payload(title="Travel · national parks", caption=""),
        writing_pack={
            "title": "Travel · national parks | HD National Parks Wallpaper - W",
            "caption": "national parks | HD National Parks Wallpaper - WallpaperSafari",
        },
        require_agent_run=False,
    )

    assert "draft_meta.caption missing while source caption exists" not in issues


def test_managed_image_meta_still_requires_real_semantic_caption():
    issues = run_mod._managed_image_author_meta_issues(
        _image_meta_payload(title="Waterfall in Dense Forest", caption=""),
        writing_pack={
            "title": "Waterfall in Dense Forest",
            "caption": "Mossy cliffs and falling water after rain",
        },
        require_agent_run=False,
    )

    assert "draft_meta.caption missing while source caption exists" in issues


def test_managed_image_meta_allows_multilingual_platform_prompt_caption_to_clear():
    issues = run_mod._managed_image_author_meta_issues(
        _image_meta_payload(title="Natura", caption=""),
        writing_pack={
            "title": "Natura",
            "caption": "Scopri (e salva) i tuoi Pin su Pinterest.",
        },
        require_agent_run=False,
    )

    assert "draft_meta.caption missing while source caption exists" not in issues


def test_managed_image_meta_allows_pin_by_title_to_clear():
    issues = run_mod._managed_image_author_meta_issues(
        _image_meta_payload(title="", caption=""),
        writing_pack={
            "title": "Pin by 🍍美月🍍 on 🌿🐯Fondos in 2026",
            "caption": "Apr 28, 2026 - This Pin was discovered by 🍍美月🍍. Discover (and save!) your own Pins on Pinterest",
        },
        require_agent_run=False,
    )

    assert "draft_meta.title missing while source title exists" not in issues
    assert "draft_meta.caption missing while source caption exists" not in issues


def test_managed_image_meta_allows_youtube_promo_caption_to_clear():
    issues = run_mod._managed_image_author_meta_issues(
        _image_meta_payload(title="Waterfall in Dense Forest", caption=""),
        writing_pack={
            "title": "Waterfall in Dense Forest",
            "caption": (
                "Hello, welcome to my YouTube channel."
                "This channel contains animated videos with entertaining content."
                "Each video clip on our channel will present stories in d..."
            ),
        },
        require_agent_run=False,
    )

    assert "draft_meta.caption missing while source caption exists" not in issues


def test_process_in_workspace_rejects_sibling_worktree_path_prefix():
    # /a/repo 不得命中兄弟 worktree /a/repo-wt-x 的进程（WP5 双省互杀实测回归）。
    from pathlib import Path

    ws = Path("/Users/zhaoyuxi/Projects/quwoquan")
    sibling_cmd = (
        "python cli.py task scaled-e2e run --cwd "
        "/Users/zhaoyuxi/Projects/quwoquan-wt-sichuan --model composer"
    )
    assert not run_mod._process_in_workspace(
        "/Users/zhaoyuxi/Projects/quwoquan-wt-sichuan", ws, sibling_cmd
    )

    same_cmd = (
        "python cli.py task scaled-e2e run --cwd "
        "/Users/zhaoyuxi/Projects/quwoquan --model composer"
    )
    assert run_mod._process_in_workspace("", ws, same_cmd)
    assert run_mod._process_in_workspace(
        "/Users/zhaoyuxi/Projects/quwoquan/quwoquan_data", ws, ""
    )
