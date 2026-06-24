from __future__ import annotations



from support.data_cli_fixtures import *  # noqa: F401,F403



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

