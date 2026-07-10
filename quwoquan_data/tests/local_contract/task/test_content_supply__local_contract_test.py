"""Content supply planning contracts.

Run directly:
  python3 quwoquan_data/tests/local_contract/task/test_content_supply__local_contract_test.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
_TMP = Path(tempfile.mkdtemp(prefix="content_supply_"))
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from task import content_supply as cs  # noqa: E402


def _spec(target: int = 100) -> dict:
    return cs.build_content_supply_task(
        supply_task_id=f"test_supply_{target}",
        goal="测试平台级内容供给",
        vertical="travel",
        scenarios=["cold_start", "long_tail_fill"],
        daily_content_target=target,
        content_mix=cs.parse_content_mix("article=0.5,imagePost=0.3,videoPost=0.2"),
        subject_kind="Entity",
        subject_type="地点/景区",
        subject_refs=["entity:地点:景区:九寨沟", "entity:地点:景区:黄龙"],
        plan_date="2026-06-14",
    )


def test_author_pool_is_three_times_daily_target():
    spec = _spec(100)
    assert spec["authorPool"]["size"] == 300
    assert spec["authorPool"]["dailyActiveAuthorTarget"] == 100
    assert spec["authorPool"]["domain"] == "CreatorProfile/SystemAuthor"
    assert spec["authorPool"]["identityPolicy"]["doNotMaterializeEachAuthorAsTagOrEntity"] is True
    assert spec["authorPool"]["disclosure"]["required"] is True
    assert spec["authorPool"]["publishIntervalDays"] == {"min": 1, "max": 5, "mean": 3}
    assert spec["creatorGovernance"]["tagEntityPolicy"]["doNotCreateTagPerAuthor"] is True
    assert spec["queuePolicy"]["backend"] == "local_file"
    assert spec["schemaVersion"] == "quwoquan.content_supply.task"
    assert spec["releasePolicy"]["publishRequiresReleaseVerify"] is True
    assert spec["tokenBudget"]["sopSummaryMaxTokens"] <= 500
    assert spec["tokenBudget"]["creatorProfileSummaryMaxTokens"] <= 300
    assert spec["planningContract"]["requiredBindings"] == [
        "verticalSopRef",
        "scenarioSopRef",
        "creatorProfileId",
        "contentSpecRef",
    ]
    assert spec["contentTargets"] == {"article": 50, "imagePost": 30, "videoPost": 20}


def test_prep_checks_reusable_sops():
    report = cs.build_prep_report(_spec(100))
    assert report["passed"], report
    assert "sop/scenarios/cold_start.md" in report["resolved"]["sopRefsChecked"]
    assert "sop/article.md" in report["resolved"]["sopRefsChecked"]
    assert report["resolved"]["queueBackend"] == "local_file"


def test_delta_plan_binds_every_sample_to_sop_creator_and_content_spec():
    plan = cs.build_delta_plan(_spec(100), sample_limit=20)
    assert plan["summary"]["generatedCount"] == 100
    assert plan["summary"]["authorPoolSize"] == 300
    assert sum(plan["authorPool"]["publishIntervalDistribution"].values()) == 300
    assert set(plan["authorPool"]["publishIntervalDistribution"]) == {"1", "2", "3", "4", "5"}
    author = plan["authorPool"]["sample"][0]
    assert author["status"] == "active"
    assert author["disclosure"]["visible"] is True
    assert author["claimPolicy"]["mayUseFirstPerson"] is False
    assert author["publishCadence"]["maxDailyPosts"] == 1
    assert len(plan["contentObjects"]["sample"]) == 20
    for obj in plan["contentObjects"]["sample"]:
        assert obj["verticalSopRef"]
        assert obj["scenarioSopRef"]
        assert obj["creatorProfileId"].startswith("agent_creator_")
        assert obj["authorId"].startswith("agent_author_")
        assert obj["creatorProfileVersion"] == "1.0.0"
        assert obj["creatorDisclosure"]["type"] == "platform_virtual_creator"
        assert obj["experienceClaimMode"] == "editorial_synthesis"
        assert obj["tokenBudget"]["creatorProfileSummaryMaxTokens"] <= 300
        assert obj["contentSpecRef"]
        assert "creator_boundary" in obj["qualityGateSet"]


def test_large_dry_run_is_lazy_sharded_not_fully_materialized():
    plan = cs.build_delta_plan(_spec(100_000), sample_limit=25)
    assert plan["summary"]["dailyContentTarget"] == 100_000
    assert plan["summary"]["authorPoolSize"] == 300_000
    assert len(plan["authorPool"]["sample"]) == 25
    assert len(plan["contentObjects"]["sample"]) == 25
    assert len(plan["authorPool"]["shards"]) == 300
    assert len(plan["contentObjects"]["shards"]) == 100
    assert plan["authorPool"]["materialization"] == "lazy_sharded"
    assert plan["queuePolicy"]["backend"] == "reliabletask"


def test_large_prep_requires_production_queue_backend():
    spec = _spec(2_000)
    spec["queuePolicy"]["backend"] = "local_file"
    report = cs.build_prep_report(spec, allow_missing_sop=True)
    assert not report["passed"]
    assert any("reliabletask" in issue for issue in report["blockingIssues"])


def test_prep_rejects_old_contract_task():
    spec = _spec(100)
    spec["schemaVersion"] = "legacy.quwoquan.content_supply.task"
    report = cs.build_prep_report(spec, allow_missing_sop=True)
    assert not report["passed"]
    assert any("old content supply tasks" in issue for issue in report["blockingIssues"])


def test_small_production_trial_can_force_reliabletask_backend():
    spec = cs.build_content_supply_task(
        supply_task_id="test_supply_reliabletask_small",
        goal="测试小批生产队列",
        vertical="travel",
        scenarios=["cold_start"],
        daily_content_target=600,
        content_mix=cs.parse_content_mix("homepage=100,article=400,imagePost=100"),
        subject_kind="Entity",
        subject_type="地点/景区",
        subject_refs=["entity:地点:景区:九寨沟"],
        plan_date="2026-06-14",
        queue_backend="reliabletask",
    )
    assert spec["queuePolicy"]["backend"] == "reliabletask"


def test_memory_skips_duplicate_semantic_fingerprint():
    base = cs.build_delta_plan(_spec(100), sample_limit=1)
    first = base["contentObjects"]["sample"][0]
    memory = {
        "existingObjectKeys": set(),
        "contentFingerprints": {first["semanticFingerprint"]},
        "usedBaseSourceRefs": set(),
    }
    plan = cs.build_delta_plan(_spec(100), memory=memory, sample_limit=5)
    assert plan["summary"]["skippedDuplicateCount"] == 1
    assert plan["summary"]["generatedCount"] == 99
    assert plan["contentObjects"]["skippedDuplicateSample"][0]["reason"] == "semantic_fingerprint"


def test_feedback_report_creates_revision_action():
    feedback_path = _TMP / "feedback.json"
    feedback_path.write_text(
        json.dumps(
            {
                "events": [
                    {"type": "report", "targetId": "content_001", "reason": "fact_error"},
                    {"type": "metric", "targetId": "content_002", "impressions": 1000, "ctr": 0.001},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    plan = cs.build_delta_plan(_spec(100), feedback_path=str(feedback_path), sample_limit=1)
    actions = plan["feedbackActions"]
    assert len(actions) == 2
    assert actions[0]["action"] == "freeze_and_repair"
    assert actions[0]["runMode"] == "repair_failed"
    assert actions[1]["action"] == "optimize_existing"


def test_cli_clarify_prep_plan_roundtrip():
    cli = SCRIPTS_ROOT / "cli.py"
    supply_task = "cli_supply_roundtrip"
    clarify = subprocess.run(
        [
            sys.executable,
            str(cli),
            "task",
            "clarify",
            "--supply-task",
            supply_task,
            "--goal",
            "CLI roundtrip",
            "--vertical",
            "travel",
            "--scenarios",
            "cold_start",
            "--daily-target",
            "100",
            "--subject-type",
            "地点/景区",
            "--subjects",
            "entity:地点:景区:九寨沟",
            "--write",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert clarify.returncode == 0, clarify.stderr
    payload = json.loads(clarify.stdout)
    assert payload["path"]

    prep = subprocess.run(
        [sys.executable, str(cli), "task", "prep", "--supply-task", supply_task, "--write"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert prep.returncode == 0, prep.stderr

    plan = subprocess.run(
        [
            sys.executable,
            str(cli),
            "task",
            "plan",
            "--supply-task",
            supply_task,
            "--sample-limit",
            "3",
            "--write",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert plan.returncode == 0, plan.stderr
    out = json.loads(plan.stdout)
    assert out["plan"]["summary"]["authorPoolSize"] == 300
    assert len(out["plan"]["contentObjects"]["sample"]) == 3


if __name__ == "__main__":
    test_author_pool_is_three_times_daily_target()
    test_prep_checks_reusable_sops()
    test_delta_plan_binds_every_sample_to_sop_creator_and_content_spec()
    test_large_dry_run_is_lazy_sharded_not_fully_materialized()
    test_large_prep_requires_production_queue_backend()
    test_prep_rejects_old_contract_task()
    test_small_production_trial_can_force_reliabletask_backend()
    test_memory_skips_duplicate_semantic_fingerprint()
    test_feedback_report_creates_revision_action()
    test_cli_clarify_prep_plan_roundtrip()
    print("content supply tests passed")
