"""Object queue lease packet projection for Subagent workers."""
from __future__ import annotations

from typing import Any

from core.control_types import ContentType
from content.execution import production_contracts as pc
from content.execution.queue.core import (
    DEFAULT_TOOL_PERMISSIONS,
)
from content.execution.queue.model import QueueJob

def build_lease_packet(job: QueueJob) -> dict[str, Any]:
    """把租到的 job 转成 Subagent 可直接消费的 handoff packet（含 Ralph 自纠环出口约束）。"""
    meta = job.metadata_document()
    content_type = job.content_type.value if job.content_type else ""
    carrier = job.carrier.value if job.carrier else ""
    is_image = ContentType.IMAGE in {job.content_type, job.carrier}
    is_video = ContentType.VIDEO in {job.content_type, job.carrier}
    object_packet_refs = {
        "contentObjectDir": job.content_object_dir or None,
        "authorJobPacket": "4.draft/author_job_packet.json",
        "writingPack": "3.compose/writing_pack.json",
        "draftMeta": "4.draft/draft_meta.json",
        "selfCheck": "4.draft/author_self_check.json",
    }
    if is_video:
        object_packet_refs["videoScript"] = "4.draft/video_script.json"
    elif not is_image:
        object_packet_refs["draft"] = "4.draft/draft.article.md"
    completion_conditions = (
        [
            "4.draft/draft.article.md 不存在",
            "4.draft/draft_meta.json.generator == image_evidence_pack",
            "ref_review_gate.passed == true (reviewDecision == approved)",
        ]
        if is_image
        else [
            "4.draft/video_script.json 通过 video_script schema",
            "4.draft/draft_meta.json.generator == agent",
            "4.draft/author_self_check.json 存在",
            "ref_review_gate.passed == true (reviewDecision == approved)",
        ]
        if is_video
        else [
            "4.draft/draft.article.md 已写且非占位",
            "4.draft/author_self_check.json 存在",
            "ref_review_gate.passed == true (reviewDecision == approved)",
        ]
    )
    output_paths = (
        ["4.draft/draft_meta.json", "5.review/ref_review_gate.json"]
        if is_image
        else [
            "4.draft/video_script.json",
            "4.draft/draft_meta.json",
            "4.draft/author_self_check.json",
            "5.review/ref_review_gate.json",
        ]
        if is_video
        else [
            "4.draft/draft.article.md",
            "4.draft/author_self_check.json",
            "5.review/ref_review_gate.json",
        ]
    )
    return {
        "schema": "quwoquan_data.lease_packet",
        "jobId": job.job_id,
        "executionId": job.execution_id,
        "ref": job.ref,
        "stage": job.stage.value,
        "queueBackend": job.backend.value,
        "partitionKey": job.partition_key,
        "controllerRunId": job.controller_run_id,
        "assignmentId": job.assignment_id,
        "assignmentPath": list(job.assignment_path),
        "owner": job.owner,
        "allowedReadRoots": list(job.allowed_read_roots),
        "allowedWriteRoots": list(job.allowed_write_roots),
        "sourceUnitId": job.source_unit_id or None,
        "creatorProfileId": job.creator_profile_id or None,
        "authorId": job.author_id or None,
        "creatorArchetype": job.creator_archetype or None,
        "creatorProfileVersion": job.creator_profile_version or None,
        "contentType": content_type or None,
        "resultEnvelopeRequired": job.result_envelope_required,
        "resultEnvelopeContract": {
            "schema": pc.AGENT_RESULT_ENVELOPE_SCHEMA,
            "required": job.result_envelope_required,
            "completionCommand": "execution controller records the validated AgentResultEnvelope for this execution/job/lease",
            "rules": [
                "AgentResultEnvelope.files[].path 必须是 batch root 下相对路径",
                "AgentResultEnvelope.files[].sha256 必须与真实文件一致",
                "AgentResultEnvelope.gates[] 必须是唯一 final verdict 且全部 passed/approved",
                # P4 审计链补强：产物必须能归因到 provider/model/run/prompt。
                "AgentResultEnvelope.agent 必填 provider/model/runId/promptSha256"
                "（promptSha256 = sha256:<本次执行 prompt 全文的 hex>）",
            ],
        },
        "lease": job.lease.holder,
        "mutexKey": job.mutex_key,
        "attempt": job.attempt,
        "maxAttempts": job.max_attempts,
        "leaseExpiresEpoch": job.lease.expires_epoch,
        "deadlineEpoch": job.lease.deadline_epoch,
        "maxWallClockSeconds": job.max_wall_clock_seconds,
        "objectPacketRefs": object_packet_refs,
        # 执行合约 5 要素（harness execution contract）：把模糊 LLM 调用收成有界 agent 调用。
        "executionContract": {
            "inputs": [
                "4.draft/author_job_packet.json",
                "3.compose/writing_pack.json",
                "2.quality/*（证据/source）",
                "5.review/repair_report.json",
            ],
            "budget": {
                "maxWallClockSeconds": job.max_wall_clock_seconds,
                "maxAttempts": job.max_attempts,
                "maxStartupFailures": job.max_startup_failures,
                "stuckThreshold": job.stuck_threshold,
                "tokenBudget": job.token_budget,
                "costBudgetUsd": job.cost_budget_usd,
            },
            "permissions": list(job.permissions or DEFAULT_TOOL_PERMISSIONS),
            "completionConditions": completion_conditions,
            "outputPaths": output_paths,
        },
        "ralphLoop": (
            "draft → 跑单 ref review 门 → 读 issues 自修 → 循环，直到 ref_review_gate.passed=approved；"
            "周期 heartbeat 续租；超 deadlineEpoch 则由 reaper 标 timeout 失败，必须由新的 execution 重试，不得假装完成"
        ),
        "isolation": "single-ref: 只读本 ref 的 packet/template/source，禁止读取同批其它文章正文作为底稿",
        "meta": meta,
    }

__all__ = [name for name in globals() if not name.startswith("__")]
