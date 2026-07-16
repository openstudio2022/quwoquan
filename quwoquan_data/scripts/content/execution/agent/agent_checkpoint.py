"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type
from content.execution.support import Any, Callable, ExecutionContext, Mapping, Sequence, _active_spec, _active_target, _download_repair_lanes, image_asset_strategy, image_strategy_allows_ai_generated, issue_messages, json, re, read_json, require_domain_etype, save_workflow_state, store, write_json

def _checkpoint_prompts(ctx: ExecutionContext, stage: str) -> list[str]:
    """把 checkpoint 拆为可并发且写集互斥的 Agent 任务。

    prompt 正文真相源全部外置在 quwoquan_data/prompts/**（P4 prompt 外置）；
    本函数只负责计算动态数据块（路径/缺口/修复提示/配额）并经 prompt_render 渲染。
    """
    from content.execution.agent.agent_managed import _managed_checkpoint_ref_limit
    from content.execution.recovery.download_gate import _download_repair_active_issues, _download_repair_entry_pending, _download_repair_path, _download_research_lane_issues
    from content.execution.pipeline.homepage_authoring import _drafts_authored, _homepage_independent_review_issues, _homepage_pending_entities
    from content.execution.recovery.stage_reset import _source_plan_filled
    from core.content_source_registry import render_lane_source_prompt
    from core.prompt_render import render as render_prompt
    if stage == "download_plan":
        from content.source.source_unit import resolve_entity_object_dir
        etype = coverage_entity_type(ctx.spec)
        quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
        per_target_articles = max(1, int(quotas.get("entityArticlesPerTarget") or 0))
        per_target_image_works = max(0, int(quotas.get("imageWorksPerTarget") or 0))
        acceptance = ctx.spec.get("acceptance") or {}
        required_angles = [
            str(angle).strip()
            for angle in (acceptance.get("requiredAngles") or [])
            if str(angle).strip()
        ]
        article_intents = [
            angle for angle in required_angles
            if angle not in {"image", "imagePost", "gallery"}
        ] or ["planning_consultation", "decision_experience"]
        done, issues = _source_plan_filled(ctx)
        if done:
            return []
        vertical = str(ctx.spec.get("vertical") or "travel")
        pending_lanes_by_entity: dict[str, dict[str, list[str]]] = {}
        for entity in ctx.entity_ids:
            lane_issues = {
                lane: issue_messages(found)
                for lane in ("homepage", "article", "image")
                if (found := _download_research_lane_issues(ctx, entity, etype, lane))
            }
            if lane_issues:
                pending_lanes_by_entity[entity] = lane_issues
        repair_by_entity: dict[str, dict[str, Any]] = {}
        repair_path = _download_repair_path(ctx)
        if repair_path.is_file():
            repair_packet = read_json(repair_path)
            repair_by_entity = {
                str(item.get("entityId") or ""): item
                for item in (repair_packet.get("entities") or [])
                if isinstance(item, dict)
            }
        prompts = []
        for entity in ctx.entity_ids:
            repair = repair_by_entity.get(entity) or {}
            repair_active_issues = _download_repair_active_issues(ctx, repair) if repair else []
            repair_pending = (
                bool(repair)
                and _download_repair_entry_pending(repair)
                and bool(repair_active_issues)
            )
            missing_lanes = dict(pending_lanes_by_entity.get(entity) or {})
            for lane in sorted(_download_repair_lanes(repair) if repair_pending else set()):
                repair_lane_issues = repair_active_issues or ["download_repair required"]
                missing_lanes.setdefault(lane, [str(item) for item in repair_lane_issues])
            if not missing_lanes:
                continue
            object_dir = resolve_entity_object_dir(
                ctx.execution_id, entity, etype_hint=etype
            )
            if repair and not repair_pending:
                repair = {}
            repair_hint = ""
            lane_hint = "\n当前缺口：\n- " + "\n- ".join(
                f"{lane}: {'; '.join(items[:4])}" for lane, items in missing_lanes.items()
            )
            if repair:
                diagnostics = repair.get("downloadDiagnostics") or {}
                rejected_by_category = diagnostics.get("rejectedByCategory") if isinstance(diagnostics, dict) else {}
                diagnostic_hint = ""
                if rejected_by_category:
                    non_zero = [
                        f"{key}={value}"
                        for key, value in rejected_by_category.items()
                        if int(value or 0)
                    ]
                    if non_zero:
                        diagnostic_hint = "\n下载失败分类：" + ", ".join(non_zero)
                image_hint_rows: list[str] = []
                for hint in repair.get("imageRepairHints") or []:
                    if not isinstance(hint, dict):
                        continue
                    if str(hint.get("lane") or "") not in missing_lanes:
                        continue
                    candidate = str(hint.get("sameSourceHighResCandidate") or "").strip()
                    candidate_text = f"，同源高清候选: {candidate}" if candidate else ""
                    image_hint_rows.append(
                        f"{hint.get('lane')}/{hint.get('sourceId')}#{hint.get('imageIndex')}: "
                        f"{hint.get('action')}，{hint.get('issue')}{candidate_text}"
                    )
                    if len(image_hint_rows) >= 8:
                        break
                image_repair_hint = (
                    "\n源图修复指令：\n- " + "\n- ".join(image_hint_rows)
                    if image_hint_rows
                    else ""
                )
                from core.prompt_render import render_partial

                repair_hint = (
                    "\n这是 download_repair，不是首次规划。先读取以下真实 gate 报告并逐项修复：\n- "
                    + "\n- ".join(str(item) for item in (repair.get("reportPaths") or []))
                    + "\n当前失败摘要："
                    + "; ".join(str(item) for item in (repair.get("issues") or []))
                    + diagnostic_hint
                    + image_repair_hint
                    + "\n"
                    + render_partial("download_repair_contract.md")
                )
            repair_hint += lane_hint
            homepage_path = object_dir / "1.download" / "homepage_source_plan.json"
            article_path = object_dir / "1.download" / "article_source_plan.json"
            image_path = object_dir / "1.download" / "image_source_plan.json"
            common_vars = {"execution_id": ctx.execution_id, "entity_id": entity}
            if "homepage" in missing_lanes:
                prompts.append(
                    render_prompt(
                        "source_plan_homepage",
                        task_vars={
                            **common_vars,
                            "output_path": str(homepage_path),
                            "repair_block": repair_hint,
                            "lane_source_prompt": render_lane_source_prompt(
                                "homepage",
                                vertical=vertical,
                                per_target_articles=per_target_articles,
                                per_target_image_works=per_target_image_works,
                            ),
                        },
                    )
                )
            if "article" in missing_lanes:
                prompts.append(
                    render_prompt(
                        "source_plan_article",
                        task_vars={
                            **common_vars,
                            "output_path": str(article_path),
                            "repair_block": repair_hint,
                            "lane_source_prompt": render_lane_source_prompt(
                                "article",
                                vertical=vertical,
                                per_target_articles=per_target_articles,
                                per_target_image_works=per_target_image_works,
                                article_intents=article_intents,
                            ),
                        },
                    )
                )
            if "image" in missing_lanes:
                prompts.append(
                    render_prompt(
                        "source_plan_image",
                        task_vars={
                            **common_vars,
                            "output_path": str(image_path),
                            "repair_block": repair_hint,
                            "lane_source_prompt": render_lane_source_prompt(
                                "image",
                                vertical=vertical,
                                per_target_articles=per_target_articles,
                                per_target_image_works=per_target_image_works,
                                image_asset_strategy=image_asset_strategy(ctx.spec),
                            ),
                            "ai_image_policy": (
                                "本批允许 AI 原创图，但必须写完整 synthetic provenance。"
                                if image_strategy_allows_ai_generated(ctx.spec)
                                else "本批禁止 AI 图。"
                            ),
                            "image_works_quota": per_target_image_works,
                        },
                    )
                )
        return prompts
    if stage == "build_homepage":
        from content.homepage.homepage_release import materialize_entity_page, validate_entity_page
        from content.source.source_unit import resolve_entity_object_dir
        etype = coverage_entity_type(ctx.spec)
        prompts = []
        pending_entities = _homepage_pending_entities(ctx)
        for entity in pending_entities:
            target = _active_target(ctx, entity)
            domain, entity_type = require_domain_etype(
                target.get("entityType") or etype,
                context=entity,
            )
            obj = resolve_entity_object_dir(
                ctx.execution_id,
                entity,
                etype_hint=f"{domain}/{entity_type}",
            )
            current_issues = validate_entity_page(
                ctx.execution_id,
                domain,
                entity_type,
                entity,
            )
            if current_issues:
                finalize_issues = materialize_entity_page(
                    ctx.execution_id,
                    domain,
                    entity_type,
                    entity,
                )
                current_issues = list(dict.fromkeys([*current_issues, *finalize_issues]))
                if not finalize_issues:
                    current_issues = validate_entity_page(
                        ctx.execution_id,
                        domain,
                        entity_type,
                        entity,
                    )
                    if not current_issues:
                        continue
            current_issues = list(
                dict.fromkeys(
                    [
                        *current_issues,
                        *_homepage_independent_review_issues(
                            ctx,
                            domain,
                            entity_type,
                            entity,
                        ),
                    ]
                )
            )
            repair_block = (
                "\n当前 validator 未过项，必须逐项修复后再写回：\n- "
                + "\n- ".join(str(item) for item in current_issues[:10])
                if current_issues
                else ""
            )
            prompts.append(
                render_prompt(
                    "checkpoint_build_homepage",
                    task_vars={
                        "execution_id": ctx.execution_id,
                        "entity_id": entity,
                        "object_dir": str(obj),
                        "repair_block": repair_block,
                    },
                )
            )
        return prompts
    if stage == "content_plan":
        prompt_spec = _active_spec(ctx)
        quotas = ((prompt_spec.get("content") or {}).get("quotas") or {})
        acceptance = prompt_spec.get("acceptance") or {}
        required_angles = [
            str(angle).strip()
            for angle in (acceptance.get("requiredAngles") or [])
            if str(angle).strip()
        ]
        content = prompt_spec.get("content") or {}
        active_targets = [
            str(target.get("name") or "").strip()
            for target in (prompt_spec.get("scope") or {}).get("coverageTargets") or []
            if str(target.get("name") or "").strip()
        ]
        return [
            render_prompt(
                "checkpoint_content_plan",
                task_vars={
                    "execution_id": ctx.execution_id,
                    "active_targets_json": json.dumps(active_targets, ensure_ascii=False),
                    "effective_spec_json": json.dumps(
                        {
                            "scope": prompt_spec.get("scope") or {},
                            "content": content,
                            "acceptance": acceptance,
                        },
                        ensure_ascii=False,
                    ),
                    "quotas_json": json.dumps(quotas, ensure_ascii=False),
                },
            )
        ]
    if stage == "post_author":
        from content.post.draft_io import (
            draft_article_path,
            draft_package_dir,
            draft_meta_path,
            prompt_path,
            read_writing_pack,
            writing_pack_path,
        )
        from content.post import object_index as content_object
        from content.post.base_draft import base_draft_is_adaptable
        from content.execution.handoff import build_author_job_packet
        from core.io import write_json
        from content.post.writing_pack import primary_entity_name
        _ok, pending = _drafts_authored(ctx)
        ref_limit = _managed_checkpoint_ref_limit()
        if ref_limit:
            pending = pending[:ref_limit]
        prompts: list[str] = []
        for ref in pending:
            pack = read_writing_pack(ctx.execution_id, ref) or {}
            brief = content_object.read_brief_object(ctx.execution_id, ref) or {}
            packet_path = draft_package_dir(ctx.execution_id, ref) / "author_job_packet.json"
            if pack and brief:
                packet = build_author_job_packet(
                    execution_id=ctx.execution_id,
                    ref=ref,
                    brief=brief,
                    writing_pack=pack,
                    prompt_rel="4.draft/prompt.md",
                    content_object_rel=content_object.content_object_rel(ctx.execution_id, ref),
                )
                write_json(packet_path, packet)
            is_image = str(pack.get("carrier") or "") == "image"
            if is_image:
                prompts.append(
                    render_prompt(
                        "checkpoint_author_image",
                        task_vars={
                            "execution_id": ctx.execution_id,
                            "content_ref": str(ref),
                            "packet_path": str(packet_path),
                            "prompt_path": str(prompt_path(ctx.execution_id, ref)),
                            "draft_meta_path": str(draft_meta_path(ctx.execution_id, ref)),
                        },
                    )
                )
                continue
            source_use_mode = str(pack.get("sourceUseMode") or "factual_reference_only").strip()
            from core.prompt_render import render_partial

            source_contract_block = render_partial(
                "author_source_adaptable.md"
                if base_draft_is_adaptable(source_use_mode)
                else "author_source_factual.md"
            )
            entity_name = primary_entity_name(pack) or str(ref)
            prompts.append(
                render_prompt(
                    "checkpoint_author_article",
                    task_vars={
                        "execution_id": ctx.execution_id,
                        "content_ref": str(ref),
                        "packet_path": str(packet_path),
                        "prompt_path": str(prompt_path(ctx.execution_id, ref)),
                        "writing_pack_path": str(writing_pack_path(ctx.execution_id, ref)),
                        "draft_article_path": str(draft_article_path(ctx.execution_id, ref)),
                        "draft_meta_path": str(draft_meta_path(ctx.execution_id, ref)),
                        "entity_name": entity_name,
                        "source_contract_block": source_contract_block,
                    },
                )
            )
        return prompts
    return []

def _checkpoint_is_done(ctx: ExecutionContext, stage: str) -> tuple[bool, list[str]]:
    from content.execution.pipeline.homepage_authoring import _content_plan_done, _drafts_authored, _homepages_done
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

def _managed_author_failure_refs(outcomes: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for outcome in outcomes:
        if str(outcome.get("status")) == "finished":
            continue
        ref = str(outcome.get("ref") or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs

def _managed_consecutive_no_start_infra_failures(state: Mapping[str, Any], *, stage: str) -> int:
    recovery_cutoffs = state.get("managedInfraRecoveryCutoffs")
    recovery_cutoff = ""
    if isinstance(recovery_cutoffs, Mapping):
        recovery_cutoff = str(recovery_cutoffs.get(stage) or "")
    rows: list[Any] = []
    history = state.get("agentRunHistory")
    if isinstance(history, list):
        rows.extend(history)
    last = state.get("lastAgentRun")
    if isinstance(last, Mapping):
        rows.append(last)
    count = 0
    for run in reversed(rows):
        if not isinstance(run, Mapping):
            continue
        if str(run.get("stage") or "") != stage:
            if count:
                break
            continue
        finished_at = str(run.get("finishedAt") or "")
        if recovery_cutoff and finished_at and finished_at <= recovery_cutoff:
            break
        infra_failures = int(run.get("infrastructureFailures") or 0)
        started = int(run.get("startedCount") or 0)
        finished = int(run.get("finishedCount") or 0)
        if infra_failures > 0 and started == 0 and finished == 0:
            count += 1
            continue
        break
    return count

def _managed_infra_failed_refs_after_checkpoint(
    ctx: ExecutionContext,
    state: Mapping[str, Any],
    *,
    stage: str,
    checkpoint_issues: Sequence[str] | None = None,
) -> list[str]:
    if stage != "post_author":
        return []
    refs = [str(item).strip() for item in (checkpoint_issues or []) if str(item).strip()]
    if refs:
        return refs
    last_run = state.get("lastAgentRun") or {}
    if isinstance(last_run, Mapping):
        return _managed_author_failure_refs(
            list((last_run.get("outcomes") or []) if isinstance(last_run, Mapping) else [])
        )
    _ok, issues = _checkpoint_is_done(ctx, stage)
    return [str(item).strip() for item in issues if str(item).strip()]

def _handle_managed_infra_budget_exhausted(
    ctx: ExecutionContext,
    state: dict[str, Any],
    *,
    stage: str,
    infra_used: int,
    infrastructure_failures: int,
    checkpoint_issues: Sequence[str] | None = None,
) -> int | None:
    ok_after_failures, issues_after_failures = _checkpoint_is_done(ctx, stage)
    if checkpoint_issues is None:
        checkpoint_issues = issues_after_failures
    if ok_after_failures:
        last_run = dict(state.get("lastAgentRun") or {})
        if last_run:
            last_run["recovered"] = True
            last_run["recoveredAt"] = store.now_iso()
            last_run["recoveryReason"] = (
                f"{stage} checkpoint gate passed despite "
                f"{infrastructure_failures} infrastructure failure(s)"
            )
            state["lastAgentRun"] = last_run
        state["status"] = "running"
        state["failedObjects"] = []
        state["nextAction"] = (
            f"continue {stage}: checkpoint gate passed despite "
            f"{infrastructure_failures} infrastructure failure(s)"
        )
        state["heartbeatAt"] = store.now_iso()
        save_workflow_state(state)
        return 0
    failed_refs = _managed_infra_failed_refs_after_checkpoint(
        ctx,
        state,
        stage=stage,
        checkpoint_issues=checkpoint_issues,
    )
    state["status"] = "manual_required"
    state["failedObjects"] = [
        f"{stage}:{ref}: infrastructure did not start"
        for ref in failed_refs
    ] or list(checkpoint_issues or state.get("failedObjects") or [])
    state["nextAction"] = (
        f"{stage} infrastructure failed after {infra_used} attempts; "
        f"{infrastructure_failures} agent job(s) did not start"
    )
    save_workflow_state(state)
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
    from content.execution.pipeline.homepage_authoring import _managed_image_author_meta_issues
    if stage == "download_plan":
        lane = _managed_prompt_lane(prompt)
        entity = _managed_prompt_entity(prompt)
        if lane not in {"homepage", "article", "image"} or not entity:
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
        from content.post.draft_io import draft_article_path, is_placeholder, read_draft_meta, read_writing_pack
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
    outcomes: list[dict[str, Any]],
) -> None:
    """用确定性 helper 补齐 Agent 草稿的 run ID 和四类 provenance hash。"""
    from content.execution.pipeline.homepage_authoring import _managed_image_author_meta_issues
    from content.post.draft_io import (
        compute_draft_provenance_facts,
        draft_article_path,
        draft_meta_path,
        is_placeholder,
        read_draft_meta,
        read_writing_pack,
    )
    for outcome in outcomes:
        if str(outcome.get("status")) != "finished":
            continue
        job_index = int(outcome.get("jobIndex", -1))
        if job_index < 0 or job_index >= len(prompts):
            continue
        ref = _managed_author_ref(prompts[job_index])
        if not ref:
            continue
        meta = read_draft_meta(ctx.execution_id, ref) or {}
        pack = read_writing_pack(ctx.execution_id, ref) or {}
        is_image_carrier = str(pack.get("carrier") or "") == "image"
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
                    "agentRunId": outcome.get("runId") or meta.get("agentRunId"),
                    "agentId": outcome.get("agentId") or meta.get("agentId"),
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
                "agentRunId": outcome.get("runId") or meta.get("agentRunId"),
                "agentId": outcome.get("agentId") or meta.get("agentId"),
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
