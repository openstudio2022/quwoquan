"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import Any, Callable, ExecutionContext, Mapping, Sequence, _active_spec, _active_target, _download_repair_lanes, image_asset_strategy, image_strategy_allows_ai_generated, issue_messages, json, re, read_json, require_domain_etype, save_execution_state, store, write_json

def _checkpoint_prompts(ctx: ExecutionContext, stage: str) -> list[str]:
    """把 checkpoint 拆为可并发且写集互斥的 Agent 任务。

    prompt 正文真相源全部外置在 quwoquan_data/prompts/**（P4 prompt 外置）；
    本函数只负责计算动态数据块（路径/缺口/修复提示/配额）并经 prompt_render 渲染。
    """
    from content.execution.agent.managed_checkpoint import _managed_checkpoint_ref_limit
    from content.execution.recovery.download_gate import _download_repair_active_issues, _download_repair_entry_pending, _download_repair_path, _download_research_lane_issues
    from content.execution.controller.homepage_authoring import _drafts_authored, _homepage_independent_review_issues, _homepage_pending_entities
    from content.execution.recovery.stage_reset import _source_plan_filled
    from core.content_source_registry import render_lane_source_prompt
    from core.prompt_render import render as render_prompt
    if stage == "download_plan":
        from content.source.source_unit import resolve_entity_object_dir
        etype = coverage_entity_type(ctx.spec)
        quotas = ctx.spec.content.quotas
        per_target_articles = max(1, quotas.entity_articles_per_target)
        per_target_image_works = quotas.image_works_per_target
        required_angles = [
            str(angle).strip()
            for angle in ctx.spec.acceptance.required_angles
            if str(angle).strip()
        ]
        article_intents = [
            angle for angle in required_angles
            if angle not in {"image", "imagePost", "gallery"}
        ] or ["planning_consultation", "decision_experience"]
        done, issues = _source_plan_filled(ctx)
        if done:
            return []
        vertical = ctx.spec.vertical
        pending_lanes_by_entity: dict[str, dict[str, list[str]]] = {}
        for entity in ctx.entity_ids:
            entity_etype = coverage_entity_type_for_entity(ctx.spec, entity) or etype
            lane_issues = {
                lane: issue_messages(found)
                for lane in ("homepage", "article", "image")
                if (
                    found := _download_research_lane_issues(
                        ctx,
                        entity,
                        entity_etype,
                        lane,
                    )
                )
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
            target = _active_target(ctx, entity)
            domain, entity_type = require_domain_etype(
                target.get("entityType")
                or coverage_entity_type_for_entity(ctx.spec, entity)
                or etype,
                context=entity,
            )
            object_dir = resolve_entity_object_dir(
                ctx.execution_id,
                entity,
                etype_hint=f"{domain}/{entity_type}",
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
                                image_asset_strategy=image_asset_strategy(ctx.spec.to_dict()),
                            ),
                            "ai_image_policy": (
                                "本批允许 AI 原创图，但必须写完整 synthetic provenance。"
                                if image_strategy_allows_ai_generated(ctx.spec.to_dict())
                                else "本批禁止 AI 图。"
                            ),
                            "image_works_quota": per_target_image_works,
                        },
                    )
                )
        return prompts
    if stage == "build_homepage":
        from content.homepage.homepage_release import materialize_entity_page
        from content.homepage.homepage_release_validation import validate_entity_page
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
        from content.post.article.draft_io import (
            draft_article_path,
            draft_package_dir,
            draft_meta_path,
            prompt_path,
            read_writing_pack,
            writing_pack_path,
        )
        from content.post import object_index as content_object
        from content.post.article.base_draft import base_draft_is_adaptable
        from content.execution.controller.execute.handoff import build_author_job_packet
        from core.io import write_json
        from content.post.article.writing_pack import primary_entity_name
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
                carrier = str(pack.get("carrier") or brief.get("carrier") or "")
                if carrier == "article":
                    from content.post.article.source_unit_freeze import (
                        validate_article_source_unit_freeze,
                    )

                    binding = (
                        pack.get("articleSourceUnitFreeze")
                        or brief.get("articleSourceUnitFreeze")
                    )
                    publish_media_mode = str(
                        pack.get("publishMediaMode")
                        or brief.get("publishMediaMode")
                        or ""
                    ).strip()
                    asset_refs = list(
                        pack.get("assetRefs") or brief.get("assetRefs") or []
                    )
                    if publish_media_mode == "text_only":
                        if asset_refs or binding is not None:
                            raise ValueError(
                                "GATE_BLOCK DATA.ARTICLE.TEXT_ONLY_MEDIA_DRIFT: "
                                "text-only article must not carry assets or a "
                                "source-unit image freeze"
                            )
                    elif not isinstance(binding, dict):
                        raise ValueError(
                            "GATE_BLOCK DATA.ARTICLE.SOURCE_UNIT_FREEZE_REQUIRED: "
                            "article semantic author requires one create-once "
                            "source-unit freeze"
                        )
                    else:
                        validate_article_source_unit_freeze(
                            binding,
                            execution_id=ctx.execution_id,
                        )
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
            is_video = str(pack.get("carrier") or "") == "video"
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
            if is_video:
                from content.post.video.authoring import video_script_path

                prompts.append(
                    render_prompt(
                        "checkpoint_author_video",
                        task_vars={
                            "execution_id": ctx.execution_id,
                            "content_ref": str(ref),
                            "packet_path": str(packet_path),
                            "prompt_path": str(prompt_path(ctx.execution_id, ref)),
                            "writing_pack_path": str(writing_pack_path(ctx.execution_id, ref)),
                            "video_script_path": str(video_script_path(ctx.execution_id, ref)),
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
