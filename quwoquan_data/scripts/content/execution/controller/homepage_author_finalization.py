"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.support import Any, DataIssueCode, DataIssueStage, DataIssueLane, DataRecoveryAction, ExecutionContext, Mapping, Path, _IMAGE_SOURCE_TEXT_NOISE_PATTERNS, _IMAGE_SOURCE_TEXT_NOISE_TOKENS, _active_spec, _is_homepage_only_execution, data_issue, execution_root, load_execution_state, os, re, read_json, require_domain_etype, save_execution_state, shutil, store, write_json
from content.execution.controller.homepage_author_evidence import (
    _homepage_finalization_unexpected_issue,
    _write_homepage_author_evidence,
)


def _write_homepage_repair_report(
    ctx: ExecutionContext,
    *,
    object_dir: Path,
    ref: str,
    materialization_messages: tuple[str, ...],
    repair_strategy: str,
) -> Path:
    """Persist typed, object-scoped feedback for the next homepage author run."""
    from content.execution.stage_reports import build_repair_report

    if repair_strategy not in {"local_edit", "rebuild_from_frozen_base"}:
        raise ValueError("homepage repair strategy is invalid")
    issues = tuple(
        data_issue(
            DataIssueCode.QUALITY_FAILED,
            stage=DataIssueStage.BUILD_HOMEPAGE,
            lane=DataIssueLane.HOMEPAGE,
            recovery=DataRecoveryAction.RETRY_AGENT,
            ref=ref,
            message=message,
            attributes={"repairStrategy": repair_strategy},
        )
        for message in materialization_messages
    )
    if not issues:
        raise ValueError("homepage repair report requires materialization issues")
    report_path = object_dir / "5.review" / "repair_report.json"
    write_json(
        report_path,
        build_repair_report(
            execution_id=ctx.execution_id,
            command="homepage",
            ref=ref,
            failed_stage=DataIssueStage.BUILD_HOMEPAGE.value,
            failed_gate="homepage_materialization",
            issues=issues,
            fallback_stage=DataIssueStage.BUILD_HOMEPAGE.value,
            rerun_chain=["author", "materialize"],
        ),
    )
    return report_path


def _normalize_homepage_document_title(*, entity_name: str, draft_text: str) -> str:
    """Add the deterministic document title when an authored body omitted it.

    The entity identity is frozen by the execution target.  Supplying a missing
    H1 is document framing, not generated content; duplicate or mismatched H1
    values remain review failures and must be repaired by the author.
    """
    from core.section_outline import match_heading

    h1_count = sum(
        1
        for line in draft_text.splitlines()
        if (heading := match_heading(line)) is not None and int(heading[0]) == 1
    )
    if h1_count:
        return draft_text
    return f"# {entity_name}\n\n{draft_text.lstrip()}"


def _finalize_managed_homepage_outputs(
    ctx: ExecutionContext,
    _prompts: list[str],
    outcomes: list["ManagedAgentJobOutcome"],
) -> tuple["ManagedAgentJobOutcome", ...]:
    """Finalize a completed homepage author run before materializing its page."""
    from content.execution.agent.outcome import ManagedAgentJobOutcome
    from core.article_package import compute_document_sha256
    from core.entity_object import parse_entity_ref
    from content.post.article.draft_io import is_placeholder
    from core.schema import assert_valid
    from content.homepage.homepage_review import _entity_draft_dir
    from content.homepage.homepage_release import materialize_entity_page
    finalized: list[ManagedAgentJobOutcome] = []
    for job_outcome in outcomes:
        if not job_outcome.succeeded:
            finalized.append(job_outcome)
            continue
        coordinates = parse_entity_ref(job_outcome.ref)
        if coordinates is None:
            finalized.append(
                job_outcome.with_gate_issues(
                    ("homepage author outcome missing canonical entity ref",)
                )
            )
            continue
        domain, et, entity = coordinates
        target = next(
            (
                row
                for row in ctx.spec.scope.coverage_targets
                if row.name == entity
            ),
            None,
        )
        if not target:
            finalized.append(
                job_outcome.with_gate_issues(
                    ("homepage author outcome entity is outside frozen target set",)
                )
            )
            continue
        target_domain, target_type = require_domain_etype(
            target.entity_type,
            context=entity,
        )
        if (domain, et) != (target_domain, target_type):
            finalized.append(
                job_outcome.with_gate_issues(
                    ("homepage author outcome entity ref type mismatches frozen target",)
                )
            )
            continue
        draft_dir = _entity_draft_dir(ctx.execution_id, domain, et, entity)
        draft_dir.mkdir(parents=True, exist_ok=True)
        meta_path = draft_dir / "draft_meta.json"
        meta = read_json(meta_path) if meta_path.is_file() else {}
        outcome = job_outcome.outcome
        run_id = outcome.run_id
        if not run_id:
            finalized.append(job_outcome)
            continue
        draft_page = draft_dir / "page.md"
        if not draft_page.is_file():
            messages = ("homepage author finished without 4.draft/page.md",)
            _write_homepage_repair_report(
                ctx,
                object_dir=draft_dir.parent,
                ref=job_outcome.ref,
                materialization_messages=messages,
                repair_strategy="rebuild_from_frozen_base",
            )
            finalized.append(job_outcome.with_gate_issues(messages))
            continue
        draft_text = draft_page.read_text(encoding="utf-8")
        # Typed failure protocol must win over placeholder detection: Agent may
        # correctly refuse to author and leave page.md untouched. Treat that as
        # a finished author pass so build_homepage can rewind source discovery.
        from core.homepage_source_failure import (
            SOURCE_RECOVERY_FAILURE_KINDS,
            entity_page_failure_issues,
            entity_page_failure_kind,
            read_entity_page_failure,
        )

        failure = read_entity_page_failure(draft_dir)
        if failure is not None:
            failure_problems = entity_page_failure_issues(failure, entity_name=entity)
            kind = entity_page_failure_kind(failure)
            if failure_problems:
                messages = tuple(
                    f"homepage author finished with invalid 4.draft/failure.json: {p}"
                    for p in failure_problems
                )
                _write_homepage_repair_report(
                    ctx,
                    object_dir=draft_dir.parent,
                    ref=job_outcome.ref,
                    materialization_messages=messages,
                    repair_strategy="rebuild_from_frozen_base",
                )
                finalized.append(job_outcome.with_gate_issues(messages))
                continue
            if kind in SOURCE_RECOVERY_FAILURE_KINDS:
                reasons = [
                    str(item).strip()
                    for item in (failure.get("reasons") or [])
                    if str(item).strip()
                ]
                (draft_dir.parent / "5.review" / "repair_report.json").unlink(
                    missing_ok=True
                )
                meta.update(
                    {
                        "generator": "agent",
                        "status": "failed",
                        "provider": outcome.provider.value,
                        "model": ctx.model,
                        "agentRunId": run_id,
                        "agentId": outcome.agent_id or None,
                        "draftSha256": None,
                        "selfCheck": {
                            "status": "failed",
                            "issues": [
                                (
                                    f"failureProtocol:{kind.value}: {reasons[0]}"
                                    if reasons
                                    else f"failureProtocol:{kind.value}"
                                )
                            ],
                        },
                        "sessionTrace": "build_homepage",
                        "updatedAt": store.now_iso(),
                        "finalizedFromAgentRunHistory": True,
                    }
                )
                assert_valid(meta, "content", "draft_meta", label=f"draft_meta:{entity}")
                write_json(meta_path, meta)
                try:
                    _write_homepage_author_evidence(
                        ctx,
                        draft_dir=draft_dir,
                        domain=domain,
                        etype=et,
                        entity=entity,
                        outcome=outcome,
                        draft_meta=meta,
                        source_failure=failure,
                    )
                except (OSError, ValueError, TypeError) as exc:
                    finalized.append(
                        job_outcome.with_gate_issues(
                            (f"homepage author evidence failed: {exc}",)
                        )
                    )
                    continue
                finalized.append(job_outcome)
                continue
        if is_placeholder(draft_text):
            messages = ("homepage author finished with placeholder 4.draft/page.md",)
            _write_homepage_repair_report(
                ctx,
                object_dir=draft_dir.parent,
                ref=job_outcome.ref,
                materialization_messages=messages,
                repair_strategy="rebuild_from_frozen_base",
            )
            finalized.append(job_outcome.with_gate_issues(messages))
            continue
        normalized_draft_text = _normalize_homepage_document_title(
            entity_name=entity,
            draft_text=draft_text,
        )
        if normalized_draft_text != draft_text:
            draft_page.write_text(normalized_draft_text, encoding="utf-8")
            draft_text = normalized_draft_text
        meta.update(
            {
                "generator": "agent",
                "status": "completed",
                "provider": outcome.provider.value,
                "model": ctx.model,
                "agentRunId": run_id,
                "agentId": outcome.agent_id or None,
                "draftSha256": compute_document_sha256(draft_text),
                "selfCheck": {"status": "passed", "issues": []},
                "sessionTrace": "build_homepage",
                "updatedAt": store.now_iso(),
                "finalizedFromAgentRunHistory": True,
            }
        )
        assert_valid(meta, "content", "draft_meta", label=f"draft_meta:{entity}")
        write_json(meta_path, meta)
        try:
            _write_homepage_author_evidence(
                ctx,
                draft_dir=draft_dir,
                domain=domain,
                etype=et,
                entity=entity,
                outcome=outcome,
                draft_meta=meta,
            )
        except (OSError, ValueError, TypeError) as exc:
            finalized.append(job_outcome.with_gate_issues((f"homepage author evidence failed: {exc}",)))
            continue
        try:
            materialize_issues = materialize_entity_page(
                ctx.execution_id,
                domain,
                et,
                entity,
            )
        except Exception as exc:  # noqa: BLE001
            issue = _homepage_finalization_unexpected_issue(entity, exc)
            finalized.append(job_outcome.with_gate_issues((issue.message,)))
            continue
        if materialize_issues:
            messages = tuple(str(item) for item in materialize_issues)
            _write_homepage_repair_report(
                ctx,
                object_dir=draft_dir.parent,
                ref=job_outcome.ref,
                materialization_messages=messages,
                repair_strategy="rebuild_from_frozen_base",
            )
            finalized.append(
                job_outcome.with_gate_issues(
                    messages,
                )
            )
            continue
        (draft_dir.parent / "5.review" / "repair_report.json").unlink(missing_ok=True)
        finalized.append(job_outcome)
    return tuple(finalized)

def _finalize_existing_object_queue_author_outputs(ctx: ExecutionContext, refs: list[str]) -> int:
    """补齐外部 fanout/object_queue author-runner 已成功草稿的 provenance。
    外部 runner 的业务真相源是 object_queue。只有 job=STATE_SUCCEEDED 且
    draft.article.md 已真实落盘、非占位时，才允许把 pending meta 升级为
    generator=agent；这避免把队列状态或空回复误认成 author 完成。
    """
    from content.post.content_review import generator_provenance_issues
    from content.post.article.draft_io import (
        compute_draft_provenance_facts,
        draft_article_path,
        draft_meta_path,
        is_placeholder,
        read_draft_meta,
        read_writing_pack,
    )
    from content.execution.queue.core import (
        STATE_SUCCEEDED,
        _read_job,
        stable_job_id,
    )
    finalized = 0
    for ref in refs:
        job_id = stable_job_id(ctx.execution_id, ref, "author")
        try:
            job = _read_job(ctx.execution_id, job_id)
        except Exception:  # noqa: BLE001
            continue
        if job.state is not STATE_SUCCEEDED:
            continue
        try:
            article_path = draft_article_path(ctx.execution_id, ref)
        except KeyError:
            continue
        if not article_path.is_file():
            continue
        article = article_path.read_text(encoding="utf-8")
        if is_placeholder(article):
            continue
        meta = read_draft_meta(ctx.execution_id, ref) or {}
        if not generator_provenance_issues(meta):
            continue
        pack = read_writing_pack(ctx.execution_id, ref) or {}
        cited_paths = meta.get("citedSourcePaths") or pack.get("sourcePaths") or []
        facts = compute_draft_provenance_facts(
            ctx.execution_id,
            ref,
            article_markdown=article,
            cited_source_paths=[str(item) for item in cited_paths],
        )
        enriched_meta = dict(meta)
        enriched_meta.update(
            {
                "ref": ref,
                "generator": "agent",
                "status": "completed",
                "model": meta.get("model") or ctx.model,
                "agentRunId": meta.get("agentRunId") or job.agent_run_id,
                "agentId": meta.get("agentId") or "",
                "citedSourcePaths": [str(item) for item in cited_paths],
                "promptSha256": facts.get("promptSha256"),
                "writingPackSha256": facts.get("writingPackSha256"),
                "sourceBundleSha256": facts.get("sourceBundleSha256"),
                "draftSha256": facts.get("draftSha256"),
                "selfCheck": {"status": "passed", "issues": []},
                "updatedAt": store.now_iso(),
                "finalizedFromObjectQueue": True,
            }
        )
        write_json(draft_meta_path(ctx.execution_id, ref), enriched_meta)
        finalized += 1
    return finalized
