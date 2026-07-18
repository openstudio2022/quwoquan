"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.runtime_policy import active_runtime_policy
from content.execution.support import Any, ExecutionContext, ExecutionStateTransition, Mapping, Path, datetime, execution_root, load_execution_state, re, read_json, store, write_json
from content.execution.controller.token_ledger import (
    build_token_ledger_payload,
    dedupe_agent_runs,
    required_creator_profile_id,
)

def _parse_iso_seconds(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None

def _estimate_tokens(*parts: object) -> int:
    text = "\n".join(str(part or "") for part in parts if part is not None)
    compact_len = len(re.sub(r"\s+", "", text))
    # Chinese-heavy prompts average below one token per visible character, but
    # use a conservative integer estimate so scale reports are not optimistic.
    return max(1, int((compact_len + 1) / 1.5))

def _read_text_if_file(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

def _batch_file_elapsed_seconds(root: Path) -> float | None:
    mtimes: list[float] = []
    if not root.is_dir():
        return None
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    if len(mtimes) < 2:
        return None
    elapsed = max(mtimes) - min(mtimes)
    return elapsed if elapsed > 0 else None

def _review_repaired_refs(ctx: ExecutionContext) -> set[str]:
    from content.post import object_index as content_object
    repaired: set[str] = set()
    state = load_execution_state(ctx.execution_id)
    for row in state.produce_review_retry_history or []:
        if not isinstance(row, Mapping):
            continue
        for ref in row.get("refs") or []:
            text = str(ref or "").strip()
            if text:
                repaired.add(text)
    root = execution_root(ctx.execution_id)
    ref_by_dir = {
        str(content_object.content_object_dir(ctx.execution_id, ref)): ref
        for ref in content_object.iter_content_refs(ctx.execution_id)
    }
    for path in root.rglob("5.review/repair_report.json"):
        ref = ref_by_dir.get(str(path.parent.parent))
        if ref:
            repaired.add(ref)
    return repaired

def _agent_active_throughput(state: ExecutionStateTransition) -> dict[str, Any]:
    runs: list[Any] = list(state.agent_run_history or [])
    last = state.last_agent_run
    if isinstance(last, Mapping):
        runs.append(last)
    agent_runs = dedupe_agent_runs(runs)
    source_stage = "post_author"
    author_runs = [row for row in agent_runs if str(row.get("stage") or "") == source_stage]
    if not author_runs:
        source_stage = "build_homepage"
        author_runs = [row for row in agent_runs if str(row.get("stage") or "") == source_stage]
    elapsed = 0.0
    finished = 0
    infra_failures = 0
    planned = 0
    max_worker_count = 0
    for row in author_runs:
        scheduler = row.get("scheduler") if isinstance(row.get("scheduler"), Mapping) else {}
        try:
            elapsed += float((scheduler or {}).get("elapsedSeconds") or 0)
        except (TypeError, ValueError):
            pass
        try:
            worker_count = int((scheduler or {}).get("effectiveWorkerCount") or 0)
        except (TypeError, ValueError):
            worker_count = 0
        max_worker_count = max(max_worker_count, worker_count)
        finished += int(row.get("finishedCount") or 0)
        infra_failures += int(row.get("infrastructureFailures") or 0)
        planned += int(row.get("plannedJobCount") or row.get("jobCount") or 0)
    aggregate_per_hour = round((finished / elapsed) * 3600, 4) if elapsed > 0 else 0.0
    # Per-worker unit rate is the aggregate author throughput divided by the
    # concurrency actually realized during the trial.  It is the only rate that
    # can be linearly projected onto a committed reliabletask worker fleet.
    realized_workers = max(1, max_worker_count)
    per_worker_per_hour = round(aggregate_per_hour / realized_workers, 4) if aggregate_per_hour else 0.0
    return {
        "measurementMode": "agent_run_history",
        "sourceStage": source_stage,
        "jobKind": "homepage" if source_stage == "build_homepage" else "author",
        "authorRunCount": len(author_runs),
        "authorActiveSeconds": round(elapsed, 3),
        "plannedAuthorJobs": planned,
        "finishedAuthorJobs": finished,
        "infrastructureFailures": infra_failures,
        "finishedAuthorJobsPerHour": aggregate_per_hour,
        "effectiveWorkerCount": realized_workers,
        "perWorkerObjectsPerHour": per_worker_per_hour,
    }

def _homepage_passed_count_from_artifacts(root: Path) -> int:
    count = 0
    entities_root = root / "entities"
    if not entities_root.is_dir():
        return 0
    for report_path in sorted(entities_root.rglob("5.review/finalization_report.json")):
        report = read_json(report_path)
        if not isinstance(report, Mapping):
            continue
        status = str(report.get("status") or report.get("decision") or "").lower()
        if status in {"passed", "approved", "done", "accepted", "success", "succeeded"} or bool(
            report.get("passed")
        ):
            count += 1
            continue
        entity_dir = report_path.parent.parent
        if (
            (entity_dir / "_entity.json").is_file()
            and (entity_dir / "page.md").is_file()
            and (entity_dir / "manifest.json").is_file()
            and (entity_dir / "5.review" / "review.json").is_file()
            and (entity_dir / "5.review" / "provenance.json").is_file()
            and str(report.get("draftArticleRef") or "") == "4.draft/page.md"
            and str(report.get("finalArticleRef") or "") == "page.md"
            and str(report.get("draftSha256") or "").strip()
            and str(report.get("finalSha256") or "").strip()
        ):
            count += 1
    return count

def _homepage_result_entity_name(result: Any) -> str:
    text = str(result or "").lstrip()
    if not text:
        return ""
    match = re.match(r"^\*\*(.+?)\*\*\s+checkpoint", text)
    return str(match.group(1) or "").strip() if match else ""

def _homepage_agent_review_stats(
    execution_id: str,
    state: ExecutionStateTransition,
    *,
    passed_count: int = 0,
) -> dict[str, Any]:
    root = execution_root(execution_id)
    run_id_to_entity: dict[str, str] = {}
    entities_root = root / "entities"
    if entities_root.is_dir():
        for meta_path in sorted(entities_root.rglob("4.draft/draft_meta.json")):
            meta = read_json(meta_path)
            if not isinstance(meta, Mapping):
                continue
            run_id = str(meta.get("agentRunId") or "").strip()
            if run_id:
                run_id_to_entity[run_id] = meta_path.parent.parent.name
    rows: list[Any] = list(state.agent_run_history or [])
    last = state.last_agent_run
    if isinstance(last, Mapping):
        rows.append(last)
    attempts_by_entity: dict[str, list[str]] = {}
    for row in dedupe_agent_runs(rows):
        if str(row.get("stage") or "") != "build_homepage":
            continue
        outcomes = row.get("outcomes") or []
        if not isinstance(outcomes, list):
            continue
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                continue
            if str(outcome.get("status") or "") != "finished":
                continue
            run_id = str(outcome.get("runId") or "").strip()
            entity = run_id_to_entity.get(run_id) or _homepage_result_entity_name(outcome.get("result"))
            if not entity:
                continue
            marker = run_id or f"{row.get('finishedAt') or ''}:{outcome.get('jobIndex') or ''}"
            markers = attempts_by_entity.setdefault(entity, [])
            if marker not in markers:
                markers.append(marker)
    reviewed = len(attempts_by_entity)
    repaired = sum(1 for markers in attempts_by_entity.values() if len(markers) > 1)
    source = "build_homepage_agent_run_history"
    if not attempts_by_entity and passed_count > 0:
        reviewed = passed_count
        source = "homepage_finalization_count_fallback"
    elif passed_count > reviewed:
        reviewed = passed_count
        source = "build_homepage_agent_run_history_plus_finalization_count"
    return {
        "reviewedRefs": reviewed,
        "repairedRefs": repaired,
        "measurementMode": source,
    }

def _write_execution_metrics(ctx: ExecutionContext, state: ExecutionStateTransition) -> None:
    """Persist production-readiness metrics derived from batch artifacts and real usage."""
    from content.post import object_index as content_object
    from content.post.article.draft_io import (
        draft_article_path,
        draft_package_dir,
        is_placeholder,
        prompt_path,
        read_writing_pack,
        writing_pack_path,
    )
    from content.release.canonical.runtime_integrity import scan_runtime_batch_integrity
    from content.execution.production_contracts import build_token_ledger_entry
    if isinstance(state.agent_run_history, list):
        state.agent_run_history = list(dedupe_agent_runs(state.agent_run_history))[-20:]
    root = execution_root(ctx.execution_id)
    shared = root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    refs = content_object.iter_content_refs(ctx.execution_id)
    entries: list[dict[str, Any]] = []
    default_budget = active_runtime_policy().default_object_token_budget
    for ref in refs:
        coords = content_object.content_coords(ctx.execution_id, ref) or {}
        prompt = _read_text_if_file(prompt_path(ctx.execution_id, ref))
        author_packet_path = draft_package_dir(ctx.execution_id, ref) / "author_job_packet.json"
        author_packet = _read_text_if_file(author_packet_path)
        pack = author_packet or _read_text_if_file(writing_pack_path(ctx.execution_id, ref))
        draft = _read_text_if_file(draft_article_path(ctx.execution_id, ref))
        content_type = str(coords.get("contentType") or "article")
        writing_pack = read_writing_pack(ctx.execution_id, ref) or {}
        deterministic_image = (
            content_type == "image"
            and str(writing_pack.get("carrier") or "") == "image"
            and not author_packet
            and is_placeholder(draft)
        )
        used = 0 if deterministic_image else _estimate_tokens(prompt, pack, draft)
        entries.append(
            build_token_ledger_entry(
                execution_id=ctx.execution_id,
                job_id=f"artifact:{ref}",
                run_id=f"artifact:{ref}",
                creator_profile_id=required_creator_profile_id(
                    writing_pack,
                    ref=ref,
                ),
                content_type=content_type,
                budget_tokens=max(default_budget, used),
                used_tokens=used,
                cache_hits={
                    "sopSummary": False,
                    "creatorProfileSummary": False,
                    "evidencePackSummary": bool(author_packet),
                },
                cost_usd=0.0,
                provider="estimated",
            )
        )
    # homepage 实体对象不在 content refs 索引里；当前 Cursor SDK 本地 bridge
    # 不回传 usage（result 无 usage 字段、事件流无 turn-ended usage），若不按
    # 实体 draft 产物估算，homepage-only 批次会落出 entries=0 的空账本。
    from core.entity_object import collect_execution_entity_objects
    for row in collect_execution_entity_objects(ctx.execution_id):
        entity_dir = Path(row["entityDir"])
        # collect 的 page.md marker 会把 4.draft/ 等 stage 子目录误判为实体根；
        # 计量只认真实实体对象（有 _entity.json），避免同一实体重复入账。
        if not (entity_dir / "_entity.json").is_file():
            continue
        prompt = _read_text_if_file(entity_dir / "4.draft" / "prompt.md")
        draft = _read_text_if_file(entity_dir / "4.draft" / "page.md") or _read_text_if_file(
            entity_dir / "page.md"
        )
        if not prompt and not draft:
            continue
        entity_payload = read_json(entity_dir / "_entity.json")
        used = _estimate_tokens(prompt, draft)
        entries.append(
            build_token_ledger_entry(
                execution_id=ctx.execution_id,
                job_id=f"artifact:{row['entityRel']}",
                run_id=f"artifact:{row['entityRel']}",
                creator_profile_id=required_creator_profile_id(
                    entity_payload,
                    ref=str(row["entityRel"]),
                ),
                content_type="homepage",
                budget_tokens=max(default_budget, used),
                used_tokens=used,
                cost_usd=0.0,
                provider="estimated",
            )
        )
    ledger = build_token_ledger_payload(
        ctx,
        state,
        estimated_entries=entries,
        default_budget=default_budget,
    )
    write_json(shared / "token_ledger.json", ledger)
    runtime_report = scan_runtime_batch_integrity(ctx.execution_id)
    stats = runtime_report.get("stats") if isinstance(runtime_report, Mapping) else {}
    post_count = int((stats or {}).get("postCount") or 0)
    homepage_passed = _homepage_passed_count_from_artifacts(root)
    published_object_count = post_count + homepage_passed
    start = _parse_iso_seconds(state.started_at)
    end = _parse_iso_seconds(store.now_iso())
    elapsed_seconds = max(1.0, (end - start) if start and end else 1.0)
    file_elapsed = _batch_file_elapsed_seconds(root)
    if file_elapsed and file_elapsed > elapsed_seconds:
        elapsed_seconds = file_elapsed
    objects_per_hour = round((published_object_count / elapsed_seconds) * 3600, 4) if published_object_count else 0.0
    state.throughput = {
        "measurementMode": "wall_clock_current_batch",
        "elapsedSeconds": round(elapsed_seconds, 3),
        "postCount": post_count,
        "homepageCount": homepage_passed,
        "publishedObjectCount": published_object_count,
        "objectsPerHour": objects_per_hour,
        "maxWorkers": int(ctx.max_workers or 1),
        "agentActive": _agent_active_throughput(state),
    }
    repaired = _review_repaired_refs(ctx)
    homepage_review = _homepage_agent_review_stats(
        ctx.execution_id,
        state,
        passed_count=homepage_passed,
    )
    total_reviewed = len(refs) + int(homepage_review.get("reviewedRefs") or 0)
    total_repaired = len(repaired) + int(homepage_review.get("repairedRefs") or 0)
    first_pass = (
        round((total_reviewed - total_repaired) / total_reviewed, 4)
        if total_reviewed
        else 0.0
    )
    state.quality = {
        "firstPassRate": first_pass,
        "reviewedRefs": total_reviewed,
        "repairedRefs": total_repaired,
        "homepageReviewedRefs": int(homepage_review.get("reviewedRefs") or 0),
        "homepageRepairedRefs": int(homepage_review.get("repairedRefs") or 0),
        "measurementMode": (
            "repair_report_derived_plus_homepage_history"
            if homepage_review.get("reviewedRefs")
            else "repair_report_derived"
        ),
        "homepageMeasurementMode": str(homepage_review.get("measurementMode") or ""),
    }
