"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ContentType, ExecutionStage, PostStage, StageStatus
from content.execution.support import AUTO, Any, DataIssue, DataIssueCode, DataIssueStage, DataRecoveryAction, ExecutionContext, Mapping, Path, Sequence, StageResult, _active_spec, _is_homepage_only_execution, data_issue, data_issues, issue_messages, read_json

def _run_post_plan(ctx: ExecutionContext) -> StageResult:
    """校验 content_plan 已物化 brief。"""
    from content.post.content_plan_validation import validate_content_plan
    from content.post.content_plan_state import load_content_plan_packet
    active_spec = _active_spec(ctx)
    if _is_homepage_only_execution(ctx):
        return StageResult(
            ExecutionStage.POST_PLAN,
            AUTO,
            StageStatus.DONE,
            "homepage-only 批次无篇目，post_plan 确定性跳过",
        )
    existing_packet = load_content_plan_packet(ctx.execution_id)
    issues = validate_content_plan(ctx.execution_id, active_spec)
    if existing_packet is None and not issues:
        issues = ["content_plan_packet.json missing"]
    if issues:
        return StageResult(
            ExecutionStage.POST_PLAN,
            AUTO,
            StageStatus.FAILED,
            "content_plan 未就绪:\n  - " + "\n  - ".join(issues[:10]),
            fallback_stage=ExecutionStage.CONTENT_PLAN,
            issue_records=data_issues(
                DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.POST_PLAN,
                messages=issues,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            ),
        )
    n = len((existing_packet or {}).get("items") or [])
    return StageResult(
        ExecutionStage.POST_PLAN,
        AUTO,
        StageStatus.DONE,
        f"content_plan 已物化 {n} 篇 brief",
    )

def _clear_compose_base_draft_assignments(
    ledger: dict[str, Any],
    selected_refs: list[str],
    overrides: Mapping[str, Mapping[str, Any]],
    *,
    image_refs: set[str] | None = None,
) -> tuple[dict[str, Any], list[str], bool]:
    """Clear stale base-draft assignments for refs/sources that will be recomposed.
    Re-runs must be driven by the current content plan, not by half-written state
    from an earlier attempt.  The source-side clear matters when an old ref used
    to occupy the source that the current content plan now assigns to another ref.
    底稿共用策略与 content_plan 对齐（content_plan 对 carrier==image 豁免
    one-source-one-work）：图文同源是正常现象，image/gallery 作品可与文章或其它图片
    作品共用同一底稿；只有两个对象都是长文类载体时复用同一底稿才算违规凑数。
    """
    image_set = set(image_refs or ())
    selected = set(selected_refs)
    selected_sources: dict[str, str] = {}
    duplicate_sources: list[str] = []
    for ref in selected_refs:
        override = overrides.get(ref) or {}
        source_ref = str(override.get("baseSourceRef") or "").strip()
        if not source_ref:
            continue
        previous = selected_sources.get(source_ref)
        if (
            previous
            and previous != ref
            and ref not in image_set
            and previous not in image_set
        ):
            duplicate_sources.append(f"{source_ref} -> {previous}, {ref}")
        selected_sources[source_ref] = ref
    current = dict(ledger.get("assignments") or {})
    assignments = {
        source_ref: post_ref
        for source_ref, post_ref in current.items()
        if post_ref not in selected and source_ref not in selected_sources
    }
    changed = assignments != current
    cleaned = dict(ledger)
    cleaned["assignments"] = assignments
    return cleaned, duplicate_sources, changed

def _run_post_compose(ctx: ExecutionContext) -> StageResult:
    from content.execution.recovery.post_recovery import _content_type_for_carrier
    from content.execution.recovery.stage_reset import _compose_brief_gate_failures
    if _is_homepage_only_execution(ctx):
        return StageResult(
            ExecutionStage.POST_COMPOSE,
            AUTO,
            StageStatus.DONE,
            "homepage-only 批次无篇目，post_compose 确定性跳过",
        )
    from content.post.handler import PostStageRequest, handle_post
    from content.post import object_index as content_object
    from content.post.object_index import BRIEF_FILE, content_object_stage_dir, iter_content_refs
    from content.post.content_plan import load_writing_intent_overrides
    from content.post.article.draft_io import (
        draft_article_path,
        is_placeholder,
        prompt_path,
        read_writing_pack,
        writing_pack_path,
    )
    from core.io import read_json
    from core.paths import STAGE_COMPOSE
    overrides = load_writing_intent_overrides(ctx.execution_id)
    expected_refs = list(iter_content_refs(ctx.execution_id))
    pending_refs: list[str] = []
    non_article_pending_refs: set[str] = set()
    for ref in expected_refs:
        needs_prepare = False
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        expected_content_type = str(coords.get("contentType") or "")
        pack = read_writing_pack(ctx.execution_id, ref) or {}
        is_image = (
            expected_content_type == "image"
            or str(pack.get("carrier") or "") == "image"
        )
        is_video = (
            expected_content_type == "video"
            or str(pack.get("carrier") or "") == "video"
        )
        wp = writing_pack_path(ctx.execution_id, ref)
        prompt = prompt_path(ctx.execution_id, ref)
        draft = draft_article_path(ctx.execution_id, ref)
        if not wp.is_file() or not prompt.is_file():
            needs_prepare = True
        elif is_image:
            if draft.is_file():
                needs_prepare = True
        elif is_video:
            from content.post.video.authoring import video_script_path

            script_path = video_script_path(ctx.execution_id, ref)
            if draft.is_file() or not script_path.parent.is_dir():
                needs_prepare = True
        else:
            if not draft.is_file():
                needs_prepare = True
            else:
                try:
                    if is_placeholder(draft.read_text(encoding="utf-8")):
                        needs_prepare = True
                except OSError:
                    needs_prepare = True
        if expected_content_type and pack:
            actual_content_type = _content_type_for_carrier(pack.get("carrier"))
            if actual_content_type != expected_content_type:
                needs_prepare = True
        if not needs_prepare:
            gate_path = (
                content_object_stage_dir(ctx.execution_id, ref, STAGE_COMPOSE)
                / "compose_brief_gate.json"
            )
            if not gate_path.is_file():
                needs_prepare = True
            else:
                try:
                    gate = read_json(gate_path)
                    gate_payload = gate.get("payload") if isinstance(gate.get("payload"), Mapping) else gate
                    if isinstance(gate_payload, Mapping) and gate_payload.get("passed") is False:
                        needs_prepare = True
                except (OSError, ValueError, TypeError):
                    needs_prepare = True
        override = overrides.get(ref) or {}
        if override:
            brief_path = (
                content_object_stage_dir(ctx.execution_id, ref, STAGE_COMPOSE)
                / BRIEF_FILE
            )
            try:
                brief = read_json(brief_path) if brief_path.is_file() else {}
            except (OSError, ValueError, TypeError):
                brief = {}
            for field in (
                "writingIntent",
                "baseSourceRef",
                "carrier",
                "sourceCollectionId",
                "assetRefs",
            ):
                if field in override and override.get(field) not in (None, ""):
                    if brief.get(field) != override.get(field):
                        needs_prepare = True
                        break
        if needs_prepare:
            pending_refs.append(ref)
            if is_image or is_video:
                non_article_pending_refs.add(ref)
    if expected_refs and not pending_refs:
        return StageResult(
            ExecutionStage.POST_COMPOSE,
            AUTO,
            StageStatus.DONE,
            "all writing packs and authored drafts already present",
        )
    selected_refs = pending_refs
    if selected_refs:
        print(
            "[task execute] compose object repair: "
            + ", ".join(selected_refs)
        )
        from content.post.article.base_draft import load_base_draft_ledger, save_base_draft_ledger
        ledger = load_base_draft_ledger(ctx.execution_id)
        ledger, duplicate_sources, ledger_changed = _clear_compose_base_draft_assignments(
            ledger, selected_refs, overrides, image_refs=non_article_pending_refs
        )
        if duplicate_sources:
            return StageResult(
                ExecutionStage.POST_COMPOSE,
                AUTO,
                StageStatus.FAILED,
                "content_plan declares duplicate baseSourceRef: "
                + "; ".join(duplicate_sources[:5]),
                fallback_stage=ExecutionStage.CONTENT_PLAN,
            )
        if ledger_changed:
            save_base_draft_ledger(ctx.execution_id, ledger)
    selected_type = ContentType(
        str(
            (content_object.content_coords(ctx.execution_id, selected_refs[0]) or {}).get(
                "contentType"
            )
            if selected_refs
            else (_active_spec(ctx).get("contentType") or "article")
        )
    )
    handle_post(
        PostStageRequest(
            execution_id=ctx.execution_id,
            content_type=selected_type,
            stage=PostStage.COMPOSE_BRIEF,
            refs=tuple(selected_refs),
            allow_partial=False,
            materialize=False,
        )
    )
    gate_failures, fallback_stage = _compose_brief_gate_failures(ctx, selected_refs)
    if gate_failures:
        effective_fallback = fallback_stage or ExecutionStage.DOWNLOAD_PLAN
        return StageResult(
            ExecutionStage.POST_COMPOSE,
            AUTO,
            StageStatus.FAILED,
            "compose-brief gate failed; stop before authoring",
            fallback_stage=effective_fallback,
            issue_records=gate_failures,
        )
    return StageResult(
        ExecutionStage.POST_COMPOSE,
        AUTO,
        StageStatus.DONE,
        "compose-brief 写出 writing_pack + prompt"
        + (f" ({len(selected_refs)} repaired refs)" if selected_refs else ""),
    )

def _run_post_annotate(ctx: ExecutionContext) -> StageResult:
    from content.post.handler import PostStageRequest, handle_post
    from content.post import object_index as content_object
    if _is_homepage_only_execution(ctx):
        return StageResult(
            ExecutionStage.POST_ANNOTATE,
            AUTO,
            StageStatus.DONE,
            "homepage-only 批次无篇目，post_annotate 确定性跳过",
        )
    active_refs = content_object.iter_content_refs(ctx.execution_id)
    content_type = ContentType(
        str(
            (content_object.content_coords(ctx.execution_id, active_refs[0]) or {}).get(
                "contentType"
            )
        )
    )
    handle_post(
        PostStageRequest(
            execution_id=ctx.execution_id,
            content_type=content_type,
            stage=PostStage.ANNOTATE_ENTITIES,
            refs=tuple(active_refs),
            allow_partial=False,
            materialize=False,
        )
    )
    return StageResult(ExecutionStage.POST_ANNOTATE, AUTO, StageStatus.DONE, "实体 inline 标注完成")
