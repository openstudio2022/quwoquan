"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ExecutionStage, StageStatus
from core.data_issue import DataIssue
from content.execution.support import AUTO, Any, DataIssueCode, DataIssueLane, DataIssueStage, DataRecoveryAction, ExecutionContext, Mapping, Path, StageResult, _active_spec, _entity_homepages_per_target, _prune_inactive_entity_homepage_artifacts, data_issue, execution_root, hashlib, issue_messages, json, os, re, read_json, require_domain_etype, stage_issues, store, write_json

_SERIAL_DOWNLOAD_WORKER_COUNT = 1

def _run_download_fetch(ctx: ExecutionContext) -> StageResult:
    from content.execution.agent.auto_research import _download_auto_research_lanes, _entity_ids_grouped_by_type, _refresh_stale_source_plans_for_fetch
    from content.execution.recovery.download_freshness import _content_plan_source_shortfall_entity_ids, _download_content_capacity_preflight, _download_fetch_stale_entity_ids, _resolve_download_content_capacity_shortfall
    from content.execution.recovery.download_gate import _build_prepare_homepage_retry_entity_ids, _download_repair_path, _download_retry_entity_ids, _download_retry_lane, _download_stage_gate_issues
    from content.execution.recovery.download_repair import _record_download_repair
    from content.execution.recovery.download_unresolved import _write_download_availability
    from content.source.handler import handle_download
    from content.source.gate import gate_download

    def current_gate_issues(entity_ids: list[str]) -> list[DataIssue]:
        issues = gate_download(ctx.execution_id, target_entities=set(ctx.entity_ids))
        seen = set(issues)
        for issue in _download_stage_gate_issues(ctx, entity_ids=entity_ids):
            if issue not in seen:
                issues.append(issue)
                seen.add(issue)
        return issues

    retry_entity_ids = _download_retry_entity_ids(ctx)
    build_prepare_retry_entity_ids = _build_prepare_homepage_retry_entity_ids(ctx)
    refresh_before_fetch_ids: list[str] = []
    download_lane_override = ""
    if retry_entity_ids:
        target_entity_ids = retry_entity_ids
        refresh_before_fetch_ids = retry_entity_ids
    elif build_prepare_retry_entity_ids:
        target_entity_ids = build_prepare_retry_entity_ids
        download_lane_override = "homepage"
    else:
        fetch_stale_ids = set(_download_fetch_stale_entity_ids(ctx))
        shortfall_ids = set(_content_plan_source_shortfall_entity_ids(ctx))
        target_ids = fetch_stale_ids | shortfall_ids
        target_entity_ids = [entity_id for entity_id in ctx.entity_ids if entity_id in target_ids]
        refresh_before_fetch_ids = [entity_id for entity_id in ctx.entity_ids if entity_id in shortfall_ids]
    if not target_entity_ids:
        issues = current_gate_issues(ctx.entity_ids)
        if issues:
            _record_download_repair(ctx, issues)
            _write_download_availability(ctx, {}, source="download_fetch_failed")
            return StageResult(
                ExecutionStage.DOWNLOAD_FETCH,
                AUTO,
                StageStatus.FAILED,
                "persisted download artifacts do not satisfy the frozen target set:\n  - "
                + "\n  - ".join(issue_messages(issues[:10])),
                fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
                issue_records=issues,
            )
        capacity_result = _resolve_download_content_capacity_shortfall(
            ctx,
            _download_content_capacity_preflight(ctx),
        )
        if capacity_result is not None:
            return capacity_result
        _write_download_availability(ctx, {}, source="download_fetch_passed")
        return StageResult(
            ExecutionStage.DOWNLOAD_FETCH,
            AUTO,
            StageStatus.DONE,
            "current persisted download gate already passes",
        )
    if refresh_before_fetch_ids:
        _refresh_stale_source_plans_for_fetch(ctx, refresh_before_fetch_ids)
    if target_entity_ids != ctx.entity_ids:
        print(
            "[task execute] download object repair/refresh: "
            + ", ".join(target_entity_ids)
        )
    download_lane = download_lane_override or _download_retry_lane(ctx, target_entity_ids)
    active_download_lanes = _download_auto_research_lanes(ctx)
    if download_lane == "all" and active_download_lanes and len(active_download_lanes) == 1:
        download_lane = next(iter(active_download_lanes))
    if download_lane != "all":
        print(f"[task execute] download lane-scoped repair: lane={download_lane}")
    fallback_entity_type = (
        ctx.spec.scope.entity_types[0] if ctx.spec.scope.entity_types else ""
    )
    grouped_targets = _entity_ids_grouped_by_type(
        ctx,
        target_entity_ids,
        fallback_type=fallback_entity_type,
    )
    try:
        grouped_items = list(grouped_targets.items())
        for group_index, (group_type, group_ids) in enumerate(grouped_items):
            if not group_ids:
                continue
            handle_download(
                execution_id=ctx.execution_id,
                entity_ids=group_ids,
                entity_type=group_type,
                lane=download_lane,
                max_workers=max(1, int(ctx.max_workers or 1)),
                defer_gate=group_index < len(grouped_items) - 1,
            )
    except SystemExit as exc:
        code = int(getattr(exc, "code", 1) or 0)
        if code not in (0,):
            issues = current_gate_issues(target_entity_ids)
            if not issues:
                issues = [data_issue(
                    DataIssueCode.INTERNAL_UNEXPECTED,
                    stage=DataIssueStage.DOWNLOAD_FETCH,
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message="download handler exited non-zero without persisted gate issues",
                    attributes={"exitCode": code},
                )]
            rendered_issues = issue_messages(issues)
            _record_download_repair(ctx, issues)
            _write_download_availability(ctx, {}, source="download_fetch_failed")
            message = f"download gate failed with exit code {code}"
            if issues:
                message += ": " + "; ".join(rendered_issues[:5])
            return StageResult(
                ExecutionStage.DOWNLOAD_FETCH,
                AUTO,
                StageStatus.FAILED,
                message,
                fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
                issue_records=issues,
            )
    except Exception as exc:  # noqa: BLE001
        issue = data_issue(
            DataIssueCode.INTERNAL_UNEXPECTED,
            stage=DataIssueStage.DOWNLOAD_FETCH,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            message="download handler raised an unexpected exception",
            attributes={"errorType": type(exc).__name__},
        )
        _record_download_repair(ctx, [issue])
        _write_download_availability(ctx, {}, source="download_fetch_failed")
        return StageResult(
            ExecutionStage.DOWNLOAD_FETCH,
            AUTO,
            StageStatus.FAILED,
            f"download handler failed: {type(exc).__name__}",
            fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
            issue_records=[issue],
        )
    issues = current_gate_issues(target_entity_ids)
    if issues:
        rendered_issues = issue_messages(issues)
        _record_download_repair(ctx, issues)
        _write_download_availability(ctx, {}, source="download_fetch_failed")
        return StageResult(
            ExecutionStage.DOWNLOAD_FETCH,
            AUTO,
            StageStatus.FAILED,
            "download gate failed:\n  - " + "\n  - ".join(rendered_issues[:10]),
            fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
            issue_records=issues,
        )
    repair_path = _download_repair_path(ctx)
    if repair_path.is_file():
        repair_path.unlink()
    _write_download_availability(ctx, {}, source="download_fetch_passed")
    capacity_result = _resolve_download_content_capacity_shortfall(
        ctx,
        _download_content_capacity_preflight(ctx),
    )
    if capacity_result is not None:
        return capacity_result
    return StageResult(
        ExecutionStage.DOWNLOAD_FETCH,
        AUTO,
        StageStatus.DONE,
        "fetched sources for " + ", ".join(target_entity_ids),
    )

def _run_build_prepare(ctx: ExecutionContext) -> StageResult:
    from content.homepage.homepage import homepage_runtime_spec, validate_entity_page_inputs
    from content.homepage.homepage_prepare import prepare_entity_pages
    if _entity_homepages_per_target(ctx) <= 0:
        return StageResult(
            ExecutionStage.BUILD_PREPARE,
            AUTO,
            StageStatus.DONE,
            "entityHomepagesPerTarget=0；图片作品-only 批次跳过主页输入准备",
        )
    active_spec = homepage_runtime_spec(ctx.execution_id, _active_spec(ctx))
    _prune_inactive_entity_homepage_artifacts(ctx, reason="build_prepare active target sync")
    inputs_dir, refs = prepare_entity_pages(ctx.execution_id, active_spec)
    issues = validate_entity_page_inputs(ctx.execution_id, active_spec)
    if issues:
        return StageResult(
            ExecutionStage.BUILD_PREPARE,
            AUTO,
            StageStatus.FAILED,
            "主页输入未就绪，需回到 download_plan/download_fetch 修复上游来源:\n  - "
            + "\n  - ".join(issue_messages(issues[:10])),
            fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
            issue_records=issues,
        )
    return StageResult(ExecutionStage.BUILD_PREPARE, AUTO, StageStatus.DONE, f"下发 {len(refs)} 个主页产出契约 -> {inputs_dir}")

def _run_build_validate(ctx: ExecutionContext) -> StageResult:
    from content.homepage.homepage import homepage_runtime_spec
    from content.homepage.homepage_release_validation import validate_entity_pages
    from verify.verify_homepage_media_completeness import homepage_media_completeness_report
    if _entity_homepages_per_target(ctx) <= 0:
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.DONE,
            "entityHomepagesPerTarget=0；图片作品-only 批次跳过主页采纳门",
        )
    runtime_spec = homepage_runtime_spec(ctx.execution_id, _active_spec(ctx))
    issues = validate_entity_pages(ctx.execution_id, runtime_spec)
    if issues:
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.FAILED,
            "主页采纳门未过:\n  - " + "\n  - ".join(issues[:10]),
            fallback_stage=ExecutionStage.BUILD_HOMEPAGE,
            issue_records=stage_issues(
                ExecutionStage.BUILD_VALIDATE,
                issues,
                code=DataIssueCode.QUALITY_FAILED,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            ),
        )
    media_report = homepage_media_completeness_report(ctx.execution_id)
    if not bool(media_report.get("passed")):
        media_issues = [
            "{code} {ref}: {message}".format(
                code=str(row.get("code") or "DATA.MEDIA.DOWNLOAD_INCOMPLETE"),
                ref=str(row.get("ref") or ""),
                message=str(row.get("message") or "homepage media closure failed"),
            )
            for row in (media_report.get("issues") or [])
            if isinstance(row, Mapping)
        ]
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.FAILED,
            "主页图片完整性门未过:\n  - " + "\n  - ".join(media_issues[:10]),
            fallback_stage=ExecutionStage.DOWNLOAD_FETCH,
            issue_records=stage_issues(
                ExecutionStage.BUILD_VALIDATE,
                media_issues or ["homepage media completeness report did not pass"],
                code=DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE,
                recovery=DataRecoveryAction.REWIND_DOWNLOAD,
            ),
        )
    review_issues = _run_homepage_independent_reviews(ctx, runtime_spec)
    if review_issues:
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.FAILED,
            "主页独立审阅未过:\n  - " + "\n  - ".join(review_issues[:10]),
            fallback_stage=ExecutionStage.BUILD_HOMEPAGE,
            issue_records=stage_issues(
                ExecutionStage.BUILD_VALIDATE,
                review_issues,
                code=DataIssueCode.AGENT_REVIEW_INVALID,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            ),
        )
    return StageResult(ExecutionStage.BUILD_VALIDATE, AUTO, StageStatus.DONE, "所有 coverage 实体主页及独立审阅达标")

def _run_homepage_independent_reviews(
    ctx: ExecutionContext,
    runtime_spec: dict[str, Any],
) -> list[str]:
    """Run one read-only Cursor reviewer per finalized homepage when evidence is pending."""
    from content.execution.agent.agent_runner import _redact_managed_secret
    from content.execution.agent.agent_worker import _default_managed_agent_runner_isolated
    from content.execution.controller.homepage_authoring import _homepage_independent_review_issues
    from governance.coverage.entity_extract import entity_ref
    from core.prompt_render import render as render_prompt
    from content.source.source_unit import resolve_entity_object_dir
    from content.homepage.homepage_review import (
        apply_independent_homepage_review,
        homepage_media_review_dispositions,
    )

    from content.execution.model_contract import execution_model_pair_for_execution

    model_pair = execution_model_pair_for_execution(ctx.execution_id)
    review_model = model_pair.reviewer.model_id
    review_model_family = model_pair.reviewer.family.value
    author_model = model_pair.author.model_id
    author_model_family = model_pair.author.family.value
    if review_model == author_model or review_model_family == author_model_family:
        return ["independent reviewer model family must differ from author model family"]
    issues: list[str] = []

    def _valid_payload(payload: Any, *, object_ref: str) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("executionId") != ctx.execution_id or payload.get("objectRef") != object_ref:
            return False
        try:
            from core.schema import assert_valid

            assert_valid(
                payload,
                "content",
                "homepage_reviewer_response",
                label=f"homepage_reviewer_response:{object_ref}",
            )
        except ValueError:
            return False
        return True

    def _payload_from_outcome(outcome: Mapping[str, Any], *, object_ref: str) -> dict[str, Any] | None:
        text = str(outcome.get("result") or "").strip()
        candidates = [text]
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
        if fenced:
            candidates.insert(0, fenced.group(1))
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            candidates.append(text[first : last + 1])
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except (TypeError, ValueError):
                continue
            if _valid_payload(payload, object_ref=object_ref):
                return payload
        return None
    for target in ((runtime_spec.get("scope") or {}).get("coverageTargets") or []):
        if not isinstance(target, Mapping):
            continue
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, etype = require_domain_etype(target.get("entityType"), context=name)
        obj = resolve_entity_object_dir(ctx.execution_id, name, etype_hint=etype)
        review_dir = obj / "5.review"
        attestation_path = review_dir / "attestation.json"
        if not attestation_path.is_file():
            issues.append(f"{name}: review attestation missing")
            continue
        attestation = read_json(attestation_path)
        if str((attestation.get("independentReviewer") or {}).get("status") or "") == "passed":
            recorded_issues = _homepage_independent_review_issues(ctx, domain, etype, name)
            if not recorded_issues:
                continue
            issues.extend(recorded_issues)
            continue
        output_path = review_dir / "reviewer_response.pending.json"
        output_path.unlink(missing_ok=True)
        object_ref = entity_ref(domain, etype, name)
        manifest = read_json(obj / "manifest.json")
        media_policy = json.dumps(
            {"assets": homepage_media_review_dispositions(manifest)},
            ensure_ascii=False,
            sort_keys=True,
        )
        prompt = render_prompt(
            "homepage_independent_review",
            task_vars={
                "object_ref": object_ref,
                "object_dir": str(obj),
                "output_path": str(output_path),
                "media_policy": media_policy,
            },
        )
        review_ctx = ExecutionContext(
            execution_id=ctx.execution_id,
            entity_ids=[name],
            spec=ctx.spec.to_dict(),
            managed=True,
            runtime=ctx.runtime,
            max_workers=_SERIAL_DOWNLOAD_WORKER_COUNT,
            model=review_model,
            agent_provider=ctx.agent_provider,
            release_only=ctx.release_only,
        )

        def _complete(path: Path = output_path) -> bool:
            if not path.is_file():
                return False
            try:
                payload = read_json(path)
            except Exception:  # noqa: BLE001
                return False
            return _valid_payload(payload, object_ref=object_ref)

        # The review response file is only a response transport.  The canonical
        # attestation must retain the Cursor SDK run identity, so this isolated
        # worker must finish normally rather than taking the contract-output
        # shortcut used by non-attested helper stages.
        outcome = _default_managed_agent_runner_isolated(review_ctx, prompt)
        payload: dict[str, Any] | None = read_json(output_path) if _complete() else None
        if payload is None and str(outcome.get("status") or "") == "finished":
            payload = _payload_from_outcome(outcome, object_ref=object_ref)
            if payload is not None:
                write_json(output_path, payload)
        if str(outcome.get("status") or "") != "finished" or payload is None:
            outcome_status = str(outcome.get("status") or "error")
            error_text = _redact_managed_secret(
                str(outcome.get("error") or "invalid reviewer output")
            )
            issue_code = (
                DataIssueCode.AGENT_REVIEW_INVALID
                if outcome_status == "finished"
                else DataIssueCode.AGENT_REVIEW_UNAVAILABLE
            )
            review_issue = data_issue(
                issue_code,
                stage=DataIssueStage.REVIEW,
                ref=object_ref,
                lane=DataIssueLane.HOMEPAGE,
                recovery=DataRecoveryAction.STOP,
                message=(
                    "independent reviewer returned invalid response"
                    if issue_code == DataIssueCode.AGENT_REVIEW_INVALID
                    else "independent reviewer model did not finish"
                ),
                attributes={
                    "model": review_model,
                    "modelFamily": review_model_family,
                    "outcomeStatus": outcome_status,
                    "errorCode": str(outcome.get("errorCode") or ""),
                },
            )
            failure_root = (
                execution_root(ctx.execution_id)
                / "evidence/reviewer_failures"
            )
            failure_root.mkdir(parents=True, exist_ok=True)
            failure_path = failure_root / (
                hashlib.sha256(object_ref.encode("utf-8")).hexdigest()[:20] + ".json"
            )
            write_json(
                failure_path,
                {
                    "schema": "quwoquan_data.homepage_review_failure",
                    "executionId": ctx.execution_id,
                    "objectRef": object_ref,
                    "model": review_model,
                    "modelFamily": review_model_family,
                    "status": outcome_status,
                    "issue": review_issue.as_dict(),
                    "runId": str(outcome.get("runId") or ""),
                    "agentId": str(outcome.get("agentId") or ""),
                    "requestId": str(outcome.get("requestId") or ""),
                    "durationMs": outcome.get("durationMs"),
                    "errorCode": str(outcome.get("errorCode") or ""),
                    "error": error_text,
                    "result": _redact_managed_secret(str(outcome.get("result") or ""))[:4000],
                    "recordedAt": store.now_iso(),
                },
            )
            output_path.unlink(missing_ok=True)
            issues.append(str(review_issue))
            continue
        output_path.unlink(missing_ok=True)
        bound = apply_independent_homepage_review(
            review_dir=review_dir,
            provider="cursor_sdk",
            model=review_model,
            model_family=review_model_family,
            run_id=str(outcome.get("runId") or ""),
            result_payload=payload,
        )
        issues.extend(f"{name}: {item}" for item in bound)
    return issues
