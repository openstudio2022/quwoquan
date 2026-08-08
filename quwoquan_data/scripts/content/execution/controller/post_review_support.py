"""Shared deterministic helpers for the post-review stage controller."""

from __future__ import annotations

from core.control_types import ExecutionStage

from content.execution.support import (
    DataIssue,
    DataIssueCode,
    DataRecoveryAction,
    ExecutionContext,
    Mapping,
    Path,
    read_json,
)


def approved_review_refs(
    ctx: ExecutionContext,
    *,
    refs: set[str] | None = None,
) -> list[str]:
    from content.post import object_index as content_object

    approved: list[str] = []
    for ref in content_object.iter_content_refs(ctx.execution_id):
        if refs is not None and ref not in refs:
            continue
        try:
            gate_path = (
                content_object.content_object_dir(ctx.execution_id, ref)
                / "5.review"
                / "review_gate.json"
            )
        except KeyError:
            continue
        if not gate_path.is_file():
            continue
        envelope = read_json(gate_path)
        payload = envelope.get("payload") or envelope
        if payload.get("passed") is True:
            approved.append(ref)
    return approved


def batch_reducer_payload(
    ctx: ExecutionContext,
    *,
    refs: set[str] | None = None,
) -> list[dict[str, str]]:
    from content.post import object_index as content_object
    from content.post.article.article_media_contract import (
        read_article_media_closure,
    )
    from content.post.article.draft_io import read_draft_article, read_writing_pack

    payload: list[dict[str, str]] = []
    for ref in approved_review_refs(ctx, refs=refs):
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        if coords.get("contentType") != "article":
            continue
        article = read_draft_article(ctx.execution_id, ref)
        pack = read_writing_pack(ctx.execution_id, ref) or {}
        if not article:
            continue
        media_mode = ""
        media_issue = ""
        try:
            manifest = read_json(
                content_object.content_object_dir(ctx.execution_id, ref)
                / "manifest.json"
            )
            media_mode = str(read_article_media_closure(manifest)["mode"])
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            media_issue = str(exc)
        payload.append(
            {
                "ref": ref,
                "article": article,
                "writingIntent": str(pack.get("writingIntent") or ""),
                "baseSourceRef": str(pack.get("baseSourceRef") or ""),
                "baseSourceReusePolicy": str(pack.get("baseSourceReusePolicy") or ""),
                "articleMediaMode": media_mode,
                "articleMediaIssue": media_issue,
            }
        )
    return payload


def aggregate_review_fallback(
    ctx: ExecutionContext,
    *,
    refs: set[str] | None = None,
) -> ExecutionStage | None:
    """Map typed review issues to the narrowest deterministic fallback stage."""
    from content.execution.stage_reports import iter_stage_envelopes

    saw_failure = False
    download_issue_codes = {
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.SOURCE_UNREADABLE,
        DataIssueCode.SOURCE_PLAN_INVALID,
    }
    for ref, report in iter_stage_envelopes(
        ctx.execution_id,
        "post",
        "review_gate",
    ):
        if refs is not None and ref not in refs:
            continue
        payload = report.get("payload") or report
        if payload.get("passed") is True:
            continue
        issues = [
            DataIssue.from_dict(issue)
            for issue in payload.get("issues") or []
            if isinstance(issue, Mapping)
        ]
        if not issues:
            continue
        saw_failure = True
        if any(
            issue.code in download_issue_codes
            or issue.recovery is DataRecoveryAction.REWIND_DOWNLOAD
            for issue in issues
        ):
            return ExecutionStage.DOWNLOAD_PLAN
    return ExecutionStage.POST_COMPOSE if saw_failure else None


def review_gate_is_stale(
    ctx: ExecutionContext,
    ref: str,
    gate_path: Path,
) -> bool:
    """Return whether review predates any compose input or authored draft."""
    from core.paths import STAGE_COMPOSE

    from content.post.article.draft_io import (
        draft_article_path,
        prompt_path,
        writing_pack_path,
    )
    from content.post.object_index import BRIEF_FILE, content_object_stage_dir

    try:
        gate_mtime = gate_path.stat().st_mtime
    except OSError:
        return True
    candidates: list[Path] = [
        writing_pack_path(ctx.execution_id, ref),
        prompt_path(ctx.execution_id, ref),
        draft_article_path(ctx.execution_id, ref),
        content_object_stage_dir(ctx.execution_id, ref, STAGE_COMPOSE) / BRIEF_FILE,
    ]
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_mtime > gate_mtime:
                return True
        except OSError:
            return True
    return False


def content_ref_types(
    ctx: ExecutionContext,
    refs: list[str],
) -> dict[str, list[str]]:
    from content.execution.identity import parse_execution_id
    from content.post import object_index as content_object

    execution_content_type = parse_execution_id(ctx.execution_id).content_type.value
    by_type: dict[str, list[str]] = {}
    for ref in refs:
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        content_type = str(coords.get("contentType") or "").strip()
        if not content_type:
            raise ValueError(f"content object {ref!r} has no contentType")
        if content_type != execution_content_type:
            raise ValueError(
                f"content object {ref!r} type {content_type!r} conflicts with "
                f"execution type {execution_content_type!r}"
            )
        by_type.setdefault(content_type, []).append(ref)
    return {key: value for key, value in by_type.items() if value}


def runtime_materialization_issues(
    ctx: ExecutionContext,
    refs: list[str],
) -> list[str]:
    from content.execution.recovery.post_recovery import _content_type_for_carrier
    from content.post import object_index as content_object

    missing: list[str] = []
    issues: list[str] = []
    for ref in refs:
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        expected_type = str(coords.get("contentType") or "article")
        try:
            obj_dir = content_object.content_object_dir(ctx.execution_id, ref)
        except KeyError:
            missing.append(ref)
            continue
        failure_path = obj_dir / "5.review" / "materialize_failure.json"
        if failure_path.is_file():
            try:
                failure = read_json(failure_path)
                message = str(failure.get("message") or "materialize failed")
            except (OSError, ValueError, TypeError):
                message = "materialize failed"
            issues.append(f"{ref}: {message}")
            missing.append(ref)
            continue
        manifest_path = obj_dir / "manifest.json"
        if not manifest_path.is_file():
            missing.append(ref)
            continue
        try:
            manifest = read_json(manifest_path)
        except (OSError, ValueError, TypeError):
            issues.append(f"{ref}: materialized manifest.json is unreadable")
            continue
        actual_type = _content_type_for_carrier(
            manifest.get("carrier") or manifest.get("contentType")
        )
        if actual_type != expected_type:
            issues.append(
                f"{ref}: runtime carrier {actual_type} != planned {expected_type}"
            )
        if expected_type == "article" and not (obj_dir / "article.md").is_file():
            missing.append(ref)
        if (
            expected_type == "video"
            and not (obj_dir / "assets" / "video.mp4").is_file()
        ):
            missing.append(ref)
    if missing:
        issues.insert(
            0,
            "release missing planned post ref(s): "
            + ", ".join(sorted(set(missing))[:20]),
        )
    return issues


def materialize_reviewed_refs(
    ctx: ExecutionContext,
    refs: list[str],
) -> list[str]:
    from content.post.materialize_apply import materialize_posts
    from content.post.materialize_residue_cleanup import prune_unregistered_post_residue

    issues: list[str] = []
    by_type = content_ref_types(ctx, refs)
    for content_type, typed_refs in sorted(by_type.items()):
        try:
            materialize_posts(ctx.execution_id, content_type, refs=typed_refs)
        except Exception as exc:  # noqa: BLE001 - stage issue preserves recovery.
            issues.append(f"{content_type} materialize failed: {exc}")
    try:
        prune_unregistered_post_residue(ctx.execution_id)
    except Exception as exc:  # noqa: BLE001 - stage issue preserves recovery.
        issues.append(f"prune unregistered post residue failed: {exc}")
    return issues


def post_exit_issues(
    ctx: ExecutionContext,
    refs: list[str],
) -> list[str]:
    from content.post.gate import gate_post

    issues: list[str] = []
    for content_type, typed_refs in sorted(content_ref_types(ctx, refs).items()):
        issues.extend(gate_post(ctx.execution_id, content_type, refs=typed_refs))
    issues.extend(runtime_materialization_issues(ctx, refs))
    return list(dict.fromkeys(str(issue) for issue in issues))


__all__ = [
    "aggregate_review_fallback",
    "approved_review_refs",
    "batch_reducer_payload",
    "content_ref_types",
    "materialize_reviewed_refs",
    "post_exit_issues",
    "review_gate_is_stale",
]
