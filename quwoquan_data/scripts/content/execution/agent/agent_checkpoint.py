"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type
from content.execution.support import Any, Callable, ExecutionContext, ExecutionStateStatus, ExecutionStateTransition, Mapping, Sequence, _active_spec, _active_target, _download_repair_lanes, image_asset_strategy, image_strategy_allows_ai_generated, issue_messages, json, re, read_json, require_domain_etype, save_execution_state, store, write_json


def _checkpoint_is_done(ctx: ExecutionContext, stage: str) -> tuple[bool, list[str]]:
    from content.execution.controller.homepage_authoring import _content_plan_done, _drafts_authored, _homepages_done
    from content.execution.recovery.stage_reset import _source_plan_filled
    checkers: dict[str, Callable[[ExecutionContext], tuple[bool, list[str]]]] = {
        "download_plan": _source_plan_filled,
        "build_homepage": _homepages_done,
        "content_plan": _content_plan_done,
        "post_author": _drafts_authored,
    }
    checker = checkers.get(stage)
    return checker(ctx) if checker else (False, [f"unsupported managed checkpoint {stage}"])

def _managed_author_ref(prompt: str) -> str:
    for line in prompt.splitlines():
        prefix = "内容 ref:"
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""

def _managed_author_failure_refs(
    outcomes: Sequence["ManagedAgentJobOutcome"],
) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for outcome in outcomes:
        if outcome.succeeded:
            continue
        ref = outcome.ref
        if not ref or ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs

def _managed_consecutive_no_start_infra_failures(state: ExecutionStateTransition, *, stage: str) -> int:
    from content.execution.agent.history import state_managed_agent_runs

    recovery_cutoffs = state.managed_infra_recovery_cutoffs
    recovery_cutoff = ""
    if isinstance(recovery_cutoffs, Mapping):
        recovery_cutoff = str(recovery_cutoffs.get(stage) or "")
    count = 0
    for run in reversed(state_managed_agent_runs(state)):
        if run.stage.value != stage:
            if count:
                break
            continue
        finished_at = run.finished_at
        if recovery_cutoff and finished_at and finished_at <= recovery_cutoff:
            break
        infra_failures = run.infrastructure_failures
        started = run.started_count
        finished = run.finished_count
        if infra_failures > 0 and started == 0 and finished == 0:
            count += 1
            continue
        break
    return count

def _managed_infra_failed_refs_after_checkpoint(
    ctx: ExecutionContext,
    state: ExecutionStateTransition,
    *,
    stage: str,
    checkpoint_issues: Sequence[str] | None = None,
) -> list[str]:
    from content.execution.agent.history import last_managed_agent_run

    if stage != "post_author":
        return []
    refs = [str(item).strip() for item in (checkpoint_issues or []) if str(item).strip()]
    if refs:
        return refs
    last_run = last_managed_agent_run(state)
    if last_run is not None:
        return _managed_author_failure_refs(last_run.outcomes)
    _ok, issues = _checkpoint_is_done(ctx, stage)
    return [str(item).strip() for item in issues if str(item).strip()]

def _handle_managed_infra_budget_exhausted(
    ctx: ExecutionContext,
    state: ExecutionStateTransition,
    *,
    stage: str,
    infra_used: int,
    infrastructure_failures: int,
    checkpoint_issues: Sequence[str] | None = None,
) -> int | None:
    from content.execution.agent.history import last_managed_agent_run, save_managed_agent_run

    ok_after_failures, issues_after_failures = _checkpoint_is_done(ctx, stage)
    if checkpoint_issues is None:
        checkpoint_issues = issues_after_failures
    if ok_after_failures:
        last_run = last_managed_agent_run(state)
        if last_run is not None:
            save_managed_agent_run(
                state,
                last_run.with_recovery(
                    recovered_at=store.now_iso(),
                    recovery_reason=(
                        f"{stage} checkpoint gate passed despite "
                        f"{infrastructure_failures} infrastructure failure(s)"
                    ),
                ),
            )
        state.status = ExecutionStateStatus.RUNNING
        state.failed_objects = []
        state.next_action = (
            f"continue {stage}: checkpoint gate passed despite "
            f"{infrastructure_failures} infrastructure failure(s)"
        )
        state.heartbeat_at = store.now_iso()
        save_execution_state(state)
        return 0
    failed_refs = _managed_infra_failed_refs_after_checkpoint(
        ctx,
        state,
        stage=stage,
        checkpoint_issues=checkpoint_issues,
    )
    state.status = ExecutionStateStatus.MANUAL_REQUIRED
    state.failed_objects = [
        f"{stage}:{ref}: infrastructure did not start"
        for ref in failed_refs
    ] or list(checkpoint_issues or state.failed_objects or [])
    state.next_action = (
        f"{stage} infrastructure failed after {infra_used} attempts; "
        f"{infrastructure_failures} agent job(s) did not start"
    )
    save_execution_state(state)
    return 1

def _managed_prompt_entity(prompt: str) -> str:
    for line in prompt.splitlines():
        prefix = "对象:"
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""

def _managed_prompt_lane(prompt: str) -> str:
    match = re.search(r"\[AGENT_LANE:(homepage|article|image)\]", prompt)
    return match.group(1) if match else "default"

def _managed_checkpoint_job_issues(
    ctx: ExecutionContext,
    *,
    stage: str,
    prompt: str,
) -> list[str]:
    from content.execution.recovery.download_gate import _download_research_lane_issues
    from content.execution.recovery.download_unresolved import _pending_download_repair_unresolved
    from content.execution.controller.homepage_author_evidence import _managed_image_author_meta_issues
    if stage == "download_plan":
        lane = _managed_prompt_lane(prompt)
        entity = _managed_prompt_entity(prompt)
        if lane not in {"homepage", "article", "image", "video"} or not entity:
            return [f"download_plan prompt missing target lane/entity: lane={lane!r}, entity={entity!r}"]
        etype = coverage_entity_type(ctx.spec)
        issues = issue_messages(
            _download_research_lane_issues(ctx, entity, etype, lane)
        )
        pending_repair = _pending_download_repair_unresolved(ctx).get(entity) or {}
        for repair_lane in (lane, "download"):
            for issue in pending_repair.get(repair_lane) or []:
                text = str(issue or "").strip()
                if text and text not in issues:
                    issues.append(text)
        return issues
    if stage == "post_author":
        from content.post import object_index as content_object
        from content.post.article.draft_io import draft_article_path, is_placeholder, read_draft_meta, read_writing_pack
        ref = _managed_author_ref(prompt)
        if not ref:
            return ["post_author prompt missing content ref"]
        try:
            pack = read_writing_pack(ctx.execution_id, ref) or {}
        except KeyError:
            pack = {}
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        is_image_carrier = (
            str(pack.get("carrier") or "") == "image"
            or str(coords.get("contentType") or "") == "image"
        )
        is_video_carrier = (
            str(pack.get("carrier") or "") == "video"
            or str(coords.get("contentType") or "") == "video"
        )
        if is_video_carrier:
            from content.post.video.authoring import video_author_issues

            return issue_messages(
                video_author_issues(
                    ctx.execution_id,
                    ref,
                    require_agent_run=False,
                )
            )
        if is_image_carrier:
            return _managed_image_author_meta_issues(
                read_draft_meta(ctx.execution_id, ref),
                writing_pack=pack,
                require_agent_run=False,
            )
        try:
            article_path = draft_article_path(ctx.execution_id, ref)
        except KeyError as exc:
            return [f"{ref}: draft package not registered after agent finished: {exc}"]
        if not article_path.is_file():
            return [f"{ref}: agent finished but did not write {article_path}"]
        try:
            article_text = article_path.read_text(encoding="utf-8")
        except OSError as exc:
            return [f"{ref}: agent finished but draft is unreadable: {exc}"]
        if is_placeholder(article_text):
            return [f"{ref}: agent finished but draft remains placeholder"]
        meta = read_draft_meta(ctx.execution_id, ref) or {}
        generator = str(meta.get("generator") or "").strip()
        if generator != "agent":
            return [
                f"{ref}: agent finished but draft_meta.generator is "
                f"{generator or '<missing>'}, expected agent"
            ]
        return []
    return []

def _finalize_managed_author_outputs(
    ctx: ExecutionContext,
    prompts: list[str],
    outcomes: list["ManagedAgentJobOutcome"],
) -> None:
    """用确定性 helper 补齐 Agent 草稿的 run ID 和四类 provenance hash。"""
    from content.execution.controller.homepage_author_evidence import _managed_image_author_meta_issues
    from content.post.article.draft_io import (
        compute_draft_provenance_facts,
        draft_article_path,
        draft_meta_path,
        is_placeholder,
        read_draft_meta,
        read_writing_pack,
    )
    from content.execution.agent.outcome import ManagedAgentJobOutcome
    from content.execution.controller.post_author_evidence import (
        write_post_author_evidence,
    )

    for job_outcome in outcomes:
        if not job_outcome.succeeded:
            continue
        outcome = job_outcome.outcome
        job_index = job_outcome.job_index
        if job_index < 0 or job_index >= len(prompts):
            continue
        ref = _managed_author_ref(prompts[job_index])
        if not ref:
            continue
        meta = read_draft_meta(ctx.execution_id, ref) or {}
        pack = read_writing_pack(ctx.execution_id, ref) or {}
        is_image_carrier = str(pack.get("carrier") or "") == "image"
        is_video_carrier = str(pack.get("carrier") or "") == "video"
        if is_video_carrier:
            from content.post.video.authoring import finalize_video_author_meta

            finalize_video_author_meta(
                ctx.execution_id,
                ref,
                run_id=outcome.run_id or str(meta.get("agentRunId") or ""),
                agent_id=outcome.agent_id or meta.get("agentId"),
                model=str(meta.get("model") or ctx.model or ""),
            )
            write_post_author_evidence(ctx, ref=ref, outcome=outcome)
            continue
        if is_image_carrier:
            if _managed_image_author_meta_issues(meta, writing_pack=pack, require_agent_run=False):
                continue
            title = str(meta.get("title") or "").strip()
            caption = str(meta.get("caption") or "").strip()
            cited_paths = meta.get("citedSourcePaths") or pack.get("sourcePaths") or []
            visible_text = "\n\n".join(
                part
                for part in [
                    f"# {title}" if title else "",
                    caption,
                ]
                if str(part).strip()
            )
            facts = compute_draft_provenance_facts(
                ctx.execution_id,
                ref,
                article_markdown=visible_text,
                cited_source_paths=[str(item) for item in cited_paths],
            )
            enriched_meta = dict(meta)
            enriched_meta.update(
                {
                    "ref": ref,
                    "generator": "image_evidence_pack",
                    "status": "completed",
                    "model": meta.get("model") or ctx.model,
                    "agentRunId": outcome.run_id or meta.get("agentRunId"),
                    "agentId": outcome.agent_id or meta.get("agentId"),
                    "citedSourcePaths": [str(item) for item in cited_paths],
                    "promptSha256": facts.get("promptSha256"),
                    "writingPackSha256": facts.get("writingPackSha256"),
                    "sourceBundleSha256": facts.get("sourceBundleSha256"),
                    "draftSha256": facts.get("draftSha256"),
                    "selfCheck": {"status": "passed", "issues": []},
                    "updatedAt": store.now_iso(),
                }
            )
            write_json(draft_meta_path(ctx.execution_id, ref), enriched_meta)
            write_post_author_evidence(ctx, ref=ref, outcome=outcome)
            continue
        article_path = draft_article_path(ctx.execution_id, ref)
        if not article_path.is_file():
            continue
        article = article_path.read_text(encoding="utf-8")
        if is_placeholder(article):
            continue
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
                "agentRunId": outcome.run_id or meta.get("agentRunId"),
                "agentId": outcome.agent_id or meta.get("agentId"),
                "citedSourcePaths": [str(item) for item in cited_paths],
                "promptSha256": facts.get("promptSha256"),
                "writingPackSha256": facts.get("writingPackSha256"),
                "sourceBundleSha256": facts.get("sourceBundleSha256"),
                "draftSha256": facts.get("draftSha256"),
                "selfCheck": {"status": "passed", "issues": []},
                "updatedAt": store.now_iso(),
            }
        )
        write_json(draft_meta_path(ctx.execution_id, ref), enriched_meta)
        write_post_author_evidence(ctx, ref=ref, outcome=outcome)
