#!/usr/bin/env python3
"""Fast production-closure gate for content supply infrastructure.

This gate deliberately checks contracts and controller behavior, not content
quality. It is the cheap preflight that prevents scale runs from entering a
legacy local-only path.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT / "quwoquan_data"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

_TMP = Path(tempfile.mkdtemp(prefix="qwq_prod_gate_"))
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")

from _common import paths as _paths  # noqa: E402

_paths.RUNTIME_ROOT = Path(os.environ["QWQ_RUNTIME_ROOT"])
_paths.TASKS_ROOT = _paths.RUNTIME_ROOT / "tasks"
_paths.COMMITTED_TASKS_ROOT = Path(os.environ["QWQ_COMMITTED_TASKS_ROOT"])

from _common.io import read_json, write_json  # noqa: E402
from _common.paths import batch_root  # noqa: E402
from task import content_supply as cs  # noqa: E402
from task import object_queue as oq  # noqa: E402
from task import production_contracts as pc  # noqa: E402


REQUIRED_SCHEMAS = [
    DATA_ROOT / "schema/task/content_supply_task.schema.json",
    DATA_ROOT / "schema/task/object_job.schema.json",
    DATA_ROOT / "schema/task/agent_result_envelope.schema.json",
    DATA_ROOT / "schema/task/gate_verdict.schema.json",
    DATA_ROOT / "schema/task/token_ledger.schema.json",
]


def fail(message: str) -> None:
    print(f"[content-supply-production] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def _spec(target: int) -> dict:
    return cs.build_content_supply_task(
        supply_task_id=f"prod_gate_{target}",
        goal="production closure gate",
        vertical="travel",
        scenarios=["cold_start"],
        daily_content_target=target,
        content_mix=cs.parse_content_mix("article=0.5,imagePost=0.3,videoPost=0.2"),
        subject_kind="Entity",
        subject_type="地点/景区",
        subject_refs=["entity:地点:景区:九寨沟"],
        plan_date="2026-06-14",
    )


def _creator_meta() -> dict:
    return {
        "authorId": "builtin_travel_blogger_chuanxi",
        "creatorProfileId": "qwq_creator_travel_blogger_chuanxi_001",
        "creatorArchetype": "travel_blogger",
        "creatorProfileVersion": "1.0.0",
        "creatorDisclosure": {
            "type": "platform_virtual_creator",
            "displayText": "平台虚拟创作者，内容由资料整理与 AI 辅助生成，经平台审核发布。",
            "visible": True,
        },
        "experienceClaimMode": "editorial_synthesis",
        "authorQualitySignals": {"qualityScore": 0.86, "fatigueScore": 0.2, "riskTier": "low"},
    }


def verify_schemas_exist() -> None:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_SCHEMAS if not path.is_file()]
    _assert(not missing, f"missing schemas: {missing}")
    schema = read_json(DATA_ROOT / "schema/task/content_supply_task.schema.json")
    _assert((schema.get("properties") or {}).get("schemaVersion", {}).get("const") == cs.TASK_SCHEMA, "content_supply schema is not current")


def verify_content_supply_contract() -> None:
    small = _spec(300)
    large = _spec(100_000)
    _assert(small["schemaVersion"] == "quwoquan.content_supply.task", "small task must be current")
    _assert(small["queuePolicy"]["backend"] == "local_file", "small task should default to local_file")
    _assert(large["queuePolicy"]["backend"] == "reliabletask", "large task must default to reliabletask")
    _assert(large["releasePolicy"]["publishRequiresReleaseVerify"] is True, "release verify must be required")
    legacy = dict(small)
    legacy["schemaVersion"] = "legacy.quwoquan.content_supply.task"
    report = cs.build_prep_report(legacy, allow_missing_sop=True)
    _assert(not report["passed"], "old task must be rejected by prep")
    _assert(any("old content supply tasks" in issue for issue in report["blockingIssues"]), "old rejection must be explicit")


def verify_queue_and_envelope() -> None:
    task = "测试/生产闭环/任务"
    batch = "prod_gate_batch"
    job = oq.enqueue_ref_job(
        task,
        batch,
        "content_ref_001",
        "author",
        queue_backend="reliabletask",
        meta={
            "authorId": "builtin_travel_blogger",
            "creatorProfileId": "qwq_creator_travel_blogger_001",
            "creatorArchetype": "travel_blogger",
            "creatorProfileVersion": "1.0.0",
            "creatorDisclosure": {
                "type": "platform_virtual_creator",
                "displayText": "平台虚拟创作者，内容由资料整理与 AI 辅助生成，经平台审核发布。",
                "visible": True,
            },
            "experienceClaimMode": "editorial_synthesis",
            "authorQualitySignals": {"qualityScore": 0.85, "fatigueScore": 0.2, "riskTier": "low"},
            "contentType": "article",
        },
    )
    _assert(job["schemaVersion"] == pc.OBJECT_JOB_SCHEMA, "object job must be current")
    _assert(job["queueBackend"] == "reliabletask", "job must carry reliabletask backend")
    _assert(job["reliableTaskRef"]["queue"] == "reliabletask.data.content_supply", "job must carry reliabletask queue ref")
    leased = oq.acquire_lease(task, batch, worker="prod-gate", stage="author")
    _assert(leased is not None, "job should lease")
    packet = oq.build_lease_packet(leased)
    _assert(packet["resultEnvelopeRequired"] is True, "reliabletask job must require envelope")
    try:
        oq.complete_job(task, batch, leased["jobId"], leased["lease"])
    except RuntimeError as exc:
        _assert("result envelope required" in str(exc), "plain complete must be blocked when envelope is required")
    else:
        fail("plain complete unexpectedly succeeded")

    root = batch_root(task, batch)
    output = root / "posts/article/demo.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("# demo\n\n有证据的正文。", encoding="utf-8")
    digest = pc.sha256_file(output)
    gate = pc.build_gate_verdict(gate_id="review", decision="passed", input_hash=digest, output_hash=digest)
    envelope = pc.build_agent_result_envelope(
        job=leased,
        files=[{"path": "posts/article/demo.md", "sha256": digest, "role": "draft"}],
        gates=[gate],
        agent_id="fake-agent",
        run_id="fake-run",
    )
    envelope_path = root / "_shared" / "agent_result_envelope.json"
    write_json(envelope_path, envelope)
    completed = oq.complete_job_with_envelope(
        task,
        batch,
        leased["jobId"],
        leased["lease"],
        envelope_path=envelope_path,
        workspace_root=root,
    )
    _assert(completed["state"] == oq.STATE_SUCCEEDED, "valid envelope should complete job")
    _assert(completed["resultEnvelopeRef"].endswith("agent_result_envelope.json"), "job should store envelope ref")


def verify_token_ledger() -> None:
    entry = pc.build_token_ledger_entry(
        supply_task_id="supply_prod",
        batch_id="batch",
        job_id="job",
        creator_profile_id="creator",
        content_type="article",
        budget_tokens=100,
        used_tokens=120,
        cache_hits={"sop": True},
    )
    issues = pc.validate_token_ledger_entry(entry)
    _assert(not issues, f"token ledger should validate: {issues}")
    _assert(entry["budgetExceeded"] is True, "token ledger must mark budgetExceeded")


def main() -> None:
    verify_schemas_exist()
    verify_content_supply_contract()
    verify_queue_and_envelope()
    verify_token_ledger()
    print(json.dumps({"passed": True, "gate": "content_supply_production"}, ensure_ascii=False))
