"""Post author evidence must bind one real output to the stable queue job."""
from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.agent.outcome import AgentRunOutcome  # noqa: E402
from content.execution.context import ExecutionContext  # noqa: E402
from content.execution.controller.post_author_evidence import (  # noqa: E402
    refresh_post_author_evidence_from_durable_meta,
    write_post_author_evidence,
)
from content.execution.controller.execute.handoff import build_author_job_packet  # noqa: E402
from content.execution.production_contracts import (  # noqa: E402
    sha256_file,
    validate_agent_result_envelope,
)
from content.execution.queue.core import _read_job, stable_job_id  # noqa: E402
from content.execution.queue.jobs import enqueue_ref_job  # noqa: E402
from content.execution.queue.reliabletask import worker as worker_module  # noqa: E402
from content.execution.queue.reliabletask.jobs import (  # noqa: E402
    post_author_job_definition,
)
from content.execution.queue.reliabletask.worker import (  # noqa: E402
    DataContentWorkItem,
    execute_work_item,
)
from content.execution.queue.reliabletask.fleet import build_fleet_request  # noqa: E402
from content.execution.queue.partition import partition_key  # noqa: E402
from content.post import object_index as content_object  # noqa: E402
from content.post.article.draft_io import (  # noqa: E402
    draft_article_path,
    draft_meta_path,
    draft_package_dir,
    write_prompt,
    write_writing_pack,
)
from content.templates.registry import TemplateRegistry  # noqa: E402
from governance.creators.assignment import creator_profile_digest  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from core.control_types import (  # noqa: E402
    AgentProvider,
    QueueBackend,
    QueueJobStage,
    QueueJobState,
)
from core.paths import OUTPUT_ROOT, execution_root  # noqa: E402
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402


def test_process_worker_keeps_stdout_protocol_clean(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    execution_id = "20260728--travel-article-golden--test-region-a--pilot-099"
    item = {
        "runtimeTaskId": "runtime-task-001",
        "jobId": "job-001",
        "executionId": execution_id,
        "ref": "posts/article/真实文章",
        "stage": "author",
        "partitionKey": "entity/真实地点",
        "entityRef": "entity/真实地点",
        "carrier": "article",
        "sourceRevision": "sha256:" + "a" * 64,
        "idempotencyKey": "entity/真实地点|article|source|author",
        "jobSetEnvelopeDigest": "sha256:" + "b" * 64,
        "jobSetDigest": "sha256:" + "c" * 64,
        "actualTaskDigest": "sha256:" + "c" * 64,
        "maxAttempts": 3,
    }
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "schema": "quwoquan.data_content_worker_request",
                    "item": item,
                }
            )
        ),
    )

    def execute(_item: DataContentWorkItem) -> dict[str, object]:
        print("managed agent progress")
        return {
            "executionId": execution_id,
            "jobId": "job-001",
            "resultEnvelopeRef": "data/tasks/result.json",
            "acceptanceClass": "stage_completed",
            "completedAt": "2026-08-07T11:30:00Z",
        }

    monkeypatch.setattr(worker_module, "execute_work_item", execute)

    worker_module.run_process_worker()

    captured = capsys.readouterr()
    response = json.loads(captured.out)
    assert response["schema"] == "quwoquan.data_content_worker_response"
    assert "managed agent progress" not in captured.out
    assert "managed agent progress" in captured.err


def test_fleet_request_rejects_carrier_different_from_execution_identity() -> None:
    execution_id = "20260728--travel-article-golden--test-region-a--pilot-099"
    shutil.rmtree(execution_root(execution_id), ignore_errors=True)
    try:
        ExecutionFixtureBuilder(execution_id).build()
        enqueue_ref_job(
            execution_id,
            "/entity/地点/景区/测试实体甲",
            QueueJobStage.AUTHOR,
            mutex_key="/entity/地点/景区/测试实体甲",
            queue_backend=QueueBackend.RELIABLE_TASK,
            meta={
                "contentType": "homepage",
                "carrier": "homepage",
                "entityRef": "/entity/地点/景区/测试实体甲",
                "sourceRevision": "sha256:" + ("a" * 64),
                "contentObjectDir": "entities/地点/景区/测试实体甲",
            },
        )

        with pytest.raises(ValueError, match="carrier 必须与 executionId 一致"):
            build_fleet_request(execution_id, QueueJobStage.AUTHOR)
    finally:
        shutil.rmtree(execution_root(execution_id), ignore_errors=True)

EXECUTION_ID = (
    "20260720--travel-article-reliabletask-evidence--"
    "test-region-b--pilot-901"
)
HIGHLAND_CREATOR_PROFILE_DIGEST = creator_profile_digest(
    TemplateRegistry.load().creators["qwq_creator_highland_travel_blogger_001"]
)


def test_post_author_evidence_binds_output_and_stable_job(monkeypatch) -> None:
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(EXECUTION_ID)
    fixture.build()
    ref = "article-source-unit-001"
    brief = {
        "titleHint": "都江堰行前安排",
        "carrier": "article",
        "writingIntent": "planning_consultation",
        "entityRefs": ["/entity/地点/景区/都江堰"],
    }
    content_object.write_brief_object(
        EXECUTION_ID,
        ref,
        brief,
        content_type="article",
    )
    writing_pack = {
        **brief,
        "baseSourceRef": "source-unit-001",
        "sourcePaths": [],
        "sourceUrls": ["https://example.com/dujiangyan"],
        "assets": [],
    }
    write_writing_pack(EXECUTION_ID, ref, writing_pack)
    prompt = write_prompt(
        EXECUTION_ID,
        ref,
        "依据冻结底稿创作都江堰行前安排，不得虚构。",
    )
    packet = build_author_job_packet(
        execution_id=EXECUTION_ID,
        ref=ref,
        brief=brief,
        writing_pack=writing_pack,
        prompt_rel="4.draft/prompt.md",
        content_object_rel=content_object.content_object_rel(EXECUTION_ID, ref),
    )
    write_json(
        draft_package_dir(EXECUTION_ID, ref) / "author_job_packet.json",
        packet,
    )
    article = draft_article_path(EXECUTION_ID, ref)
    article.write_text(
        "# 都江堰行前安排\n\n"
        "都江堰位于岷江上游，出发前应核对开放时间与交通接驳。"
        "游览时按离堆公园、宝瓶口和鱼嘴的顺序理解水利工程关系。",
        encoding="utf-8",
    )
    write_json(
        draft_meta_path(EXECUTION_ID, ref),
        {
            "executionId": EXECUTION_ID,
            "objectRef": ref,
            "ref": ref,
            "generator": "agent",
            "status": "completed",
            "provider": "cursor_sdk",
            "model": "Composer",
            "agentRunId": "cursor-run-post-001",
            "agentId": "agent-post-001",
            "promptSha256": sha256_file(prompt),
            "draftSha256": sha256_file(article),
        },
    )
    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=("测试实体",),
        spec=fixture.spec(),
        managed=True,
        runtime="local",
        max_workers=1,
        model="composer-2.5",
        agent_provider="cursor_sdk",
    )
    mutex_key, retry_metadata = post_author_job_definition(ctx, ref)
    assert mutex_key == "source-unit-001"
    assert retry_metadata["carrier"] == "article"
    assert retry_metadata["entityRef"] == "/entity/地点/景区/都江堰"
    assert str(retry_metadata["sourceRevision"]).startswith("sha256:")
    initial_source_revision = retry_metadata["sourceRevision"]
    repair_report = (
        draft_package_dir(EXECUTION_ID, ref).parent
        / "5.review"
        / "repair_report.json"
    )
    write_json(repair_report, {"issues": ["修复图文锚点"]})
    _, repaired_metadata = post_author_job_definition(ctx, ref)
    assert repaired_metadata["sourceRevision"] != initial_source_revision
    prompt.write_text(
        prompt.read_text(encoding="utf-8") + "\n补充修订后的图文锚点。",
        encoding="utf-8",
    )
    _, reprompted_metadata = post_author_job_definition(ctx, ref)
    assert reprompted_metadata["sourceRevision"] != repaired_metadata["sourceRevision"]
    envelope_path = write_post_author_evidence(
        ctx,
        ref=ref,
        outcome=AgentRunOutcome.finished(
            provider=AgentProvider.CURSOR_SDK,
            run_id="cursor-run-post-001",
            agent_id="agent-post-001",
        ),
    )
    envelope = read_json(envelope_path)
    assert envelope["jobId"] == stable_job_id(EXECUTION_ID, ref, "author")
    assert envelope["ref"] == ref
    assert envelope["stage"] == "author"
    assert envelope["agent"]["runId"] == "cursor-run-post-001"
    assert envelope["agent"]["model"] == "composer-2.5"
    assert validate_agent_result_envelope(
        envelope,
        workspace_root=envelope_path.parent,
    ) == []
    article.write_text(
        article.read_text(encoding="utf-8") + "\n\n出发前再核对当日公告。",
        encoding="utf-8",
    )
    durable_meta = read_json(draft_meta_path(EXECUTION_ID, ref))
    durable_meta["draftSha256"] = sha256_file(article)
    durable_meta["model"] = "composer-2.5"
    write_json(draft_meta_path(EXECUTION_ID, ref), durable_meta)
    refresh_post_author_evidence_from_durable_meta(ctx, ref=ref)
    refreshed = read_json(envelope_path)
    assert refreshed["files"][0]["sha256"] == sha256_file(article)
    assert validate_agent_result_envelope(
        refreshed,
        workspace_root=envelope_path.parent,
    ) == []
    job = enqueue_ref_job(
        EXECUTION_ID,
        ref,
        "author",
        mutex_key="source-unit-001",
        meta={
            "contentType": "article",
            "carrier": "article",
            "entityRef": "/entity/地点/景区/都江堰",
            "sourceRevision": "sha256:" + ("1" * 64),
            "sourceUnitId": "source-unit-001",
            "contentObjectDir": content_object.content_object_rel(
                EXECUTION_ID,
                ref,
            ),
            "authorId": "builtin_highland_travel_blogger",
            "creatorProfileId": "qwq_creator_highland_travel_blogger_001",
            "creatorArchetype": "travel_blogger",
            "creatorProfileDigest": HIGHLAND_CREATOR_PROFILE_DIGEST,
            "creatorDisclosure": {
                "type": "platform_virtual_creator",
                "displayText": "平台虚拟创作者，内容由资料整理与 AI 辅助生成，经平台审核发布。",
                "visible": True,
            },
            "experienceClaimMode": "editorial_synthesis",
            "authorQualitySignals": {
                "qualityScore": 0.86,
                "fatigueScore": 0.2,
                "riskTier": "low",
            },
        },
        queue_backend=QueueBackend.RELIABLE_TASK,
    )
    reliable_ref = job.reliable_task_ref_document()
    assert reliable_ref is not None
    payload = reliable_ref["payload"]
    assert isinstance(payload, dict)
    author_request = build_fleet_request(
        EXECUTION_ID,
        QueueJobStage.AUTHOR,
    )
    assert author_request["requireCommercial"] is False
    assert payload["partitionKey"] == "source-unit-001"
    assert author_request["jobs"] == [
        {
            "entityRef": "/entity/地点/景区/都江堰",
                "carrier": "article",
                "sourceRevision": "sha256:" + ("1" * 64),
                "idempotencyKey": payload["idempotencyKey"],
                "jobId": job.job_id,
            "executionId": EXECUTION_ID,
                "ref": ref,
                "stage": "author",
                "partitionKey": partition_key("article", ref, 16),
                "maxAttempts": job.max_attempts,
            }
        ]
    result = execute_work_item(
        DataContentWorkItem.from_document(
            {
                "runtimeTaskId": "reliabletask-runtime-001",
                "jobSetEnvelopeDigest": author_request["jobSetEnvelopeDigest"],
                "jobSetDigest": author_request["jobSetDigest"],
                "actualTaskDigest": author_request["actualTaskDigest"],
                **author_request["jobs"][0],
            }
        )
    )
    completed = _read_job(EXECUTION_ID, job.job_id)
    assert completed.state is QueueJobState.SUCCEEDED
    assert completed.agent_run_id == "cursor-run-post-001"
    assert result["acceptanceClass"] == "stage_completed"
    assert result["resultEnvelopeRef"] == envelope_path.relative_to(
        OUTPUT_ROOT
    ).as_posix()
    apply_report = (
        OUTPUT_ROOT
        / "data/local/workspace/object-transactions"
        / "post-worker-transaction-001"
        / "apply_report.json"
    )
    write_json(
        apply_report,
        {
            "schema": "quwoquan_data.object_transaction_apply",
            "status": "applied",
            "executionId": EXECUTION_ID,
            "transactionId": "post-worker-transaction-001",
        },
    )

    def fake_promote_post_object(
        execution_id: str,
        post_ref: str,
        *,
        pool_delivery_intent: dict[str, object] | None = None,
    ) -> dict[str, str]:
        assert execution_id == EXECUTION_ID
        assert post_ref == content_object.content_object_rel(EXECUTION_ID, ref)
        assert pool_delivery_intent is not None
        return {
            "transactionId": "post-worker-transaction-001",
            "applyReportRef": apply_report.relative_to(OUTPUT_ROOT).as_posix(),
            "canonicalObjectRef": "posts/article/行前安排/都江堰/1",
            "canonicalObjectSha256": "sha256:" + ("2" * 64),
            "objectClosureDigest": "sha256:" + ("3" * 64),
        }

    from content.release.canonical import post_promotion

    monkeypatch.setattr(
        post_promotion,
        "promote_post_object",
        fake_promote_post_object,
    )
    # publish 阶段绑定 pool delivery preflight receipt；本测试关注 author
    # evidence 与 job 绑定，preflight 面由对象级替身提供最小 receipt。
    from content.execution.preflight import pool_delivery as delivery_preflight
    from content.execution.workspace import execution_root as _execution_root

    synthetic_receipt = {
        "receiptId": "sha256:" + "4" * 64,
        "evidenceDigest": "sha256:" + "5" * 64,
        "transportDigest": "sha256:" + "6" * 64,
        "deliveryGeneration": 1,
        "deliveryFencingToken": "sha256:" + "7" * 64,
        "workerRef": "data/local/cache/worker/data-content-worker",
        "workerSha256": "sha256:" + "8" * 64,
        "campaignBinding": None,
    }
    monkeypatch.setattr(
        delivery_preflight,
        "load_current_pool_delivery_preflight_receipt",
        lambda _execution_id: (
            synthetic_receipt,
            _execution_root(EXECUTION_ID)
            / "preflight/pool-delivery/receipt.json",
        ),
    )
    # publish 执行只消费 reviewed pool delivery intent；本测试的交付物是
    # author evidence 与 job 绑定，intent 校验由对象级替身给出最小结果。
    from content.execution.queue.reliabletask import publish as reliabletask_publish

    monkeypatch.setattr(
        reliabletask_publish,
        "validate_pool_delivery_intent_for_job",
        lambda _job: {
            "intentId": "sha256:" + "9" * 64,
            "transactionId": "post-worker-transaction-001",
            "executionId": EXECUTION_ID,
            "carrier": "article",
            "objectRef": ref,
        },
    )
    publish_job = enqueue_ref_job(
        EXECUTION_ID,
        ref,
        "publish",
        mutex_key="canonical-publish",
        meta={
            "contentType": "article",
            "carrier": "article",
            "entityRef": "/entity/地点/景区/都江堰",
            "sourceRevision": "sha256:" + ("4" * 64),
            "contentObjectDir": content_object.content_object_rel(
                EXECUTION_ID,
                ref,
            ),
        },
        queue_backend=QueueBackend.RELIABLE_TASK,
    )
    publish_reliable_ref = publish_job.reliable_task_ref_document()
    assert publish_reliable_ref is not None
    publish_payload = publish_reliable_ref["payload"]
    assert isinstance(publish_payload, dict)
    publish_request = build_fleet_request(
        EXECUTION_ID,
        QueueJobStage.PUBLISH,
    )
    assert publish_request["requireCommercial"] is False
    assert publish_payload["partitionKey"] == "canonical-publish"
    assert publish_request["jobs"] == [
        {
            "entityRef": "/entity/地点/景区/都江堰",
                "carrier": "article",
                "sourceRevision": "sha256:" + ("4" * 64),
                "idempotencyKey": publish_payload["idempotencyKey"],
                "jobId": publish_job.job_id,
            "executionId": EXECUTION_ID,
                "ref": ref,
                "stage": "publish",
                "partitionKey": partition_key("article", ref, 16),
                "maxAttempts": publish_job.max_attempts,
            }
        ]
    publish_result = execute_work_item(
        DataContentWorkItem.from_document(
            {
                "runtimeTaskId": "reliabletask-runtime-publish-001",
                "jobSetEnvelopeDigest": publish_request["jobSetEnvelopeDigest"],
                "jobSetDigest": publish_request["jobSetDigest"],
                "actualTaskDigest": publish_request["actualTaskDigest"],
                **publish_request["jobs"][0],
            }
        )
    )
    completed_publish = _read_job(EXECUTION_ID, publish_job.job_id)
    assert completed_publish.state is QueueJobState.SUCCEEDED
    assert publish_result["acceptanceClass"] == "canonical_pool"
    assert publish_result["objectTransactionId"] == "post-worker-transaction-001"
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    shutil.rmtree(apply_report.parents[0], ignore_errors=True)
