"""Typed completion validators for object-queue author jobs."""
from __future__ import annotations

from pathlib import Path

from core.control_types import QueueFailureKind, QueueJobStage
from core.data_issue import DataIssue, DataRecoveryAction
from core.io import read_json, write_json
from governance.creators.assignment import CREATOR_ASSIGNMENT_FIELDS, creator_from_payload
from content.execution import store
from content.execution.queue.model import QueueJob


def _creator_payload(job: QueueJob) -> dict[str, object]:
    return {
        "authorId": job.author_id,
        "creatorProfileId": job.creator_profile_id,
        "creatorArchetype": job.creator_archetype,
        "creatorProfileVersion": job.creator_profile_version,
    }


def _stamp_locked_creator(
    job: QueueJob,
    draft_meta: dict[str, object],
    meta_path: Path,
) -> DataIssue | None:
    """Fill only absent creator fields from the frozen queue assignment."""
    locked = creator_from_payload(_creator_payload(job))
    if not locked:
        return None
    changed = False
    for field in CREATOR_ASSIGNMENT_FIELDS:
        value = locked.get(field)
        if value in (None, "", {}):
            continue
        if draft_meta.get(field) in (None, "", {}):
            draft_meta[field] = value
            changed = True
    if not changed:
        return None
    try:
        write_json(meta_path, draft_meta)
    except OSError as exc:
        return job.issue(
            QueueFailureKind.EXECUTION,
            message=f"author draft metadata cannot be written: {exc}",
            recovery=DataRecoveryAction.REWIND_COMPOSE,
        )
    return None


def author_completion_issues(job: QueueJob) -> tuple[DataIssue, ...]:
    """Validate author output and retain the typed reason for every failure."""
    if job.stage is not QueueJobStage.AUTHOR or not job.require_governance:
        return ()
    content_dir = job.content_object_dir
    if not content_dir.startswith(("posts/article/", "posts/video/")):
        return ()
    is_video = content_dir.startswith("posts/video/")
    root = store.execution_root(job.execution_id)
    draft_path = root / content_dir / "4.draft" / (
        "video_script.json" if is_video else "draft.article.md"
    )
    meta_path = root / content_dir / "4.draft" / "draft_meta.json"
    issues: list[DataIssue] = []

    if not draft_path.is_file():
        issues.append(
            job.issue(
                QueueFailureKind.EXECUTION,
                message=f"author output missing: {draft_path.relative_to(root).as_posix()}",
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            )
        )
    else:
        try:
            article = draft_path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(
                job.issue(
                    QueueFailureKind.EXECUTION,
                    message=f"author output unreadable: {exc}",
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                )
            )
        else:
            if is_video:
                from content.post.video.authoring import video_author_issues

                issues.extend(video_author_issues(job.execution_id, job.ref, require_agent_run=False))
            else:
                from content.post.article.draft_io import is_placeholder

                if is_placeholder(article):
                    issues.append(
                        job.issue(
                            QueueFailureKind.EXECUTION,
                            message="author output remains placeholder",
                            recovery=DataRecoveryAction.REWIND_COMPOSE,
                        )
                    )
    try:
        loaded_meta = read_json(meta_path)
    except (OSError, ValueError) as exc:
        issues.append(
            job.issue(
                QueueFailureKind.EXECUTION,
                message=f"author draft metadata unreadable: {exc}",
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            )
        )
        loaded_meta: object = {}
    if not isinstance(loaded_meta, dict):
        issues.append(
            job.issue(
                QueueFailureKind.EXECUTION,
                message="author draft metadata must be an object",
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            )
        )
        loaded_meta = {}
    draft_meta = {str(key): value for key, value in loaded_meta.items()}
    generator = str(draft_meta.get("generator") or "").strip()
    if generator != "agent":
        issues.append(
            job.issue(
                QueueFailureKind.EXECUTION,
                message=f"draft_meta.generator is {generator or '<missing>'}, expected agent",
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            )
        )
    if not issues and generator == "agent":
        write_issue = _stamp_locked_creator(job, draft_meta, meta_path)
        if write_issue is not None:
            issues.append(write_issue)
    expected_creator = creator_from_payload(_creator_payload(job))
    if expected_creator:
        actual_creator = creator_from_payload(draft_meta)
        for field in CREATOR_ASSIGNMENT_FIELDS:
            expected = str(expected_creator.get(field) or "").strip()
            actual = str(actual_creator.get(field) or "").strip()
            if expected and actual != expected:
                issues.append(
                    job.issue(
                        QueueFailureKind.GOVERNANCE,
                        message=(
                            f"draft_meta.{field} is {actual or '<missing>'}, "
                            f"expected locked creator assignment {expected}"
                        ),
                        recovery=DataRecoveryAction.MANUAL_REVIEW,
                    )
                )
    return tuple(issues)


__all__ = ["author_completion_issues"]
