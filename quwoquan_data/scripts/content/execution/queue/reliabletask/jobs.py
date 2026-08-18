"""Declare object jobs from frozen execution artefacts for ReliableTask."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from core.control_types import QueueBackend, QueueJobStage
from core.io import read_json
from governance.creators.assignment import creator_from_payload

from content.execution.context import ExecutionContext
from content.execution.production_contracts import sha256_file
from content.execution.queue.jobs import enqueue_ref_job
from content.execution.queue.model import QueueJob
from content.execution.runtime_contract import canonical_sha256


def uses_reliabletask(
    ctx: ExecutionContext,
    *,
    stage: QueueJobStage | str | None = None,
) -> bool:
    if stage is not None and QueueJobStage(str(stage)) is QueueJobStage.PUBLISH:
        from content.execution.queue.backend import load_execution_queue_backend

        envelope = load_execution_queue_backend(ctx.execution_id)
        return (
            str(envelope.get("poolDeliveryBackend") or "")
            == QueueBackend.RELIABLE_TASK.value
        )
    return str(ctx.spec.queue_policy.backend) == QueueBackend.RELIABLE_TASK.value


def _canonical_entity_ref(payload: Mapping[str, object]) -> str:
    candidates = payload.get("entityRefs")
    if isinstance(candidates, list):
        for raw in candidates:
            ref = str(raw or "").strip()
            if ref.startswith("/entity/"):
                return ref
    ref = str(payload.get("entityRef") or payload.get("targetRef") or "").strip()
    return ref if ref.startswith("/entity/") else ""


def _post_source_revision(
    packet: Mapping[str, object],
    writing_pack: Mapping[str, object],
    *,
    author_packet: Path | None = None,
    author_prompt: Path | None = None,
    repair_report: Path | None = None,
) -> str:
    files: list[dict[str, str]] = []
    for raw in packet.get("sourcePaths") or []:
        path = Path(str(raw or "").strip())
        if path.is_file():
            files.append({"path": path.name, "sha256": sha256_file(path)})
    payload: dict[str, object] = {
        "baseSourceRef": packet.get("baseSourceRef"),
        "writingPack": writing_pack,
        "sourceFiles": sorted(files, key=lambda row: (row["path"], row["sha256"])),
    }
    if repair_report is not None and repair_report.is_file():
        payload["repairReportSha256"] = sha256_file(repair_report)
    if author_packet is not None and author_packet.is_file():
        payload["authorPacketSha256"] = sha256_file(author_packet)
    if author_prompt is not None and author_prompt.is_file():
        payload["authorPromptSha256"] = sha256_file(author_prompt)
    return canonical_sha256(payload)


def post_author_job_definition(
    ctx: ExecutionContext,
    ref: str,
) -> tuple[str, dict[str, object]]:
    """Derive the canonical mutex and identity metadata for one author job."""
    from content.post import object_index as content_object
    from content.post.article.draft_io import draft_package_dir, read_writing_pack

    packet_path = draft_package_dir(ctx.execution_id, ref) / "author_job_packet.json"
    if not packet_path.is_file():
        raise ValueError(f"ReliableTask author packet missing: {ref}")
    packet = read_json(packet_path)
    pack = read_writing_pack(ctx.execution_id, ref) or {}
    brief = content_object.read_brief_object(ctx.execution_id, ref) or {}
    carrier = str(packet.get("carrier") or pack.get("carrier") or "").strip()
    entity_ref = (
        _canonical_entity_ref(pack)
        or _canonical_entity_ref(brief)
        or _canonical_entity_ref(packet)
    )
    if not carrier or not entity_ref:
        raise ValueError(
            f"ReliableTask author identity incomplete: ref={ref} "
            f"carrier={carrier!r} entityRef={entity_ref!r}"
        )
    creator_payload = packet.get("creatorAssignment")
    creator = (
        creator_from_payload(creator_payload)
        if isinstance(creator_payload, Mapping)
        else {}
    )
    metadata: dict[str, object] = {
        "contentType": carrier,
        "carrier": carrier,
        "entityRef": entity_ref,
        "sourceRevision": _post_source_revision(
            packet,
            pack,
            author_packet=packet_path,
            author_prompt=draft_package_dir(ctx.execution_id, ref) / "prompt.md",
            repair_report=draft_package_dir(ctx.execution_id, ref).parent
            / "5.review"
            / "repair_report.json",
        ),
        "sourceUnitId": str(packet.get("baseSourceRef") or ""),
        "contentObjectDir": content_object.content_object_rel(
            ctx.execution_id,
            ref,
        ),
        **creator,
    }
    return str(packet.get("baseSourceRef") or ref), metadata


def _prepare_post_author_jobs(
    ctx: ExecutionContext,
    prompts: list[str],
) -> int:
    from content.execution.agent.agent_checkpoint import _managed_author_ref

    created = 0
    for prompt in prompts:
        ref = _managed_author_ref(prompt)
        if not ref:
            continue
        mutex_key, metadata = post_author_job_definition(ctx, ref)
        enqueue_ref_job(
            ctx.execution_id,
            ref,
            "author",
            mutex_key=mutex_key,
            meta=metadata,
            queue_backend=QueueBackend.RELIABLE_TASK,
        )
        created += 1
    return created


def _prepare_homepage_author_jobs(
    ctx: ExecutionContext,
    prompts: list[str],
) -> int:
    from governance.coverage.entity_extract import entity_ref, require_domain_etype

    from content.execution.agent.agent_checkpoint import _managed_prompt_entity
    from content.homepage.homepage_review import _entity_draft_dir

    created = 0
    for prompt in prompts:
        entity = _managed_prompt_entity(prompt)
        target = next(
            (item for item in ctx.spec.scope.coverage_targets if item.name == entity),
            None,
        )
        if target is None:
            continue
        domain, entity_type = require_domain_etype(target.entity_type, context=entity)
        object_ref = entity_ref(domain, entity_type, entity)
        draft_dir = _entity_draft_dir(
            ctx.execution_id,
            domain,
            entity_type,
            entity,
        )
        packet_path = draft_dir / "author_job_packet.json"
        compose_path = draft_dir.parent / "3.compose" / "entity_page_input.json"
        if not packet_path.is_file() or not compose_path.is_file():
            raise ValueError(
                "ReliableTask homepage author artefacts missing for "
                f"{object_ref}: require author_job_packet.json and "
                "entity_page_input.json from build_prepare"
            )
        packet = read_json(packet_path)
        compose = read_json(compose_path)
        source_revision = str(compose.get("sourceRevision") or "").strip()
        if not source_revision:
            source_revision = canonical_sha256(compose)
        repair_report = draft_dir.parent / "5.review" / "repair_report.json"
        envelope_path = draft_dir / "agent_result_envelope.json"
        repair_is_newer = False
        if repair_report.is_file():
            try:
                repair_is_newer = (
                    not envelope_path.is_file()
                    or repair_report.stat().st_mtime >= envelope_path.stat().st_mtime
                )
            except OSError as exc:
                raise RuntimeError(
                    f"homepage author repair evidence unreadable: {object_ref}"
                ) from exc
            source_revision = canonical_sha256(
                {
                    "sourceRevision": source_revision,
                    "repairReportSha256": sha256_file(repair_report),
                }
            )
        if repair_is_newer:
            from content.execution.queue.management import purge_jobs

            purge_jobs(
                ctx.execution_id,
                stage="author",
                refs=[object_ref],
            )
        creator_payload = compose.get("creatorAssignment")
        creator = (
            creator_from_payload(creator_payload)
            if isinstance(creator_payload, Mapping)
            else {}
        )
        from core.paths import execution_root

        content_object_dir = draft_dir.parent.relative_to(
            execution_root(ctx.execution_id)
        ).as_posix()
        enqueue_ref_job(
            ctx.execution_id,
            object_ref,
            "author",
            mutex_key=object_ref,
            # 首轮成稿后，最多保留两次确定性 materialization 反馈修复机会。
            max_attempts=3,
            meta={
                "contentType": "homepage",
                "carrier": "homepage",
                "entityRef": object_ref,
                "sourceRevision": source_revision,
                "contentObjectDir": content_object_dir,
                **creator,
            },
            queue_backend=QueueBackend.RELIABLE_TASK,
        )
        expected_packet_ref = str(packet.get("objectRef") or "")
        if expected_packet_ref != object_ref:
            raise ValueError(
                f"homepage author packet objectRef mismatch: {expected_packet_ref!r}"
            )
        created += 1
    return created


def prepare_reliable_author_jobs(
    ctx: ExecutionContext,
    checkpoint: str,
) -> int:
    """Create one strongly bound ReliableTask job for every pending author prompt."""
    if not uses_reliabletask(ctx):
        return 0
    from content.execution.agent.checkpoint_prompts import _checkpoint_prompts

    prompts = _checkpoint_prompts(ctx, checkpoint)
    if checkpoint == "build_homepage":
        return _prepare_homepage_author_jobs(ctx, prompts)
    if checkpoint == "post_author":
        return _prepare_post_author_jobs(ctx, prompts)
    return 0


def _post_entity_ref(execution_id: str, ref: str) -> str:
    from content.post import object_index as content_object

    brief = content_object.read_brief_object(execution_id, ref) or {}
    entity_ref = _canonical_entity_ref(brief)
    if not entity_ref:
        raise ValueError(f"ReliableTask publish post 缺 entityRef：{ref}")
    return entity_ref


def prepare_reliable_publish_jobs(
    ctx: ExecutionContext,
    *,
    homepage_refs: set[str] | None = None,
) -> tuple[QueueJob, ...]:
    """Declare one publish transaction task per reviewed canonical object."""
    if not uses_reliabletask(ctx, stage=QueueJobStage.PUBLISH):
        return ()
    from core.paths import execution_root

    from content.execution.closure.pool_delivery import write_pool_delivery_intent
    from content.execution.closure.publish_outcome import is_hard_publish_failure
    from content.release.canonical.object_transaction_contract import (
        ObjectTransactionError,
    )

    root = execution_root(ctx.execution_id)
    jobs: list[QueueJob] = []
    # 被跳过的对象最终只会在 publish 收口时变成一条无信息的
    # OBJECT_PREPARATION_FAILED。把每次跳过的具体原因留成证据，否则 publish
    # 失败无法归因，还会连带耗尽 reviewer 的 attempt 预算。
    skips: list[dict[str, str]] = []

    def _record_skip(object_ref: str, reason: str) -> None:
        skips.append({"objectRef": object_ref, "reason": reason})

    for object_ref in sorted(homepage_refs or set()):
        canonical_ref = object_ref.removeprefix("/entity/")
        object_dir = root / "entities" / canonical_ref
        relative = object_dir.relative_to(root).as_posix()
        try:
            intent, intent_path = write_pool_delivery_intent(
                ctx.execution_id,
                carrier="homepage",
                object_ref=object_ref,
                content_object_dir=relative,
            )
        except (ObjectTransactionError, ValueError) as exc:
            if is_hard_publish_failure(exc):
                raise
            _record_skip(
                object_ref,
                f"pool delivery intent failed: {type(exc).__name__}: {exc}",
            )
            continue
        jobs.append(
            enqueue_ref_job(
                ctx.execution_id,
                object_ref,
                "publish",
                mutex_key="canonical-publish",
                meta={
                    "contentType": "homepage",
                    "carrier": "homepage",
                    "entityRef": object_ref,
                    "sourceRevision": intent["transactionInputDigest"],
                    "contentObjectDir": relative,
                    "poolDeliveryIntentRef": intent_path.relative_to(root).as_posix(),
                    "poolDeliveryIntentDigest": intent["intentId"],
                },
                queue_backend=QueueBackend.RELIABLE_TASK,
            )
        )
    if homepage_refs is not None:
        _write_publish_job_skips(ctx.execution_id, skips)
        return tuple(jobs)
    from content.execution.closure.post_review import (
        indexed_post_targets,
        load_post_review_closure,
    )

    closure = load_post_review_closure(
        ctx.execution_id,
        expected_object_targets=indexed_post_targets(ctx.execution_id),
        require_quota_milestone=False,
    )
    for verdict in closure.qualified:
        ref = verdict.object_ref
        object_dir = root / verdict.publish_ref
        attestation = object_dir / "5.review" / "attestation.json"
        if not attestation.is_file() or not (object_dir / "manifest.json").is_file():
            _record_skip(
                ref,
                "missing publish inputs: "
                f"attestation={attestation.is_file()} "
                f"manifest={(object_dir / 'manifest.json').is_file()}",
            )
            continue
        review = read_json(attestation)
        if review.get("decision") != "approved":
            _record_skip(ref, f"attestation decision={review.get('decision')!r}")
            continue
        relative = verdict.publish_ref
        carrier = relative.split("/", 2)[1] if relative.startswith("posts/") else ""
        if not carrier:
            _record_skip(ref, f"carrier unresolved from publishRef={relative!r}")
            continue
        try:
            entity_ref = _post_entity_ref(ctx.execution_id, ref)
            intent, intent_path = write_pool_delivery_intent(
                ctx.execution_id,
                carrier=carrier,
                object_ref=ref,
                content_object_dir=relative,
            )
        except (ObjectTransactionError, ValueError) as exc:
            if is_hard_publish_failure(exc):
                raise
            _record_skip(
                ref,
                f"pool delivery intent failed: {type(exc).__name__}: {exc}",
            )
            continue
        jobs.append(
            enqueue_ref_job(
                ctx.execution_id,
                ref,
                "publish",
                mutex_key="canonical-publish",
                meta={
                    "contentType": carrier,
                    "carrier": carrier,
                    "entityRef": entity_ref,
                    "sourceRevision": intent["transactionInputDigest"],
                    "contentObjectDir": relative,
                    "poolDeliveryIntentRef": intent_path.relative_to(root).as_posix(),
                    "poolDeliveryIntentDigest": intent["intentId"],
                },
                queue_backend=QueueBackend.RELIABLE_TASK,
            )
        )
    _write_publish_job_skips(ctx.execution_id, skips)
    return tuple(jobs)


def _write_publish_job_skips(
    execution_id: str,
    skips: Sequence[Mapping[str, str]],
) -> None:
    """Keep why each reviewed object never became a publish job."""
    if not skips:
        return
    from core.io import write_json
    from core.paths import execution_root

    write_json(
        execution_root(execution_id) / "evidence/publish_job_skips.json",
        {
            "schema": "quwoquan_data.publish_job_skips",
            "executionId": execution_id,
            "skips": [dict(row) for row in skips],
        },
    )


__all__ = [
    "prepare_reliable_author_jobs",
    "prepare_reliable_publish_jobs",
    "uses_reliabletask",
]
