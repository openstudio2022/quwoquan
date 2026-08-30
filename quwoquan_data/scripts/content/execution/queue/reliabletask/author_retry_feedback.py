"""Typed predecessor review feedback for a new ReliableTask author retry."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from core.io import read_json

from content.execution.queue.model import QueueJob


def article_retry_review_feedback_addendum(
    job: QueueJob,
    object_dir: Path,
    root: Path,
) -> str:
    """Render predecessor typed review feedback for one new retryOf object."""

    del object_dir
    request_path = root / "0.plan/request.json"
    plan_path = root / "_shared/content_plan_packet.json"
    if not request_path.is_file():
        return ""
    from content.execution.request import RuntimeExecutionRequest

    request = RuntimeExecutionRequest.from_document(read_json(request_path))
    raw_feedback = request.retry_review_feedback
    if raw_feedback is None:
        return ""
    from content.execution.planning.retry_review_feedback import (
        validate_retry_review_feedback,
    )

    feedback = validate_retry_review_feedback(raw_feedback)
    if feedback.get("executionId") != job.execution_id:
        raise ValueError(
            f"ReliableTask retry review feedback executionId mismatch: {job.ref}"
        )
    if not plan_path.is_file():
        raise ValueError(
            f"ReliableTask retry review feedback content plan missing: {job.ref}"
        )
    plan = read_json(plan_path)
    if not isinstance(plan, Mapping) or plan.get("executionId") != job.execution_id:
        raise ValueError(
            f"ReliableTask retry review feedback content plan invalid: {job.ref}"
        )
    current_items = [
        item
        for item in plan.get("items") or []
        if isinstance(item, Mapping) and str(item.get("ref") or "") == job.ref
    ]
    if len(current_items) != 1:
        raise ValueError(
            f"ReliableTask retry review feedback current object ambiguous: {job.ref}"
        )
    entity_refs = current_items[0].get("entityRefs")
    if not isinstance(entity_refs, list) or len(entity_refs) != 1:
        raise ValueError(
            f"ReliableTask retry review feedback entity binding invalid: {job.ref}"
        )
    entity_ref = str(entity_refs[0])
    matches = [
        item
        for item in feedback.get("items") or []
        if isinstance(item, Mapping) and item.get("entityRef") == entity_ref
    ]
    if not matches:
        return ""
    if len(matches) != 1:
        raise ValueError(
            f"ReliableTask retry review feedback entity binding ambiguous: {job.ref}"
        )
    item = matches[0]
    issues = [str(value).strip() for value in item.get("issues") or []]
    if not issues:
        raise ValueError(
            f"ReliableTask retry review feedback issues invalid: {job.ref}"
        )
    rendered = "\n".join(f"- {issue}" for issue in issues)
    return (
        "\n\n## 前驱 final review 的 typed 重写反馈\n"
        "这是新 sequence 的失败对象重写，不是继续发布前驱稿件。必须使用当前 "
        "writing_pack.json 冻结的新来源与事实边界重新撰写全文，逐项消除以下问题；"
        "不得复用前驱正文的连续表达，不得通过改标题、改 entityRef、删除审核证据或"
        "降低实体相关性、近抄、权利及质量门来规避：\n"
        f"{rendered}\n"
        "若 sourceUseMode=factual_reference_only，只可提取可核验事实并以独立句式、"
        "结构和叙事重新表达；不得保留来源连续长句。完成后逐项自检，确认当前标题、"
        "正文主线和结尾均兑现当前实体，且旧问题中的误绑或近抄片段已不存在。"
    )
