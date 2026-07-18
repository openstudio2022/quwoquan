"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ContentType, ExecutionStage, PostStage, StageStatus
from content.execution.support import AUTO, Any, DataIssue, DataIssueCode, DataIssueStage, DataRecoveryAction, ExecutionContext, Mapping, Path, Sequence, StageResult, _active_spec, _is_homepage_only_execution, data_issue, data_issues, issue_messages, read_json
def _approved_review_refs(ctx: ExecutionContext, *, refs: set[str] | None = None) -> list[str]:
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

def _batch_reducer_payload(ctx: ExecutionContext, *, refs: set[str] | None = None) -> list[dict[str, str]]:
    from content.post import object_index as content_object
    from content.post.article.draft_io import read_draft_article, read_writing_pack
    payload: list[dict[str, str]] = []
    for ref in _approved_review_refs(ctx, refs=refs):
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        if coords.get("contentType") != "article":
            continue
        article = read_draft_article(ctx.execution_id, ref)
        pack = read_writing_pack(ctx.execution_id, ref) or {}
        if not article:
            continue
        payload.append(
            {
                "ref": ref,
                "article": article,
                "writingIntent": str(pack.get("writingIntent") or ""),
                "baseSourceRef": str(pack.get("baseSourceRef") or ""),
                "baseSourceReusePolicy": str(pack.get("baseSourceReusePolicy") or ""),
            }
        )
    return payload

def _aggregate_review_fallback(
    ctx: ExecutionContext,
    *,
    refs: set[str] | None = None,
) -> ExecutionStage | None:
    """Aggregate typed review issues into the ReAct fallback stage.
    只有来源文件确实缺失/不可读时才回 download。事实表达、必含事实、
    文体或载体失败都属于单作品 compose 修复，不能让整批回退重抓来源。
    """
    from content.execution.stage_reports import iter_stage_envelopes
    saw_failure = False
    download_issue_codes = {
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.SOURCE_UNREADABLE,
        DataIssueCode.SOURCE_PLAN_INVALID,
    }
    for _ref, rep in iter_stage_envelopes(ctx.execution_id, "post", "review_gate"):
        if refs is not None and _ref not in refs:
            continue
        payload = rep.get("payload") or rep
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

def _review_gate_is_stale(ctx: ExecutionContext, ref: str, gate_path: Path) -> bool:
    """Review depends on the latest compose contract and authored draft."""
    from content.post.article.draft_io import draft_article_path, prompt_path, writing_pack_path
    from content.post.object_index import BRIEF_FILE, content_object_stage_dir
    from core.paths import STAGE_COMPOSE
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

def _content_ref_types(ctx: ExecutionContext, refs: list[str]) -> dict[str, list[str]]:
    from content.post import object_index as content_object
    from content.execution.workspace import load_execution_manifest
    execution_content_type = str(
        load_execution_manifest(ctx.execution_id).get("contentType") or ""
    )
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

def _runtime_materialization_issues(ctx: ExecutionContext, refs: list[str]) -> list[str]:
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
        manifest_path = obj_dir / "manifest.json"
        if not manifest_path.is_file():
            missing.append(ref)
            continue
        try:
            manifest = read_json(manifest_path)
        except (OSError, ValueError, TypeError):
            issues.append(f"{ref}: materialized manifest.json is unreadable")
            continue
        actual_type = _content_type_for_carrier(manifest.get("carrier") or manifest.get("contentType"))
        if actual_type != expected_type:
            issues.append(f"{ref}: runtime carrier {actual_type} != planned {expected_type}")
        if expected_type == "article" and not (obj_dir / "article.md").is_file():
            missing.append(ref)
    if missing:
        issues.insert(0, "release missing planned post ref(s): " + ", ".join(sorted(set(missing))[:20]))
    return issues

def _materialize_reviewed_refs(ctx: ExecutionContext, refs: list[str]) -> list[str]:
    from content.post.materialize_apply import materialize_posts
    from content.post.materialize_residue_cleanup import prune_unregistered_post_residue
    issues: list[str] = []
    by_type = _content_ref_types(ctx, refs)
    for content_type, typed_refs in sorted(by_type.items()):
        try:
            materialize_posts(ctx.execution_id, content_type, refs=typed_refs)
        except Exception as exc:  # noqa: BLE001 - gate turns materialization defects into stage issues.
            issues.append(f"{content_type} materialize failed: {exc}")
    # 物化后 content_object_index 已权威：清除 agent 用临时标题落地、最终改派坐标后
    # 遗留的死 provisional 残骸（未登记 + 无 manifest/无成品），否则目录证据链孤儿门
    # 会因旧坐标阶段残骸 BLOCK（放量时 agent 重组合/改标题会复现）。
    try:
        prune_unregistered_post_residue(ctx.execution_id)
    except Exception as exc:  # noqa: BLE001 - 剪枝失败降级为 stage issue，不静默吞。
        issues.append(f"prune unregistered post residue failed: {exc}")
    return issues

def _post_exit_issues(ctx: ExecutionContext, refs: list[str]) -> list[str]:
    from content.post.gate import gate_post
    issues: list[str] = []
    for content_type, typed_refs in sorted(_content_ref_types(ctx, refs).items()):
        issues.extend(gate_post(ctx.execution_id, content_type, refs=typed_refs))
    issues.extend(_runtime_materialization_issues(ctx, refs))
    # Keep repeated global/runtime findings readable across article+image gates.
    return list(dict.fromkeys(str(issue) for issue in issues))


def _post_review_issue_records(
    ctx: ExecutionContext,
    messages: Sequence[str],
    *,
    refs: Sequence[str],
) -> list[DataIssue]:
    """Decode object review gates; never infer affected refs from message text."""
    from content.post import object_index as content_object

    records: list[DataIssue] = []
    for ref in refs:
        try:
            gate_path = (
                content_object.content_object_dir(ctx.execution_id, ref)
                / "5.review"
                / "review_gate.json"
            )
        except KeyError:
            gate_path = None
        if gate_path is None or not gate_path.is_file():
            continue
        envelope = read_json(gate_path)
        payload = envelope.get("payload") or envelope
        if payload.get("passed") is not False:
            continue
        for raw_issue in payload.get("issues") or []:
            if isinstance(raw_issue, Mapping):
                records.append(DataIssue.from_dict(raw_issue))
            else:
                records.append(data_issue(
                    DataIssueCode.QUALITY_FAILED,
                    stage=DataIssueStage.POST_REVIEW,
                    ref=ref,
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                    message=str(raw_issue),
                ))
    if records:
        return records
    return data_issues(
        DataIssueCode.QUALITY_FAILED,
        stage=DataIssueStage.POST_REVIEW,
        messages=messages,
        recovery=DataRecoveryAction.REWIND_COMPOSE,
    )

def _run_post_review(ctx: ExecutionContext) -> StageResult:
    from content.execution.recovery.post_recovery import _content_plan_base_draft_shortfall_refs, _post_review_retry_refs, _release_base_draft_shortfall_refs
    from content.post.handler import PostStageRequest, handle_post
    from content.post import object_index as content_object
    from content.post.article.base_draft import load_base_draft_ledger, save_base_draft_ledger
    from content.execution.handoff import build_execution_reducer_gate, write_execution_reducer_gate
    # 物化 batch 级 base_draft_ledger 落盘：纯图（image-only）批次不认领单一底稿、
    # assignments 合法为空，但 release_integrity 要求 ledger 文件存在且 schema 正确。
    # 幂等：文章批次的 assignments 已在底稿认领时写入，此处只保证文件落盘，不改内容。
    save_base_draft_ledger(
        ctx.execution_id, load_base_draft_ledger(ctx.execution_id)
    )
    if _is_homepage_only_execution(ctx):
        # homepage-only：无篇目对象；主页 review 证据在 build_validate 采纳门产出。
        # 与 image-only 空 payload 行为对齐，写空 batch reducer gate 供 release verify 消费。
        write_execution_reducer_gate(
            ctx.execution_id,
            {
                "schema": "quwoquan_data.execution_reducer_gate",
                "passed": True,
                "issues": [],
                "affectedRefs": [],
                "sourceReuse": {},
                "intentDistribution": {},
                "imageCoverage": {},
            },
        )
        return StageResult(
            ExecutionStage.POST_REVIEW,
            AUTO,
            StageStatus.DONE,
            "homepage-only 批次无篇目，post_review 确定性跳过（主页发布门由 build_validate + release gate 承载）",
        )
    refs = content_object.iter_content_refs(ctx.execution_id)
    active_refs = list(refs)
    preflight_short_refs = _content_plan_base_draft_shortfall_refs(ctx, active_refs)
    if preflight_short_refs:
        return StageResult(
            ExecutionStage.POST_REVIEW,
            AUTO,
            StageStatus.FAILED,
            "content_plan preflight found frozen refs below base draft gate",
            fallback_stage=ExecutionStage.CONTENT_PLAN,
            issue_records=[
                data_issue(
                    DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                    stage=DataIssueStage.CONTENT_PLAN,
                    ref=ref,
                    recovery=DataRecoveryAction.REWIND_DOWNLOAD,
                    message="baseDraftText effective length below release gate",
                )
                for ref in preflight_short_refs
            ],
        )
    all_green = bool(active_refs)
    stale_review_refs: list[str] = []
    for ref in refs:
        gate_path = (
            content_object.content_object_dir(ctx.execution_id, ref)
            / "5.review"
            / "review_gate.json"
        )
        if not gate_path.is_file():
            all_green = False
            stale_review_refs.append(ref)
            continue
        envelope = read_json(gate_path)
        if (envelope.get("payload") or envelope).get("passed") is not True:
            all_green = False
            stale_review_refs.append(ref)
            continue
        if _review_gate_is_stale(ctx, ref, gate_path):
            all_green = False
            stale_review_refs.append(ref)
    initial_issues: list[str] = []
    review_refs = active_refs
    if all_green:
        # review gate 已绿时本分支跳过 handle_post 的 _stage_review，而 media_check
        # 正是在 _stage_review 内产出。纯图（image-only）内容对象的 review 在叶子阶段已
        # 通过，会直接走到此处，导致发布门因缺 media_check envelope 失败。这里幂等补跑
        # 图像安全体检（CV：人脸/水印/OCR/去重），保证发布门有真实 media_check 证据。
        from content.source.media.check import check_images
        check_images(ctx.execution_id, list(active_refs), allow_needs_review=True)
        initial_issues = _materialize_reviewed_refs(ctx, active_refs)
        initial_issues.extend(_post_exit_issues(ctx, active_refs))
        release_short_refs = _release_base_draft_shortfall_refs(
            ctx,
            active_refs=active_refs,
        )
        if release_short_refs:
            initial_issues.extend(
                f"{ref}: baseDraftText below release gate"
                for ref in release_short_refs
            )
        if not initial_issues:
            return StageResult(
                ExecutionStage.POST_REVIEW,
                AUTO,
                StageStatus.DONE,
                "existing review + materialized packages still pass current gates",
            )
        initial_issue_records = _post_review_issue_records(
            ctx,
            initial_issues,
            refs=active_refs,
        )
        matched_refs, _issue_map = _post_review_retry_refs(ctx, initial_issue_records)
        if not matched_refs:
            return StageResult(
                ExecutionStage.POST_REVIEW,
                AUTO,
                StageStatus.FAILED,
                "发布门未过但无法映射到对象级 ref:\n  - " + "\n  - ".join(initial_issues[:10]),
                fallback_stage=ExecutionStage.POST_COMPOSE,
                issue_records=initial_issue_records,
            )
        review_refs = [ref for ref in matched_refs if ref in active_refs]
    elif stale_review_refs:
        review_refs = sorted(set(stale_review_refs))
    handle_post(
        PostStageRequest(
            execution_id=ctx.execution_id,
            content_type=ContentType(
                next(iter(_content_ref_types(ctx, review_refs)))
            ),
            stage=PostStage.REVIEW,
            refs=tuple(review_refs),
            allow_partial=False,
            materialize=True,
        )
    )
    issues = _materialize_reviewed_refs(ctx, active_refs)
    issues.extend(_post_exit_issues(ctx, active_refs))
    release_short_refs = _release_base_draft_shortfall_refs(
        ctx,
        active_refs=active_refs,
    )
    if release_short_refs:
        issues.extend(
            f"{ref}: baseDraftText below release gate"
            for ref in release_short_refs
        )
    for ref in refs:
        gate_path = (
            content_object.content_object_dir(ctx.execution_id, ref)
            / "5.review"
            / "review_gate.json"
        )
        if not gate_path.is_file():
            issues.append(f"{ref}: review_gate.json missing")
            continue
        envelope = read_json(gate_path)
        payload = envelope.get("payload") or envelope
        if payload.get("passed") is not True:
            ref_issues = [str(item) for item in (payload.get("issues") or [])]
            issues.append(
                f"{ref}: review_gate failed"
                + (": " + "; ".join(ref_issues[:5]) if ref_issues else "")
            )
    active_ref_types = _content_ref_types(ctx, active_refs)
    article_refs = set(active_ref_types.get("article") or [])
    refs_payload = _batch_reducer_payload(ctx, refs=article_refs) if article_refs else []
    execution_gate = build_execution_reducer_gate(refs_payload) if refs_payload else {
        "schema": "quwoquan_data.execution_reducer_gate",
        "passed": not article_refs,
        "issues": [] if not article_refs else ["batchReducer: no draft payloads available after post_review"],
        "affectedRefs": [],
        "sourceReuse": {},
        "intentDistribution": {},
        "imageCoverage": {},
    }
    write_execution_reducer_gate(ctx.execution_id, execution_gate)
    if execution_gate.get("passed") is False:
        issues.extend([str(issue) for issue in (execution_gate.get("issues") or [])])
    if issues:
        fb = _aggregate_review_fallback(ctx, refs=set(active_refs)) or ExecutionStage.POST_COMPOSE
        return StageResult(ExecutionStage.POST_REVIEW, AUTO, StageStatus.FAILED,
                           "发布门未过:\n  - " + "\n  - ".join(issues[:10]),
                           fallback_stage=fb,
                           issue_records=_post_review_issue_records(ctx, issues, refs=active_refs))
    return StageResult(ExecutionStage.POST_REVIEW, AUTO, StageStatus.DONE, "review + materialize approved，发布门通过")
