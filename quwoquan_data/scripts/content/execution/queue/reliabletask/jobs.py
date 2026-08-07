"""Declare object jobs from frozen execution artefacts for ReliableTask."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from core.control_types import QueueBackend
from core.io import read_json
from content.execution.context import ExecutionContext
from content.execution.production_contracts import sha256_file
from content.execution.queue.jobs import enqueue_ref_job
from content.execution.queue.model import QueueJob
from content.execution.runtime_contract import canonical_sha256
from governance.creators.assignment import creator_from_payload


def uses_reliabletask(ctx: ExecutionContext) -> bool:
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
) -> str:
    files: list[dict[str, str]] = []
    for raw in packet.get("sourcePaths") or []:
        path = Path(str(raw or "").strip())
        if path.is_file():
            files.append({"path": path.name, "sha256": sha256_file(path)})
    return canonical_sha256(
        {
            "baseSourceRef": packet.get("baseSourceRef"),
            "writingPack": writing_pack,
            "sourceFiles": sorted(files, key=lambda row: (row["path"], row["sha256"])),
        }
    )


def _prepare_post_author_jobs(
    ctx: ExecutionContext,
    prompts: list[str],
) -> int:
    from content.execution.agent.agent_checkpoint import _managed_author_ref
    from content.post import object_index as content_object
    from content.post.article.draft_io import draft_package_dir, read_writing_pack

    created = 0
    for prompt in prompts:
        ref = _managed_author_ref(prompt)
        if not ref:
            continue
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
            "sourceRevision": _post_source_revision(packet, pack),
            "sourceUnitId": str(packet.get("baseSourceRef") or ""),
            "contentObjectDir": content_object.content_object_rel(
                ctx.execution_id,
                ref,
            ),
            **creator,
        }
        enqueue_ref_job(
            ctx.execution_id,
            ref,
            "author",
            mutex_key=str(packet.get("baseSourceRef") or ref),
            meta=metadata,
            queue_backend=QueueBackend.RELIABLE_TASK,
        )
        created += 1
    return created


def _prepare_homepage_author_jobs(
    ctx: ExecutionContext,
    prompts: list[str],
) -> int:
    from content.execution.agent.agent_checkpoint import _managed_prompt_entity
    from content.homepage.homepage_review import _entity_draft_dir
    from governance.coverage.entity_extract import entity_ref, require_domain_etype

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
    if not uses_reliabletask(ctx):
        return ()
    from core.paths import execution_root
    from core.tree_integrity import tree_integrity_stats

    root = execution_root(ctx.execution_id)
    jobs: list[QueueJob] = []
    for object_ref in sorted(homepage_refs or set()):
        canonical_ref = object_ref.removeprefix("/entity/")
        object_dir = root / "entities" / canonical_ref
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
                    "sourceRevision": str(
                        tree_integrity_stats(object_dir)["merkleRoot"]
                    ),
                    "contentObjectDir": object_dir.relative_to(root).as_posix(),
                },
                queue_backend=QueueBackend.RELIABLE_TASK,
            )
        )
    if homepage_refs is not None:
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
            raise ValueError(f"qualified post evidence is incomplete: {ref}")
        review = read_json(attestation)
        if review.get("decision") != "approved":
            raise ValueError(f"qualified post is no longer review-approved: {ref}")
        relative = verdict.publish_ref
        carrier = relative.split("/", 2)[1] if relative.startswith("posts/") else ""
        if not carrier:
            raise ValueError(f"ReliableTask publish object path 无载体：{relative}")
        jobs.append(
            enqueue_ref_job(
                ctx.execution_id,
                ref,
                "publish",
                mutex_key="canonical-publish",
                meta={
                    "contentType": carrier,
                    "carrier": carrier,
                    "entityRef": _post_entity_ref(ctx.execution_id, ref),
                    "sourceRevision": str(
                        tree_integrity_stats(object_dir)["merkleRoot"]
                    ),
                    "contentObjectDir": relative,
                },
                queue_backend=QueueBackend.RELIABLE_TASK,
            )
        )
    return tuple(jobs)


__all__ = [
    "prepare_reliable_author_jobs",
    "prepare_reliable_publish_jobs",
    "uses_reliabletask",
]
