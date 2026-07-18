"""Canonical execution stage graph."""
from __future__ import annotations

from content.execution.support import AUTO, CHECKPOINT, Callable, ExecutionContext, ExecutionStage, StageKind, StageResult
from content.execution.controller.checkpoints import _checkpoint_build_homepage, _checkpoint_content_plan, _checkpoint_download_plan, _checkpoint_post_author
from content.execution.controller.publish import _run_publish
from content.execution.controller.stage_download_build import _run_build_prepare, _run_build_validate, _run_download_fetch
from content.execution.controller.stage_post_compose import (
    _run_post_annotate,
    _run_post_compose,
    _run_post_plan,
)
from content.execution.controller.stage_post_review import _run_post_review

DAG: list[tuple[ExecutionStage, StageKind, Callable[[ExecutionContext], StageResult]]] = [
    (ExecutionStage.DOWNLOAD_PLAN, CHECKPOINT, _checkpoint_download_plan),
    (ExecutionStage.DOWNLOAD_FETCH, AUTO, _run_download_fetch),
    (ExecutionStage.BUILD_PREPARE, AUTO, _run_build_prepare),
    (ExecutionStage.BUILD_HOMEPAGE, CHECKPOINT, _checkpoint_build_homepage),
    (ExecutionStage.BUILD_VALIDATE, AUTO, _run_build_validate),
    (ExecutionStage.CONTENT_PLAN, CHECKPOINT, _checkpoint_content_plan),
    (ExecutionStage.POST_PLAN, AUTO, _run_post_plan),
    (ExecutionStage.POST_COMPOSE, AUTO, _run_post_compose),
    (ExecutionStage.POST_AUTHOR, CHECKPOINT, _checkpoint_post_author),
    (ExecutionStage.POST_ANNOTATE, AUTO, _run_post_annotate),
    (ExecutionStage.POST_REVIEW, AUTO, _run_post_review),
    (ExecutionStage.PUBLISH, AUTO, _run_publish),
]
STAGE_NAMES = [stage for stage, _kind, _runner in DAG]
