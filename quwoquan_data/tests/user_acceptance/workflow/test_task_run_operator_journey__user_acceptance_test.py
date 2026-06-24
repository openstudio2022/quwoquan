from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_first_run_pauses_at_download_plan():
    task_id = _make_task()
    code = run_mod.run_pipeline(_ctx(task_id, "b1"))
    assert code == 10, f"expected pause(10), got {code}"
    state = run_mod.load_workflow_state(task_id, "b1")
    assert state["waitingCheckpoint"] == "download_plan"
    assert "download_fetch" not in state["completed"]

def test_resume_advances_after_source_plan():
    task_id = _make_task()
    run_mod.run_pipeline(_ctx(task_id, "b2"))  # pause at download_plan
    _seed_source_plan(task_id, "b2")
    ctx = _ctx(task_id, "b2")
    ctx.until = "build_prepare"
    code = _run_pipeline_with_fake_download(ctx)  # resume
    assert code == 0, f"expected stopped-at-until success(0), got {code}"
    state = run_mod.load_workflow_state(task_id, "b2")
    # download_plan/fetch/build_prepare 应已完成，并在 build_prepare 截止点停住。
    assert "download_plan" in state["completed"]
    assert "download_fetch" in state["completed"]
    assert "build_prepare" in state["completed"]
    assert "build_homepage" not in state["completed"]
    assert state["status"] == "stopped_at_until"
    assert state["stoppedAtStage"] == "build_prepare"

def test_until_stops_early():
    task_id = _make_task()
    run_mod.run_pipeline(_ctx(task_id, "b3"))
    _seed_source_plan(task_id, "b3")
    ctx = _ctx(task_id, "b3")
    ctx.until = "download_fetch"
    code = _run_pipeline_with_fake_download(ctx)
    assert code == 0, f"expected clean stop(0) at --until, got {code}"
    state = run_mod.load_workflow_state(task_id, "b3")
    assert "download_fetch" in state["completed"]
    assert "build_homepage" not in state["completed"]
    assert state["status"] == "stopped_at_until"
    assert state["stoppedAtStage"] == "download_fetch"

def test_until_completed_checkpoint_stops_without_downstream(monkeypatch):
    task_id = _make_task()
    batch_id = "until_completed_download_plan"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["completed"] = ["download_plan"]
    run_mod.save_workflow_state(state)
    ctx.until = "download_plan"

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (True, []))
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda _ctx, entity_ids: [])

    code = run_mod.run_pipeline(ctx)

    assert code == 0
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "stopped_at_until"
    assert state["stoppedAtStage"] == "download_plan"
    assert "download_fetch" not in state["completed"]

def test_until_completed_checkpoint_revalidates_before_downstream(monkeypatch):
    task_id = _make_task()
    batch_id = "until_revalidate_download_plan"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["completed"] = ["download_plan"]
    run_mod.save_workflow_state(state)
    ctx.until = "download_plan"

    monkeypatch.setattr(
        "task.run._source_plan_filled",
        lambda _ctx: (False, ["article sources=1 need>=2"]),
    )
    monkeypatch.setenv("QWQ_DOWNLOAD_AUTO_RESEARCH", "0")

    code = run_mod.run_pipeline(ctx)

    assert code == 10
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["waitingCheckpoint"] == "download_plan"
    assert "download_plan" not in state["completed"]
    assert "download_fetch" not in state["completed"]
    assert any("article sources=0 need>=2" in item for item in state["failedObjects"])
    assert not any("article sources=1 need>=2" in item for item in state["failedObjects"])

