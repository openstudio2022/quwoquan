"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type
from content.execution.support import Any, DataIssueCode, DataIssueStage, DataIssueLane, DataRecoveryAction, ExecutionContext, ExecutionStateTransition, Mapping, Path, _IMAGE_SOURCE_TEXT_NOISE_PATTERNS, _IMAGE_SOURCE_TEXT_NOISE_TOKENS, _active_spec, _is_homepage_only_execution, data_issue, execution_root, load_execution_state, os, re, read_json, require_domain_etype, save_execution_state, shutil, store, write_json


def _managed_finished_author_outcomes_by_ref(
    state: ExecutionStateTransition,
) -> dict[str, "AgentRunOutcome"]:
    from content.execution.agent.history import state_managed_agent_runs

    outcomes_by_ref: dict[str, "AgentRunOutcome"] = {}
    for run in state_managed_agent_runs(state):
        if run.stage.value != "post_author":
            continue
        for job_outcome in run.outcomes:
            if not job_outcome.succeeded:
                continue
            if job_outcome.ref:
                outcomes_by_ref[job_outcome.ref] = job_outcome.outcome
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

def _finalize_existing_managed_author_outputs(ctx: ExecutionContext, state: ExecutionStateTransition) -> int:
    """补齐已写回但因中断未 finalize 的 Agent 草稿 provenance。"""
    from content.post import object_index as content_object
    from content.post.content_review import generator_provenance_issues
    from content.post.article.draft_io import (
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
        is_video_carrier = str(pack.get("carrier") or "") == "video"
        if is_video_carrier:
            from content.post.video.authoring import finalize_video_author_meta

            if finalize_video_author_meta(
                ctx.execution_id,
                ref,
                run_id=outcome.run_id or str(meta.get("agentRunId") or ""),
                agent_id=outcome.agent_id or meta.get("agentId"),
                model=str(ctx.model or ""),
            ):
                finalized += 1
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
                    "model": ctx.model,
                    "agentRunId": outcome.run_id or meta.get("agentRunId"),
                    "agentId": outcome.agent_id or meta.get("agentId"),
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
                "model": ctx.model,
                "agentRunId": outcome.run_id or meta.get("agentRunId"),
                "agentId": outcome.agent_id or meta.get("agentId"),
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
    outcome: "AgentRunOutcome",
    draft_meta: Mapping[str, Any],
    source_failure: Mapping[str, Any] | None = None,
) -> None:
    """Mint controller evidence from one finished Cursor author run.

    The page itself is authored by the Agent. These two JSON files are not
    Agent-authored prose: they bind that completed run to the exact file and
    deterministic output checks so later stages can replay the proof without
    trusting a conversational status message.

    When ``source_failure`` is provided, the Agent applied the typed failure
    protocol (``failure.json``) and left ``page.md`` as a placeholder; evidence
    binds that refusal instead of requiring a non-placeholder draft.
    """
    from content.execution.production_contracts import (
        build_agent_result_envelope,
        build_gate_verdict,
        sha256_file,
        validate_agent_result_envelope,
    )
    from content.execution.agent.outcome import AgentRunOutcome
    from content.execution.queue.core import stable_job_id
    from content.post.article.draft_io import is_placeholder
    from core.schema import assert_valid
    from governance.coverage.entity_extract import entity_ref

    page_path = draft_dir / "page.md"
    prompt_path = draft_dir / "prompt.md"
    packet_path = draft_dir / "author_job_packet.json"
    failure_path = draft_dir / "failure.json"
    if not page_path.is_file() or not prompt_path.is_file() or not packet_path.is_file():
        raise ValueError("homepage author evidence requires page.md, prompt.md, and author_job_packet.json")
    if source_failure is not None and not failure_path.is_file():
        raise ValueError("homepage author evidence source_failure requires 4.draft/failure.json")
    packet = read_json(packet_path)
    object_ref = entity_ref(domain, etype, entity)
    if not outcome.succeeded:
        raise ValueError("homepage author evidence requires a finished AgentRunOutcome")
    run_id = outcome.run_id
    provider = outcome.provider.value
    model = str(draft_meta.get("model") or ctx.model or "").strip()
    prompt_sha = str(draft_meta.get("promptSha256") or "").strip()
    draft_sha = sha256_file(page_path)
    if source_failure is not None:
        failure_sha = sha256_file(failure_path)
        checks = [
            {
                "name": "failure_protocol_applied",
                "passed": True,
                "ref": "4.draft/failure.json",
                "failureKind": str(source_failure.get("failureKind") or ""),
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
        envelope_files = [
            {
                "path": "failure.json",
                "sha256": failure_sha,
                "role": "homepage_source_failure",
            },
            {
                "path": "page.md",
                "sha256": draft_sha,
                "role": "homepage_draft_placeholder",
            },
        ]
        output_hash = failure_sha
    else:
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
        envelope_files = [
            {"path": "page.md", "sha256": draft_sha, "role": "homepage_draft"}
        ]
        output_hash = draft_sha
    issues = [
        str(check.get("name") or "check")
        for check in checks
        if not bool(check.get("passed"))
    ]
    self_check = {
        "schema": "quwoquan_data.author_self_check",
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
        output_hash=output_hash,
        issues=issues,
    )
    envelope = build_agent_result_envelope(
        job={
            "jobId": stable_job_id(ctx.execution_id, object_ref, "author"),
            "executionId": ctx.execution_id,
            "ref": object_ref,
            "stage": "author",
        },
        files=envelope_files,
        gates=[gate],
        provider=provider,
        model=model,
        run_id=run_id,
        prompt_sha256=prompt_sha,
        agent_id=outcome.agent_id or None,
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
