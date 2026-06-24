"""Object queue lease packet projection for Subagent workers."""
from __future__ import annotations

from typing import Any, Mapping

from task import production_contracts as pc
from task.object_queue_core import DEFAULT_TOOL_PERMISSIONS, QUEUE_BACKEND_LOCAL

def build_lease_packet(job: Mapping[str, Any]) -> dict[str, Any]:
    """把租到的 job 转成 Subagent 可直接消费的 handoff packet（含 Ralph 自纠环出口约束）。"""
    meta = dict(job.get("meta") or {})
    content_type = str(job.get("contentType") or meta.get("contentType") or "")
    carrier = str(job.get("carrier") or meta.get("carrier") or "")
    is_image = content_type == "image" or carrier in ("image", "gallery")
    object_packet_refs = {
        "contentObjectDir": meta.get("contentObjectDir"),
        "authorJobPacket": "4.draft/author_job_packet.json",
        "writingPack": "3.compose/writing_pack.json",
        "draftMeta": "4.draft/draft_meta.json",
        "selfCheck": "4.draft/author_self_check.json",
    }
    if not is_image:
        object_packet_refs["draft"] = "4.draft/draft.article.md"
    completion_conditions = (
        [
            "4.draft/draft.article.md 不存在",
            "4.draft/draft_meta.json.generator == image_evidence_pack",
            "ref_review_gate.passed == true (reviewDecision == approved)",
        ]
        if is_image
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
            "4.draft/draft.article.md",
            "4.draft/author_self_check.json",
            "5.review/ref_review_gate.json",
        ]
    )
    return {
        "schemaVersion": "quwoquan_data.lease_packet",
        "jobId": job.get("jobId"),
        "taskId": job.get("taskId"),
        "batchId": job.get("batchId"),
        "ref": job.get("ref"),
        "stage": job.get("stage"),
        "queueBackend": job.get("queueBackend") or QUEUE_BACKEND_LOCAL,
        "partitionKey": job.get("partitionKey") or job.get("mutexKey") or job.get("ref"),
        "controllerRunId": job.get("controllerRunId"),
        "assignmentId": job.get("assignmentId"),
        "assignmentPath": job.get("assignmentPath") or [],
        "owner": job.get("owner"),
        "allowedReadRoots": job.get("allowedReadRoots") or [],
        "allowedWriteRoots": job.get("allowedWriteRoots") or [],
        "sourceUnitId": job.get("sourceUnitId") or None,
        "creatorProfileId": job.get("creatorProfileId") or meta.get("creatorProfileId"),
        "authorId": job.get("authorId") or meta.get("authorId"),
        "creatorArchetype": job.get("creatorArchetype") or meta.get("creatorArchetype"),
        "creatorProfileVersion": job.get("creatorProfileVersion") or meta.get("creatorProfileVersion"),
        "contentType": content_type or None,
        "resultEnvelopeRequired": bool(job.get("resultEnvelopeRequired")),
        "resultEnvelopeContract": {
            "schemaVersion": pc.AGENT_RESULT_ENVELOPE_SCHEMA,
            "required": bool(job.get("resultEnvelopeRequired")),
            "completionCommand": "qwq-data object-queue complete-envelope --task <task> --batch <batch> --job <jobId> --lease <lease> --envelope <path>",
            "rules": [
                "AgentResultEnvelope.files[].path 必须是 batch root 下相对路径",
                "AgentResultEnvelope.files[].sha256 必须与真实文件一致",
                "AgentResultEnvelope.gates[] 必须是唯一 final verdict 且全部 passed/approved",
            ],
        },
        "lease": job.get("lease"),
        "mutexKey": job.get("mutexKey"),
        "attempt": job.get("attempt"),
        "maxAttempts": job.get("maxAttempts"),
        "leaseExpiresEpoch": job.get("leaseExpiresEpoch"),
        "deadlineEpoch": job.get("deadlineEpoch"),
        "maxWallClockSeconds": job.get("maxWallClockSeconds"),
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
                "maxWallClockSeconds": job.get("maxWallClockSeconds"),
                "maxAttempts": job.get("maxAttempts"),
                "maxStartupFailures": job.get("maxStartupFailures"),
                "stuckThreshold": job.get("stuckThreshold"),
                "tokenBudget": job.get("tokenBudget"),
                "costBudgetUsd": job.get("costBudgetUsd"),
            },
            "permissions": list(job.get("permissions") or DEFAULT_TOOL_PERMISSIONS),
            "completionConditions": completion_conditions,
            "outputPaths": output_paths,
        },
        "ralphLoop": (
            "draft → 跑单 ref review 门 → 读 issues 自修 → 循环，直到 ref_review_gate.passed=approved；"
            "周期 heartbeat 续租；超 deadlineEpoch 则由 reaper 标 timeout 失败（交 spillover），不得假装完成"
        ),
        "isolation": "single-ref: 只读本 ref 的 packet/SOP/source，禁止读取同批其它文章正文作为底稿",
        "meta": meta,
    }

__all__ = [name for name in globals() if not name.startswith("__")]
