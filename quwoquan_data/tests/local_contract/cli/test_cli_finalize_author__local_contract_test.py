from __future__ import annotations



from support.data_cli_fixtures import *  # noqa: F401,F403

from task import scaled_e2e as scaled_e2e_mod



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
    original_prepare = scaled_e2e_mod._prepare_author_jobs_for_paused_targets
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
        scaled_e2e_mod._prepare_author_jobs_for_paused_targets = _fake_prepare
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
        scaled_e2e_mod._prepare_author_jobs_for_paused_targets = original_prepare
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
    original_picker = scaled_e2e_mod._fanout_runner_python
    original_run = scaled_e2e_mod.subprocess.run
    try:
        scaled_e2e_mod._fanout_runner_python = lambda: "/tmp/.venv-fanout/bin/python"

        def _fake_run(argv, check=False):
            calls.append(list(argv))

            class _Result:
                returncode = 0

            return _Result()

        scaled_e2e_mod.subprocess.run = _fake_run
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
        scaled_e2e_mod._fanout_runner_python = original_picker
        scaled_e2e_mod.subprocess.run = original_run
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
