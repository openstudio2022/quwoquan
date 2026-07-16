"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type
from content.execution.support import Any, DataIssueCode, DataIssueStage, DataIssueLane, DataRecoveryAction, ExecutionContext, Mapping, Path, _IMAGE_SOURCE_TEXT_NOISE_PATTERNS, _IMAGE_SOURCE_TEXT_NOISE_TOKENS, _active_spec, _is_homepage_only_workflow, data_issue, execution_root, load_workflow_state, os, re, read_json, require_domain_etype, save_workflow_state, shutil, store, write_json

def _homepages_done(ctx: ExecutionContext) -> tuple[bool, list[str]]:
    """build_homepage checkpoint：coverage 实体三件套是否物化（用 build validate 复核）。"""
    from content.homepage.homepage import homepage_runtime_spec
    from content.homepage.homepage_release import validate_entity_pages
    runtime_spec = homepage_runtime_spec(ctx.execution_id, _active_spec(ctx))
    issues = validate_entity_pages(ctx.execution_id, runtime_spec)
    for target in ((runtime_spec.get("scope") or {}).get("coverageTargets") or []):
        if not isinstance(target, Mapping):
            continue
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, etype = require_domain_etype(target.get("entityType"), context=name)
        issues.extend(_homepage_independent_review_issues(ctx, domain, etype, name))
    return (not issues), issues

def _homepage_independent_review_issues(
    ctx: ExecutionContext,
    domain: str,
    etype: str,
    name: str,
) -> list[str]:
    review_path = (
        execution_root(ctx.execution_id)
        / "entities"
        / domain
        / etype
        / name
        / "5.review/review.json"
    )
    if not review_path.is_file():
        return []
    review = read_json(review_path)
    reviewer = (
        review.get("independentReviewer")
        if isinstance(review.get("independentReviewer"), Mapping)
        else {}
    )
    reviewer_status = str((reviewer or {}).get("status") or "pending")
    if reviewer_status == "pending":
        return []
    if reviewer_status != "passed":
        recorded = [str(item) for item in review.get("issues") or [] if str(item).strip()]
        return recorded or [f"{name}: independent reviewer not passed ({reviewer_status})"]
    from content.homepage.commercial_gate import independent_review_issues

    draft_meta_path = (
        execution_root(ctx.execution_id)
        / "entities"
        / domain
        / etype
        / name
        / "4.draft/draft_meta.json"
    )
    draft_meta = read_json(draft_meta_path) if draft_meta_path.is_file() else {}
    author = {
        "runId": str(draft_meta.get("agentRunId") or ""),
        "modelFamily": str(os.environ.get("QWQ_HOMEPAGE_AUTHOR_MODEL_FAMILY") or ""),
    }
    return independent_review_issues(reviewer, author, label=name)

def _homepage_pending_entities(ctx: ExecutionContext) -> list[str]:
    """Return only active homepage objects that still fail per-entity validate.
    Managed retries must not re-run already accepted homepage triplets; otherwise
    a single slow/failed Cursor job can multiply token cost and overwrite stable
    evidence. The validator remains the source of truth, not Agent self-report.
    """
    from content.homepage.homepage_release import validate_entity_page
    pending: list[str] = []
    for target in ((_active_spec(ctx).get("scope") or {}).get("coverageTargets") or []):
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, etype = require_domain_etype(
            target.get("entityType"),
            context=f"coverageTargets[{name}]",
        )
        issues = validate_entity_page(
            ctx.execution_id,
            domain,
            etype,
            name,
        )
        issues.extend(_homepage_independent_review_issues(ctx, domain, etype, name))
        if issues:
            pending.append(name)
    return pending

def _content_plan_done(ctx: ExecutionContext) -> tuple[bool, list[str]]:
    """content_plan checkpoint：篇目包+注册+brief 是否就绪。"""
    from content.execution.pipeline.content_plan_prep import _clean_content_plan_outputs
    from content.post.content_plan import validate_content_plan
    if _is_homepage_only_workflow(ctx):
        # homepage-only：无篇目合同，content_plan 确定性完成；清掉任何篇目残留，
        # 防止历史 agent 误写的 packet/briefs 把 post 车道当文章推进。
        _clean_content_plan_outputs(ctx)
        return True, []
    _prune_content_plan_extra_briefs(ctx)
    issues = validate_content_plan(ctx.execution_id, _active_spec(ctx))
    return (not issues), issues

def _prune_content_plan_extra_briefs(ctx: ExecutionContext) -> list[str]:
    """Remove filesystem brief objects that are no longer registered.
    Agent repairs may rewrite content_plan_packet/index while leaving old
    posts/**/3.compose/brief.json trees behind. Downstream post must consume
    only the packet/index truth source, so stale object trees are pruned before
    validating the checkpoint.
    """
    from content.post.object_index import BRIEF_FILE, content_object_stage_dir, load_index
    from core.paths import STAGE_COMPOSE
    root = execution_root(ctx.execution_id)
    posts_root = root / "posts"
    if not posts_root.is_dir():
        return []
    index = load_index(ctx.execution_id)
    expected: set[Path] = set()
    for ref in index:
        try:
            expected.add((content_object_stage_dir(ctx.execution_id, ref, STAGE_COMPOSE) / BRIEF_FILE).resolve())
        except (KeyError, OSError, ValueError):
            continue
    actual = {
        path.resolve()
        for path in posts_root.glob(f"*/*/*/*/{STAGE_COMPOSE}/{BRIEF_FILE}")
        if path.is_file()
    }
    removed: list[str] = []
    for brief_path in sorted(actual - expected):
        object_dir = brief_path.parents[1]
        rel = object_dir.relative_to(root).as_posix() if object_dir.is_relative_to(root) else object_dir.as_posix()
        shutil.rmtree(object_dir)
        removed.append(rel)
    if removed:
        print(
            "[geo-homepages] Pruned stale content_plan brief object(s): "
            + ", ".join(removed[:12])
            + (" ..." if len(removed) > 12 else "")
        )
    return removed

def _managed_finished_author_outcomes_by_ref(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: list[Any] = []
    history = state.get("agentRunHistory")
    if isinstance(history, list):
        rows.extend(history)
    last = state.get("lastAgentRun")
    if isinstance(last, Mapping):
        rows.append(last)
    outcomes_by_ref: dict[str, Mapping[str, Any]] = {}
    for run in rows:
        if not isinstance(run, Mapping) or str(run.get("stage") or "") != "post_author":
            continue
        for outcome in run.get("outcomes") or []:
            if not isinstance(outcome, Mapping) or str(outcome.get("status") or "") != "finished":
                continue
            ref = str(outcome.get("ref") or "").strip()
            if ref:
                outcomes_by_ref[ref] = outcome
    return outcomes_by_ref

def _image_source_text_semantic_tokens(text: str) -> list[str]:
    lowered = str(text or "").casefold()
    if not lowered.strip():
        return []
    cleaned = lowered
    for pattern in _IMAGE_SOURCE_TEXT_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{1,4}\b", " ", cleaned)
    cleaned = re.sub(r"[^\w\u00c0-\u024f\u4e00-\u9fff]+", " ", cleaned)
    tokens: list[str] = []
    for raw in cleaned.split():
        token = raw.strip("_- ")
        if not token:
            continue
        if token in _IMAGE_SOURCE_TEXT_NOISE_TOKENS:
            continue
        if len(token) == 1 and not re.search(r"[\u4e00-\u9fff]", token):
            continue
        tokens.append(token)
    return tokens

def _managed_image_author_meta_issues(
    meta: Mapping[str, Any] | None,
    *,
    writing_pack: Mapping[str, Any] | None = None,
    require_agent_run: bool,
) -> list[str]:
    from core import creative_brief as cb
    data = meta or {}
    pack = writing_pack or {}
    issues: list[str] = []
    generator = str(data.get("generator") or "").strip()
    if generator != "image_evidence_pack":
        issues.append(
            "draft_meta.generator is "
            + (generator or "<missing>")
            + ", expected image_evidence_pack"
        )
    source_title = str(pack.get("title") or "").strip()
    source_caption = str(pack.get("caption") or "").strip()
    source_title_tokens = _image_source_text_semantic_tokens(source_title)
    source_caption_tokens = _image_source_text_semantic_tokens(source_caption)
    title = re.sub(r"\s+", "", str(data.get("title") or ""))
    caption = re.sub(r"\s+", "", str(data.get("caption") or ""))
    title_tokens = _image_source_text_semantic_tokens(str(data.get("title") or ""))
    title_required = bool(source_title_tokens)
    caption_required = bool(source_caption_tokens)
    if caption_required and title_tokens:
        title_token_set = set(title_tokens)
        if set(source_caption_tokens).issubset(title_token_set):
            caption_required = False
    elif caption_required and source_title_tokens:
        if set(source_caption_tokens).issubset(set(source_title_tokens)):
            caption_required = False
    if title_required:
        if not title:
            issues.append("draft_meta.title missing while source title exists")
    elif title:
        issues.append("draft_meta.title must stay empty when source title has no usable semantic content")
    if caption_required:
        if not caption:
            issues.append("draft_meta.caption missing while source caption exists")
    elif not source_caption and caption:
        issues.append("draft_meta.caption must stay empty when source caption is empty")
    if len(title) > 80:
        issues.append(f"draft_meta.title exceeds 80 characters ({len(title)})")
    if len(caption) > 300:
        issues.append(f"draft_meta.caption exceeds 300 characters ({len(caption)})")
    plan = data.get("creativePlan")
    if not isinstance(plan, Mapping):
        issues.append("draft_meta.creativePlan missing")
    else:
        concepts = plan.get("concepts")
        if not isinstance(concepts, list) or len(concepts) < cb.CREATIVE_PLAN_MIN_CONCEPTS:
            issues.append(
                "draft_meta.creativePlan.concepts must contain at least "
                f"{cb.CREATIVE_PLAN_MIN_CONCEPTS} concepts"
            )
        if not str(plan.get("selectedPlanId") or "").strip():
            issues.append("draft_meta.creativePlan.selectedPlanId missing")
        if not str(plan.get("selectionReason") or "").strip():
            issues.append("draft_meta.creativePlan.selectionReason missing")
    critique = data.get("selfCritique")
    if not isinstance(critique, Mapping):
        issues.append("draft_meta.selfCritique missing")
    else:
        for field in cb.SELF_CRITIQUE_FIELDS:
            if not str(critique.get(field) or "").strip():
                issues.append(f"draft_meta.selfCritique.{field} missing")
    if require_agent_run and not str(data.get("agentRunId") or "").strip():
        issues.append("draft_meta.agentRunId missing")
    return issues

def _finalize_existing_managed_author_outputs(ctx: ExecutionContext, state: Mapping[str, Any]) -> int:
    """补齐已写回但因中断未 finalize 的 Agent 草稿 provenance。"""
    from content.post import object_index as content_object
    from content.post.content_review import generator_provenance_issues
    from content.post.draft_io import (
        compute_draft_provenance_facts,
        draft_article_path,
        draft_meta_path,
        is_placeholder,
        read_draft_meta,
        read_writing_pack,
    )
    outcomes_by_ref = _managed_finished_author_outcomes_by_ref(state)
    if not outcomes_by_ref:
        return 0
    finalized = 0
    for ref in content_object.iter_content_refs(ctx.execution_id):
        outcome = outcomes_by_ref.get(ref)
        if not outcome:
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
                    "finalizedFromAgentRunHistory": True,
                }
            )
            write_json(draft_meta_path(ctx.execution_id, ref), enriched_meta)
            finalized += 1
            continue
        article_path = draft_article_path(ctx.execution_id, ref)
        if not article_path.is_file():
            continue
        article = article_path.read_text(encoding="utf-8")
        if is_placeholder(article):
            continue
        if not generator_provenance_issues(meta):
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
                "finalizedFromAgentRunHistory": True,
            }
        )
        write_json(draft_meta_path(ctx.execution_id, ref), enriched_meta)
        finalized += 1
    return finalized

def _homepage_finalization_unexpected_issue(entity: str, exc: Exception):
    """Return a bounded typed failure instead of leaking a finalize traceback."""
    detail = re.sub(r"crsr_[A-Za-z0-9_-]+", "<redacted-cursor-key>", " ".join(str(exc).split()))[:400]
    return data_issue(
        DataIssueCode.INTERNAL_UNEXPECTED,
        stage=DataIssueStage.BUILD_HOMEPAGE,
        ref=entity,
        lane=DataIssueLane.HOMEPAGE,
        recovery=DataRecoveryAction.STOP,
        message="homepage materialization raised an unexpected exception",
        attributes={
            "errorType": type(exc).__name__,
            "errorMessage": detail or type(exc).__name__,
        },
    )


def _write_homepage_author_evidence(
    ctx: ExecutionContext,
    *,
    draft_dir: Path,
    domain: str,
    etype: str,
    entity: str,
    outcome: Mapping[str, Any],
    draft_meta: Mapping[str, Any],
) -> None:
    """Mint controller evidence from one finished Cursor author run.

    The page itself is authored by the Agent. These two JSON files are not
    Agent-authored prose: they bind that completed run to the exact file and
    deterministic output checks so later stages can replay the proof without
    trusting a conversational status message.
    """
    from content.execution.production_contracts import (
        build_agent_result_envelope,
        build_gate_verdict,
        sha256_file,
        validate_agent_result_envelope,
    )
    from content.post.draft_io import is_placeholder
    from core.schema import assert_valid
    from governance.coverage.entity_extract import entity_ref

    page_path = draft_dir / "page.md"
    prompt_path = draft_dir / "prompt.md"
    packet_path = draft_dir / "author_job_packet.json"
    if not page_path.is_file() or not prompt_path.is_file() or not packet_path.is_file():
        raise ValueError("homepage author evidence requires page.md, prompt.md, and author_job_packet.json")
    packet = read_json(packet_path)
    object_ref = entity_ref(domain, etype, entity)
    run_id = str(outcome.get("runId") or "").strip()
    provider = str(
        outcome.get("agentProvider") or draft_meta.get("provider") or ctx.agent_provider or ""
    ).strip()
    model = str(draft_meta.get("model") or ctx.model or "").strip()
    prompt_sha = str(draft_meta.get("promptSha256") or "").strip()
    draft_sha = sha256_file(page_path)
    checks = [
        {
            "name": "non_placeholder_page",
            "passed": not is_placeholder(page_path.read_text(encoding="utf-8")),
            "ref": "4.draft/page.md",
        },
        {
            "name": "draft_hash_matches_metadata",
            "passed": str(draft_meta.get("draftSha256") or "") == draft_sha,
            "expected": str(draft_meta.get("draftSha256") or ""),
            "actual": draft_sha,
        },
        {
            "name": "agent_run_bound",
            "passed": bool(run_id and provider and model and prompt_sha),
            "runId": run_id,
        },
        {
            "name": "author_packet_matches_object",
            "passed": (
                str(packet.get("executionId") or "") == ctx.execution_id
                and str(packet.get("objectRef") or "") == object_ref
            ),
        },
    ]
    issues = [
        str(check.get("name") or "check")
        for check in checks
        if not bool(check.get("passed"))
    ]
    self_check = {
        "schemaVersion": "quwoquan_data.author_self_check/1",
        "stage": "4.draft",
        "executionId": ctx.execution_id,
        "objectRef": object_ref,
        "passed": not issues,
        "checks": checks,
        "issues": issues,
    }
    gate = build_gate_verdict(
        gate_id="homepage_author_output",
        decision="passed" if not issues else "failed",
        input_hash=prompt_sha,
        output_hash=draft_sha,
        issues=issues,
    )
    envelope = build_agent_result_envelope(
        job={
            "jobId": f"homepage-author:{ctx.execution_id}:{object_ref}",
            "executionId": ctx.execution_id,
            "ref": object_ref,
            "stage": "homepage_author",
        },
        files=[{"path": "page.md", "sha256": draft_sha, "role": "homepage_draft"}],
        gates=[gate],
        provider=provider,
        model=model,
        run_id=run_id,
        prompt_sha256=prompt_sha,
        agent_id=str(outcome.get("agentId") or "").strip() or None,
    )
    assert_valid(self_check, "content", "author_self_check", label=f"author_self_check:{entity}")
    assert_valid(envelope, "content", "agent_result_envelope", label=f"agent_result_envelope:{entity}")
    envelope_issues = validate_agent_result_envelope(envelope, workspace_root=draft_dir)
    if envelope_issues:
        raise ValueError("homepage author envelope invalid: " + "; ".join(envelope_issues))
    if issues:
        raise ValueError("homepage author self-check failed: " + "; ".join(issues))
    write_json(draft_dir / "author_self_check.json", self_check)
    write_json(draft_dir / "agent_result_envelope.json", envelope)


def _finalize_managed_homepage_outputs(
    ctx: ExecutionContext,
    prompts: list[str],
    outcomes: list[dict[str, Any]],
) -> int:
    """Finalize a completed homepage author run before materializing its page."""
    from content.execution.agent.agent_checkpoint import _managed_prompt_entity
    from core.article_package import compute_document_sha256
    from content.post.draft_io import is_placeholder
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
                for row in ((ctx.spec.get("scope") or {}).get("coverageTargets") or [])
                if str(row.get("name") or "").strip() == entity
            ),
            None,
        )
        if not target:
            continue
        domain, et = require_domain_etype(target.get("entityType"), context=entity)
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
    from content.post.draft_io import (
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

def _drafts_authored(ctx: ExecutionContext) -> tuple[bool, list[str]]:
    """post_author checkpoint：compose 后的所有 carrier drafts 是否被 Agent 创作."""
    from content.execution.recovery.post_recovery import _content_plan_base_draft_shortfall_refs
    from content.post import object_index as content_object
    from content.post.content_review import generator_provenance_issues
    from content.post.draft_io import draft_article_path, is_placeholder, read_draft_meta, read_writing_pack
    from core.paths import STAGE_REVIEW
    state = load_workflow_state(ctx.execution_id)
    finalized_count = _finalize_existing_managed_author_outputs(ctx, state)
    if finalized_count:
        state = load_workflow_state(ctx.execution_id)
        state["heartbeatAt"] = store.now_iso()
        state["lastAuthorFinalizeCount"] = finalized_count
        save_workflow_state(state)
    content_refs = content_object.iter_content_refs(ctx.execution_id)
    active_refs = list(content_refs)
    if not content_refs:
        return False, ["(no content objects; run compose-brief first)"]
    preflight_short_refs = _content_plan_base_draft_shortfall_refs(ctx, active_refs)
    if preflight_short_refs:
        return False, [
            f"{ref}: baseDraftText effective length below authoring gate"
            for ref in preflight_short_refs
        ]
    object_queue_finalized = _finalize_existing_object_queue_author_outputs(ctx, active_refs)
    if object_queue_finalized:
        state = load_workflow_state(ctx.execution_id)
        state["heartbeatAt"] = store.now_iso()
        state["lastObjectQueueAuthorFinalizeCount"] = object_queue_finalized
        save_workflow_state(state)
    pending: list[str] = []
    for ref in active_refs:
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
            if ctx.managed and _managed_image_author_meta_issues(
                read_draft_meta(ctx.execution_id, ref),
                writing_pack=pack,
                require_agent_run=True,
            ):
                pending.append(ref)
            continue
        try:
            art = draft_article_path(ctx.execution_id, ref)
        except KeyError:
            pending.append(ref)
            continue
        if not art.is_file():
            pending.append(ref)
            continue
        try:
            article_text = art.read_text(encoding="utf-8")
        except OSError:
            pending.append(ref)
            continue
        draft_needs_agent = False
        try:
            review_dir = content_object.content_object_stage_dir(
                ctx.execution_id, ref, STAGE_REVIEW
            )
        except KeyError:
            review_dir = None
        repair_is_newer = False
        if review_dir is not None:
            repair_report = review_dir / "repair_report.json"
            if repair_report.is_file():
                try:
                    repair_is_newer = repair_report.stat().st_mtime >= art.stat().st_mtime
                except OSError:
                    repair_is_newer = True
        if is_placeholder(article_text):
            draft_needs_agent = True
        elif generator_provenance_issues(read_draft_meta(ctx.execution_id, ref)):
            draft_needs_agent = True
        elif repair_is_newer:
            draft_needs_agent = True
        if draft_needs_agent:
            pending.append(ref)
    return (not pending), pending
