"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type
from content.execution.support import Any, DataIssueCode, DataIssueStage, DataIssueLane, DataRecoveryAction, ExecutionContext, Mapping, Path, _IMAGE_SOURCE_TEXT_NOISE_PATTERNS, _IMAGE_SOURCE_TEXT_NOISE_TOKENS, _active_spec, _is_homepage_only_execution, data_issue, execution_root, load_execution_state, os, re, read_json, require_domain_etype, save_execution_state, shutil, store, write_json
from content.execution.controller.homepage_author_evidence import (
    _homepage_finalization_unexpected_issue,
    _write_homepage_author_evidence,
)
def _finalize_managed_homepage_outputs(
    ctx: ExecutionContext,
    prompts: list[str],
    outcomes: list[dict[str, Any]],
) -> int:
    """Finalize a completed homepage author run before materializing its page."""
    from content.execution.agent.agent_checkpoint import _managed_prompt_entity
    from core.article_package import compute_document_sha256
    from content.post.article.draft_io import is_placeholder
    from core.schema import assert_valid
    from content.homepage.homepage_review import _entity_draft_dir
    from content.homepage.homepage_release import materialize_entity_page
    finalized = 0
    for index, outcome in enumerate(outcomes):
        if str(outcome.get("status") or "") != "finished":
            continue
        prompt = prompts[index] if index < len(prompts) else ""
        entity = _managed_prompt_entity(prompt)
        if not entity:
            continue
        etype = coverage_entity_type(ctx.spec)
        target = next(
            (
                row
                for row in ctx.spec.scope.coverage_targets
                if row.name == entity
            ),
            None,
        )
        if not target:
            continue
        domain, et = require_domain_etype(target.entity_type, context=entity)
        draft_dir = _entity_draft_dir(ctx.execution_id, domain, et, entity)
        draft_dir.mkdir(parents=True, exist_ok=True)
        meta_path = draft_dir / "draft_meta.json"
        meta = read_json(meta_path) if meta_path.is_file() else {}
        run_id = str(outcome.get("runId") or "").strip()
        if not run_id:
            continue
        draft_page = draft_dir / "page.md"
        if not draft_page.is_file():
            outcome["status"] = "error"
            outcome["error"] = "homepage author finished without 4.draft/page.md"
            continue
        draft_text = draft_page.read_text(encoding="utf-8")
        if is_placeholder(draft_text):
            outcome["status"] = "error"
            outcome["error"] = "homepage author finished with placeholder 4.draft/page.md"
            continue
        meta.update(
            {
                "generator": "agent",
                "status": "completed",
                "provider": str(outcome.get("agentProvider") or meta.get("provider") or ctx.agent_provider),
                "model": ctx.model,
                "agentRunId": run_id,
                "agentId": outcome.get("agentId"),
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
            outcome["status"] = "error"
            outcome["error"] = f"homepage author evidence failed: {exc}"
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
            outcome["status"] = "error"
            outcome["error"] = issue.message
            outcome["issueRecords"] = [issue.as_dict()]
            continue
        if materialize_issues:
            outcome["status"] = "error"
            outcome["error"] = (
                "homepage finalize after agent failed: "
                + "; ".join(str(item) for item in materialize_issues[:8])
            )
            outcome["gateIssues"] = [str(item) for item in materialize_issues[:20]]
            continue
        finalized += 1
    return finalized

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
    from content.execution.queue.core import STATE_SUCCEEDED, _job_path, stable_job_id
    finalized = 0
    for ref in refs:
        job_id = stable_job_id(ctx.execution_id, ref, "author")
        try:
            job = read_json(_job_path(ctx.execution_id, job_id))
        except Exception:  # noqa: BLE001
            continue
        if str(job.get("state") or "") != STATE_SUCCEEDED:
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
                "agentRunId": meta.get("agentRunId") or job.get("lastAgentRunId"),
                "agentId": meta.get("agentId") or job.get("lastAgentId"),
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
