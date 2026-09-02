"""CLI-first binding for offline four-carrier source-ready pools."""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path

from core.paths import SOURCE_ACQUISITION_ROOT
from content.execution.planning.carrier_demand import normalize_workloads

from content.source.professional_image_discovery_governed import (
    build_professional_image_governed_candidate_catalog,
    write_professional_image_governed_candidate_catalog,
)
from content.source.research.pre_acquisition_handoff_cli import (
    handle_prepare_handoff as prepare_pre_acquisition_handoff,
)
from content.source.research.handler_cli_io import (
    canonical_candidates_destination,
    canonical_pool_destination,
    file_sha256,
    load_array,
    load_candidates,
    load_object,
    print_document,
    typed_error,
)
from content.source.research.homepage_article_seed_selection_writer import (
    register_seed_selection_parser,
)
from content.source.research.homepage_article_source_ready_acquisition import (
    acquire_homepage_article_source_ready_batch,
)
from content.source.research.homepage_article_source_ready_aggregate import (
    merge_homepage_article_source_ready_batches,
)
from content.source.research.homepage_article_source_ready_batch import (
    freeze_homepage_article_source_ready_batch,
)
from content.source.research.media_source_admission_cli import (
    register_media_source_admission_parsers,
)
from content.source.research.host_source_review_cli import (
    register_host_source_review_parsers,
)
from content.source.research.professional_image_manual_file_evidence_cli import (
    register_professional_image_manual_file_evidence_parser,
)
from content.source.research.scale_source_pool import (
    build_scale_source_pool_plan,
    validate_scale_source_pool,
    validate_scale_source_pool_evidence,
    write_create_once_scale_source_pool,
)
from content.source.research.scale_source_pool_candidates import (
    build_scale_source_pool_candidates,
    write_create_once_scale_source_pool_candidates,
)
from content.source.research.scale_source_pool_homepage_article import (
    project_scale_source_pool_homepage_article,
)
from content.source.research.scale_source_pool_image_video import (
    project_scale_source_pool_image_video,
)


def _workload_targets(args: argparse.Namespace) -> dict[str, int] | None:
    rows = tuple(getattr(args, "workload", ()) or ())
    if not rows:
        return None
    values: dict[str, int] = {}
    for raw in rows:
        carrier, separator, quota = str(raw).partition("=")
        carrier = carrier.strip()
        quota = quota.strip()
        if not separator or carrier in values:
            raise ValueError("--workload must be unique CARRIER=QUOTA values")
        try:
            values[carrier] = int(quota)
        except ValueError as exc:
            raise ValueError("--workload quota must be a positive integer") from exc
    return normalize_workloads(values)


def handle_prepare_handoff(args: argparse.Namespace) -> None:
    workloads = _workload_targets(args)
    if workloads is None:
        raise SystemExit("[source-pool prepare-handoff] GATE_BLOCK requires --workload")
    prepare_pre_acquisition_handoff(args, workload_targets=workloads)


def handle_plan(args: argparse.Namespace) -> None:
    try:
        workloads = _workload_targets(args)
        if workloads is not None and args.target_scale is not None:
            raise ValueError("explicit --workload forbids --target-scale")
        if workloads is None and args.target_scale is None:
            raise ValueError("plan requires --workload or --target-scale preset")
        plan = build_scale_source_pool_plan(
            pool_id=args.pool_id,
            target_scale=args.target_scale,
            source_revision=args.source_revision,
            source_digest=args.source_digest,
            entity_catalog_digest=args.entity_catalog_digest,
            created_at=args.created_at,
            candidates=load_candidates(args.candidates),
            workload_targets=workloads,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[source-pool plan] GATE_BLOCK {typed_error(exc)}") from exc
    print_document(plan)


def handle_validate(args: argparse.Namespace) -> None:
    try:
        validation = validate_scale_source_pool_evidence(
            load_object(args.plan, label="plan"),
            evidence_root=Path(args.evidence_root),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[source-pool validate] GATE_BLOCK {typed_error(exc)}"
        ) from exc
    print_document(validation)


def handle_write(args: argparse.Namespace) -> None:
    try:
        plan = load_object(args.plan, label="plan")
        output_root = Path(
            args.output_root or SOURCE_ACQUISITION_ROOT
        ).expanduser().resolve()
        destination = canonical_pool_destination(plan, output_root=output_root)
        frozen = write_create_once_scale_source_pool(
            destination,
            plan,
            evidence_root=Path(args.evidence_root),
        )
        validation = validate_scale_source_pool(frozen)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[source-pool write] GATE_BLOCK {typed_error(exc)}") from exc
    print_document(
        {
            "schema": "quwoquan_data.scale_source_pool_write_result",
            "planRef": destination.relative_to(output_root).as_posix(),
            "planDigest": frozen["planDigest"],
            "decision": validation["decision"],
        }
    )


def handle_project_candidates(args: argparse.Namespace) -> None:
    try:
        evidence_root = Path(args.evidence_root).expanduser().absolute()
        workloads = _workload_targets(args)
        if workloads is not None and args.target_scale is not None:
            raise ValueError("explicit --workload forbids --target-scale")
        if workloads is None and args.target_scale is None:
            raise ValueError(
                "project-candidates requires --workload or --target-scale preset"
            )
        requested_active = tuple(args.active_carrier or ())
        active_carriers = tuple(workloads or requested_active)
        if not active_carriers:
            raise ValueError("project-candidates requires at least one --workload")
        if requested_active and requested_active != active_carriers:
            raise ValueError("--active-carrier must exactly match --workload keys")
        homepage_article = None
        if set(active_carriers) & {"homepage", "article"}:
            homepage_article = project_scale_source_pool_homepage_article(
                evidence_root=evidence_root,
                homepage_catalog_ref=args.homepage_catalog_ref,
                homepage_catalog_digest=args.homepage_catalog_digest,
                homepage_catalog_file_sha256=args.homepage_catalog_file_sha256,
                article_catalog_ref=args.article_catalog_ref,
                article_catalog_digest=args.article_catalog_digest,
                article_catalog_file_sha256=args.article_catalog_file_sha256,
                source_ready_set_ref=args.source_ready_set_ref,
                source_ready_set_digest=args.source_ready_set_digest,
                source_ready_set_file_sha256=args.source_ready_set_file_sha256,
                active_carriers=tuple(
                    carrier
                    for carrier in active_carriers
                    if carrier in {"homepage", "article"}
                ),
            )
        image_video = None
        if set(active_carriers) & {"image", "video"}:
            if not args.entity_catalog_ref:
                raise ValueError(
                    "--entity-catalog-ref is required for Image/Video projection"
                )
            image_video = project_scale_source_pool_image_video(
                evidence_root=evidence_root,
                target_scale=(args.target_scale or "WORKLOAD"),
                source_revision=args.source_revision,
                source_digest=args.source_digest,
                entity_catalog_digest=args.entity_catalog_digest,
                entity_catalog_ref=args.entity_catalog_ref,
                image_source_admission_refs=args.image_source_admission_ref,
                video_source_admission_refs=args.video_source_admission_ref,
            )
        candidates = build_scale_source_pool_candidates(
            target_scale=args.target_scale,
            source_revision=args.source_revision,
            source_digest=args.source_digest,
            entity_catalog_digest=args.entity_catalog_digest,
            homepage_article_projection=homepage_article,
            image_video_projection=image_video,
            active_carriers=active_carriers,
            workload_targets=workloads,
        )
        output_root = Path(
            args.output_root or SOURCE_ACQUISITION_ROOT
        ).expanduser().resolve()
        destination = canonical_candidates_destination(
            candidates,
            output_root=output_root,
        )
        frozen = write_create_once_scale_source_pool_candidates(
            destination,
            candidates,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[source-pool project-candidates] GATE_BLOCK {typed_error(exc)}"
        ) from exc
    print_document(
        {
            "schema": "quwoquan_data.scale_source_pool_candidates_write_result",
            "targetScale": frozen["targetScale"],
            "candidatesRef": destination.relative_to(output_root).as_posix(),
            "candidatesDigest": frozen["candidatesDigest"],
            "activeCarriers": frozen["activeCarriers"],
            "workloadTargets": frozen["workloadTargets"],
            "candidateCounts": frozen["candidateCounts"],
            "projectionBindings": frozen["projectionBindings"],
        }
    )


def handle_freeze_homepage_article_catalogs(args: argparse.Namespace) -> None:
    try:
        output_root = Path(
            args.output_root or SOURCE_ACQUISITION_ROOT
        ).expanduser().resolve()
        result = freeze_homepage_article_source_ready_batch(
            Path(args.source_ready_manifest),
            evidence_root=Path(args.evidence_root),
            output_root=output_root,
            minimum_homepage_candidate_count=args.minimum_homepage_candidate_count,
            minimum_article_candidate_count=args.minimum_article_candidate_count,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            "[source-pool freeze-homepage-article-catalogs] GATE_BLOCK "
            f"{typed_error(exc)}"
        ) from exc
    print_document(result)


def handle_merge_homepage_article(args: argparse.Namespace) -> None:
    try:
        result = merge_homepage_article_source_ready_batches(
            batch_manifests=[Path(value) for value in args.source_ready_manifest],
            output_root=Path(args.output_root or SOURCE_ACQUISITION_ROOT),
            source_set_id=args.source_set_id,
            target_scale=args.target_scale,
            source_revision=args.source_revision,
            source_digest=args.source_digest,
            entity_catalog_digest=args.entity_catalog_digest,
            created_at=args.created_at,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            "[source-pool merge-homepage-article] GATE_BLOCK "
            f"{typed_error(exc)}"
        ) from exc
    print_document(result)


def handle_acquire_homepage_article(args: argparse.Namespace) -> None:
    try:
        result = acquire_homepage_article_source_ready_batch(
            coverage_run_dir=Path(args.coverage_run_dir),
            output_root=Path(
                args.output_root or SOURCE_ACQUISITION_ROOT
            ),
            source_set_id=args.source_set_id,
            target_scale=args.target_scale,
            source_revision=args.source_revision,
            source_digest=args.source_digest,
            entity_catalog_digest=args.entity_catalog_digest,
            captured_at=args.captured_at,
            homepage_count=args.homepage_count,
            article_count=args.article_count,
            seed_selection=Path(args.seed_selection),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        checkpoint = getattr(exc, "checkpoint", None)
        if isinstance(checkpoint, Mapping):
            print_document(checkpoint)
        raise SystemExit(
            "[source-pool acquire-homepage-article] GATE_BLOCK "
            f"{typed_error(exc)}"
        ) from exc
    print_document(result)


def handle_freeze_professional_image_catalog(args: argparse.Namespace) -> None:
    try:
        output_root = Path(
            args.output_root or SOURCE_ACQUISITION_ROOT
        ).expanduser().resolve()
        catalog_root = (
            output_root / "professional-image-candidate-catalogs" / "governed"
        )
        catalog = build_professional_image_governed_candidate_catalog(
            discovery_plan_id=args.discovery_plan_id,
            discovery_plan_digest=args.discovery_plan_digest,
            created_at=args.created_at,
            evidence_root=Path(args.evidence_root),
            evidence_refs=args.evidence_ref,
        )
        destination = write_professional_image_governed_candidate_catalog(
            catalog,
            output_root=catalog_root,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[source-pool freeze-professional-image-catalog] GATE_BLOCK "
            f"{typed_error(exc)}"
        ) from exc
    print_document(
        {
            "schema": "quwoquan_data.professional_image_governed_catalog_write_result",
            "catalogRef": destination.relative_to(output_root).as_posix(),
            "catalogDigest": catalog["catalogDigest"],
            "catalogFileSha256": file_sha256(destination),
            "candidateCount": catalog["candidateCount"],
            "providerCounts": catalog["providerCounts"],
        }
    )


def handle_freeze_professional_video_catalog(args: argparse.Namespace) -> None:
    from content.source.professional_video_popular_catalog import (
        build_professional_video_popular_candidate_catalog,
        write_create_once_professional_video_popular_candidate_catalog,
    )

    try:
        output_root = Path(
            args.output_root or (SOURCE_ACQUISITION_ROOT / "video")
        ).expanduser().resolve()
        catalog = build_professional_video_popular_candidate_catalog(
            source_revision=args.source_revision,
            source_digest=args.source_digest,
            entity_catalog_digest=args.entity_catalog_digest,
            metadata_responses=load_array(
                args.metadata_responses, label="supported API metadata responses"
            ),
            manual_file_manifests=load_array(
                args.manual_file_manifests, label="manual video manifests"
            ),
            evidence_root=Path(args.evidence_root),
        )
        destination = (
            output_root
            / "professional-video-popular-catalogs"
            / f"{catalog['catalogDigest'].removeprefix('sha256:')}.json"
        )
        frozen = write_create_once_professional_video_popular_candidate_catalog(
            destination, catalog
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[source-pool freeze-professional-video-catalog] GATE_BLOCK "
            f"{typed_error(exc)}"
        ) from exc
    print_document({
        "schema": "quwoquan_data.professional_video_popular_catalog_write_result",
        "catalogRef": destination.relative_to(output_root).as_posix(),
        "catalogDigest": frozen["catalogDigest"],
        "catalogFileSha256": file_sha256(destination),
        "candidateCount": frozen["candidateCount"],
        "providerCounts": frozen["providerCounts"],
    })


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "source-pool",
        help="离线冻结、验证并 create-once 写入四载体规模 source-ready pool",
    )
    commands = parser.add_subparsers(dest="source_pool_command", required=True)
    register_seed_selection_parser(commands)
    register_host_source_review_parsers(commands)

    handoff = commands.add_parser(
        "prepare-handoff",
        help="从显式需求 create-once 冻结 current-identity pre-acquisition handoff",
    )
    handoff.add_argument("--handoff-id", required=True)
    handoff.add_argument("--handoff-revision", type=int, required=True)
    handoff.add_argument("--supersedes-handoff-ref")
    handoff.add_argument("--vertical", required=True)
    handoff.add_argument("--lifecycle", choices=("research", "commercial"), required=True)
    handoff.add_argument(
        "--scope-type",
        choices=("vertical", "region", "topic", "region_topic"),
        required=True,
    )
    handoff.add_argument("--region-ref")
    handoff.add_argument("--primary-topic-ref")
    handoff.add_argument("--related-topic-ref", action="append", default=[])
    handoff.add_argument("--run-date", required=True)
    handoff.add_argument("--sequence", type=int, required=True)
    handoff.add_argument("--retry-of")
    handoff.add_argument("--source-selection", action="append", required=True)
    handoff.add_argument("--workload", action="append", required=True)
    handoff.set_defaults(handler=handle_prepare_handoff)

    acquire_content = commands.add_parser(
        "acquire-homepage-article",
        help="从 current-identity coverage 与公开 MediaWiki 原始证据冻结 source-ready capsules",
    )
    acquire_content.add_argument("--coverage-run-dir", required=True)
    acquire_content.add_argument("--source-set-id", required=True)
    acquire_content.add_argument(
        "--target-scale",
        choices=("WORKLOAD", "M100", "M1000", "M10000"),
        required=True,
        help="WORKLOAD 表示 explicit 按需小批采集；M100+ 为 milestone preset",
    )
    acquire_content.add_argument("--source-revision", required=True)
    acquire_content.add_argument("--source-digest", required=True)
    acquire_content.add_argument("--entity-catalog-digest", required=True)
    acquire_content.add_argument("--captured-at", required=True)
    acquire_content.add_argument("--homepage-count", type=int, required=True)
    acquire_content.add_argument("--article-count", type=int, required=True)
    acquire_content.add_argument(
        "--seed-selection",
        required=True,
        help="identity-free historical hints intersected with fresh coverage evidence",
    )
    acquire_content.add_argument("--output-root")
    acquire_content.set_defaults(handler=handle_acquire_homepage_article)

    merge_content = commands.add_parser(
        "merge-homepage-article",
        help="逐字节复验并 create-once 合并同 identity 的 source-ready batches",
    )
    merge_content.add_argument("--source-ready-manifest", action="append", required=True)
    merge_content.add_argument("--source-set-id", required=True)
    merge_content.add_argument(
        "--target-scale",
        choices=("WORKLOAD", "M100", "M1000", "M10000"),
        required=True,
    )
    merge_content.add_argument("--source-revision", required=True)
    merge_content.add_argument("--source-digest", required=True)
    merge_content.add_argument("--entity-catalog-digest", required=True)
    merge_content.add_argument("--created-at", required=True)
    merge_content.add_argument("--output-root")
    merge_content.set_defaults(handler=handle_merge_homepage_article)

    freeze_content = commands.add_parser(
        "freeze-homepage-article-catalogs",
        help="从 immutable physical capsules 单轨冻结 homepage/article catalogs",
    )
    freeze_content.add_argument("--source-ready-manifest", required=True)
    freeze_content.add_argument("--evidence-root", required=True)
    freeze_content.add_argument(
        "--minimum-homepage-candidate-count", type=int, required=True
    )
    freeze_content.add_argument(
        "--minimum-article-candidate-count", type=int, required=True
    )
    freeze_content.add_argument("--output-root")
    freeze_content.set_defaults(handler=handle_freeze_homepage_article_catalogs)

    freeze_image = commands.add_parser(
        "freeze-professional-image-catalog",
        help="从 manual_file/supported_api 证据 create-once 冻结专业图片 catalog",
    )
    freeze_image.add_argument("--discovery-plan-id", required=True)
    freeze_image.add_argument("--discovery-plan-digest", required=True)
    freeze_image.add_argument("--created-at", required=True)
    freeze_image.add_argument("--evidence-root", required=True)
    freeze_image.add_argument("--evidence-ref", action="append", required=True)
    freeze_image.add_argument("--output-root")
    freeze_image.set_defaults(handler=handle_freeze_professional_image_catalog)

    register_professional_image_manual_file_evidence_parser(commands)

    freeze_video = commands.add_parser(
        "freeze-professional-video-catalog",
        help="从 supported API metadata 与人工文件清单冻结热门视频 catalog",
    )
    freeze_video.add_argument("--source-revision", required=True)
    freeze_video.add_argument("--source-digest", required=True)
    freeze_video.add_argument("--entity-catalog-digest", required=True)
    freeze_video.add_argument("--metadata-responses", required=True)
    freeze_video.add_argument("--manual-file-manifests", required=True)
    freeze_video.add_argument("--evidence-root", required=True)
    freeze_video.add_argument("--output-root")
    freeze_video.set_defaults(handler=handle_freeze_professional_video_catalog)

    register_media_source_admission_parsers(commands)

    project = commands.add_parser(
        "project-candidates",
        help="从当前 wave 的 catalog/evidence 确定性 create-once 投影候选文件",
    )
    project.add_argument(
        "--target-scale",
        choices=("M100", "M1000", "M10000"),
        help="仅 milestone preset 使用；显式 --workload 时省略",
    )
    project.add_argument("--source-revision", required=True)
    project.add_argument("--source-digest", required=True)
    project.add_argument("--entity-catalog-digest", required=True)
    project.add_argument(
        "--entity-catalog-ref",
        help="版本控制实体主表 ref；Image/Video 投影必填且必须命中 digest",
    )
    project.add_argument("--evidence-root", required=True)
    project.add_argument("--output-root")
    project.add_argument(
        "--active-carrier",
        action="append",
        choices=("homepage", "article", "image", "video"),
        required=False,
    )
    project.add_argument(
        "--workload",
        action="append",
        metavar="CARRIER=QUOTA",
        help="显式活动载体及其精确目标；可重复传入",
    )
    project.add_argument("--homepage-catalog-ref")
    project.add_argument("--homepage-catalog-digest")
    project.add_argument("--homepage-catalog-file-sha256")
    project.add_argument("--article-catalog-ref")
    project.add_argument("--article-catalog-digest")
    project.add_argument("--article-catalog-file-sha256")
    project.add_argument("--source-ready-set-ref")
    project.add_argument("--source-ready-set-digest")
    project.add_argument("--source-ready-set-file-sha256")
    project.add_argument("--image-source-admission-ref", action="append")
    project.add_argument("--video-source-admission-ref", action="append")
    project.set_defaults(handler=handle_project_candidates)

    plan = commands.add_parser("plan", help="从已审核候选构建 digest-bound pool")
    plan.add_argument("--pool-id", required=True)
    plan.add_argument(
        "--target-scale",
        choices=("M100", "M1000", "M10000"),
        help="仅 milestone preset 使用；显式 --workload 时省略",
    )
    plan.add_argument("--source-revision", required=True)
    plan.add_argument("--source-digest", required=True)
    plan.add_argument("--entity-catalog-digest", required=True)
    plan.add_argument("--created-at", required=True)
    plan.add_argument("--candidates", required=True)
    plan.add_argument(
        "--workload",
        action="append",
        metavar="CARRIER=QUOTA",
        help="显式活动载体及其精确目标；可重复传入",
    )
    plan.set_defaults(handler=handle_plan)

    validate = commands.add_parser("validate", help="严格验证 immutable pool")
    validate.add_argument("--plan", required=True)
    validate.add_argument("--evidence-root", required=True)
    validate.set_defaults(handler=handle_validate)

    write = commands.add_parser("write", help="按 planDigest create-once 写入 canonical workspace")
    write.add_argument("--plan", required=True)
    write.add_argument("--output-root")
    write.add_argument("--evidence-root", required=True)
    write.set_defaults(handler=handle_write)


__all__ = [
    "handle_acquire_homepage_article",
    "handle_freeze_homepage_article_catalogs",
    "handle_freeze_professional_image_catalog",
    "handle_freeze_professional_video_catalog",
    "handle_merge_homepage_article",
    "handle_plan",
    "handle_prepare_handoff",
    "handle_project_candidates",
    "handle_validate",
    "handle_write",
    "register_parser",
]
