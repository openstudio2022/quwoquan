"""Bind one post author result to immutable, queue-consumable evidence."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.io import read_json, write_json
from content.execution.production_contracts import (
    build_agent_result_envelope,
    build_gate_verdict,
    sha256_file,
    validate_agent_result_envelope,
)
from content.execution.queue.core import stable_job_id
from content.post import object_index as content_object
from content.post.article.draft_io import (
    draft_article_path,
    draft_meta_path,
    is_placeholder,
    prompt_path,
    read_draft_meta,
    read_writing_pack,
)

if TYPE_CHECKING:
    from content.execution.agent.outcome import AgentRunOutcome
    from content.execution.context import ExecutionContext


def _primary_author_output(
    execution_id: str,
    ref: str,
    *,
    carrier: str,
) -> tuple[Path, str, str]:
    if carrier == "video":
        from content.post.video.authoring import video_script_path

        return video_script_path(execution_id, ref), "video_script", "agent"
    if carrier == "image":
        return draft_meta_path(execution_id, ref), "image_draft_meta", "image_evidence_pack"
    return draft_article_path(execution_id, ref), "article_draft", "agent"


def write_post_author_evidence(
    ctx: "ExecutionContext",
    *,
    ref: str,
    outcome: "AgentRunOutcome",
) -> Path:
    """Validate the real output and write the canonical AgentResultEnvelope."""
    pack = read_writing_pack(ctx.execution_id, ref) or {}
    meta = read_draft_meta(ctx.execution_id, ref) or {}
    carrier = str(pack.get("carrier") or "article").strip()
    draft_dir = content_object.content_object_stage_dir(
        ctx.execution_id,
        ref,
        "4.draft",
    )
    packet_path = draft_dir / "author_job_packet.json"
    source_prompt_path = prompt_path(ctx.execution_id, ref)
    if not packet_path.is_file() or not source_prompt_path.is_file():
        raise ValueError(
            f"post author evidence requires packet and prompt: ref={ref}"
        )
    packet = read_json(packet_path)
    output_path, output_role, expected_generator = _primary_author_output(
        ctx.execution_id,
        ref,
        carrier=carrier,
    )
    issues: list[str] = []
    if not outcome.succeeded:
        issues.append("agent_run_not_finished")
    if not output_path.is_file():
        issues.append("author_output_missing")
    generator = str(meta.get("generator") or "").strip()
    if generator != expected_generator:
        issues.append(
            f"draft_generator_mismatch:{generator or '<missing>'}!={expected_generator}"
        )
    if carrier not in {"image", "video"} and output_path.is_file():
        if is_placeholder(output_path.read_text(encoding="utf-8")):
            issues.append("article_output_placeholder")
    if carrier == "video" and output_path.is_file():
        from content.post.video.authoring import video_author_issues

        issues.extend(
            str(issue)
            for issue in video_author_issues(
                ctx.execution_id,
                ref,
                require_agent_run=False,
            )
        )
    if (
        str(packet.get("executionId") or "") != ctx.execution_id
        or str(packet.get("objectRef") or "") != ref
    ):
        issues.append("author_packet_binding_mismatch")
    prompt_sha = str(meta.get("promptSha256") or "").strip()
    if not prompt_sha:
        prompt_sha = sha256_file(source_prompt_path)
    output_sha = sha256_file(output_path) if output_path.is_file() else prompt_sha
    if not outcome.run_id or not outcome.provider.value or not str(meta.get("model") or ctx.model):
        issues.append("agent_provenance_incomplete")
    self_check = {
        "schema": "quwoquan_data.author_self_check",
        "stage": "4.draft",
        "executionId": ctx.execution_id,
        "objectRef": ref,
        "passed": not issues,
        "checks": [
            {
                "name": "post_author_output",
                "passed": not issues,
                "carrier": carrier,
                "generator": generator,
                "output": output_path.name,
            }
        ],
        "issues": issues,
    }
    from core.schema import assert_valid

    assert_valid(
        self_check,
        "content",
        "author_self_check",
        label=f"author_self_check:{ref}",
    )
    write_json(draft_dir / "author_self_check.json", self_check)
    gate = build_gate_verdict(
        gate_id="post_author_output",
        decision="passed" if not issues else "failed",
        input_hash=prompt_sha,
        output_hash=output_sha,
        issues=issues,
    )
    envelope = build_agent_result_envelope(
        job={
            "jobId": stable_job_id(ctx.execution_id, ref, "author"),
            "executionId": ctx.execution_id,
            "ref": ref,
            "stage": "author",
        },
        files=[
            {
                "path": output_path.relative_to(draft_dir).as_posix(),
                "sha256": output_sha,
                "role": output_role,
            }
        ],
        gates=[gate],
        provider=outcome.provider.value,
        model=str(meta.get("model") or ctx.model or ""),
        run_id=outcome.run_id,
        prompt_sha256=prompt_sha,
        agent_id=outcome.agent_id or None,
    )
    assert_valid(
        envelope,
        "content",
        "agent_result_envelope",
        label=f"agent_result_envelope:{ref}",
    )
    envelope_issues = validate_agent_result_envelope(
        envelope,
        workspace_root=draft_dir,
    )
    if envelope_issues:
        raise ValueError(
            "post author envelope invalid: " + "; ".join(envelope_issues)
        )
    if issues:
        raise ValueError("post author self-check failed: " + "; ".join(issues))
    envelope_path = draft_dir / "agent_result_envelope.json"
    write_json(envelope_path, envelope)
    return envelope_path


__all__ = ["write_post_author_evidence"]
