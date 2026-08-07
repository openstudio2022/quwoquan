"""CLI handlers for generic immutable content releases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.release.canonical.acceptance_lease import handle_acceptance_lease
from content.release.canonical.baseline_release import build_empty_baseline_release
from content.release.canonical.build_lookup_indexes import (
    build_publish_lookup_indexes,
)
from content.release.canonical.campaign_release import (
    CampaignReleaseError,
    CampaignReleaseRoots,
    build_campaign_release,
)
from content.release.canonical.campaign_scale_evidence import (
    CampaignScaleEvidenceError,
    write_campaign_scale_evidence,
)
from content.release.canonical.commercial_transition import (
    CommercialTransitionError,
    write_commercial_transition,
)
from content.release.canonical.discard import handle_discard
from content.release.canonical.garbage_collection import (
    apply_canonical_gc,
    plan_canonical_gc,
)
from content.release.canonical.lifecycle_exit import handle_lifecycle_exit
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.release_identity_incident import (
    record_release_identity_incident,
)
from content.release.canonical.release_identity_incident_legacy_migration import (
    migrate_legacy_release_identity_incident,
)
from content.release.canonical.release_identity_recovery import (
    write_deterministic_identity_attestation_recovery,
)
from content.release.canonical.release_operation_lock import (
    ReleaseOperationConflict,
    release_operation_guard,
    release_operation_lock_root,
)
from content.release.canonical.research_scale_promotion import (
    ResearchScalePromotionError,
    write_research_scale_promotion,
)
from content.release.canonical.reset import handle_reset_canonical
from core.io import read_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT
from core.release_layout import attestation_root
from verify.verify_release_lifecycle import release_lifecycle_issues


def handle_campaign_aggregate_release(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT).resolve()
    roots = CampaignReleaseRoots(
        output_root=output_root,
        campaigns_root=(
            output_root / "data/local/workspace/content-campaign-submissions"
        ),
        tasks_root=output_root / "data/tasks",
        publish_root=PUBLISH_ROOT,
        release_root=output_root / "data/releases",
    )
    try:
        report = build_campaign_release(
            root_execution_id=str(args.root_execution_id),
            release_id=str(args.release_id),
            roots=roots,
        )
    except (
        CampaignReleaseError,
        FileNotFoundError,
        ObjectTransactionError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release campaign-aggregate] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_release_identity_incident(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT).resolve()
    try:
        document, path = record_release_identity_incident(
            release_id=str(args.release_id),
            incident_id=str(args.incident_id),
            original_attestations=tuple(
                Path(item).expanduser() for item in args.original_attestation
            ),
            recovery_provenances=tuple(
                Path(item).expanduser() for item in args.recovery_provenance
            ),
            output_root=output_root,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release identity-incident] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**document, "incidentRef": path.relative_to(output_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_release_identity_incident_legacy_migration(
    args: argparse.Namespace,
) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT).resolve()
    try:
        document, path = migrate_legacy_release_identity_incident(
            source_incident_path=Path(args.incident).expanduser(),
            source_incident_file_sha256=str(args.incident_sha256),
            output_root=output_root,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[release identity-incident-migrate-legacy] GATE_BLOCK {exc}"
        ) from exc
    print(
        json.dumps(
            {
                **document,
                "migrationReceiptRef": path.relative_to(output_root).as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _labeled_evidence(values: list[str]) -> tuple[tuple[str, Path], ...]:
    rows: list[tuple[str, Path]] = []
    for raw in values:
        label, separator, path = str(raw).partition("=")
        if not separator or not label.strip() or not path.strip():
            raise ValueError("--evidence must use <label>=<path>")
        rows.append((label.strip(), Path(path.strip()).expanduser()))
    return tuple(rows)


def handle_release_identity_recovery(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT).resolve()
    try:
        document, path = write_deterministic_identity_attestation_recovery(
            release_id=str(args.release_id),
            recovery_id=str(args.recovery_id),
            attestation_document_path=Path(args.attestation_document).expanduser(),
            template_attestation_path=Path(args.template_attestation).expanduser(),
            target_attestation_file_sha256=str(args.target_attestation_sha256),
            writer_revision=str(args.writer_revision),
            historical_writer_sources=_labeled_evidence(list(args.writer_source)),
            recovered_recorded_at=str(args.recovered_recorded_at),
            search_start_at=str(args.search_start_at),
            search_end_at=str(args.search_end_at),
            independent_evidence=_labeled_evidence(list(args.evidence)),
            output_root=output_root,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release identity-recovery] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {
                **document,
                "recoveryProvenanceRef": path.relative_to(output_root).as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_baseline_release(args: argparse.Namespace) -> None:
    release_root = Path(args.release_root or (OUTPUT_ROOT / "data/releases"))
    release_id = str(args.release_id)
    publish_root = Path(args.publish_root or PUBLISH_ROOT)
    try:
        with (
            release_operation_guard(
                lock_root=release_operation_lock_root(release_root),
                release_ids=(release_id,),
                exclusive_releases=True,
            ),
            canonical_publish_lock(publish_root),
        ):
            report = build_empty_baseline_release(
                publish_root=publish_root,
                release_root=release_root,
                release_id=release_id,
            )
    except (
        FileNotFoundError,
        ObjectTransactionError,
        ReleaseOperationConflict,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release baseline] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_build_lookup_indexes(args: argparse.Namespace) -> None:
    release_id = str(args.release_id)
    publish_root = Path(args.publish_root or PUBLISH_ROOT)
    release_root = Path(args.release_root or (OUTPUT_ROOT / "data/releases"))
    try:
        with (
            release_operation_guard(
                lock_root=release_operation_lock_root(release_root),
                release_ids=(release_id,),
                exclusive_releases=True,
            ),
            canonical_publish_lock(publish_root),
        ):
            report = build_publish_lookup_indexes(
                release_id=release_id,
                canonical_root=publish_root,
                release_root=release_root,
                taxonomy_root=(
                    Path(args.taxonomy_root) if args.taxonomy_root else None
                ),
            )
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        ReleaseOperationConflict,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release build-lookups] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_attest_release(args: argparse.Namespace) -> None:
    release_root = Path(args.release_root or (OUTPUT_ROOT / "data/releases"))
    release_id = str(args.release_id)
    issues = release_lifecycle_issues(release_id, release_root=release_root)
    if issues:
        print(
            json.dumps(
                {"releaseId": release_id, "attested": False, "issues": issues},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)
    aggregate = read_json(attestation_root(release_root / release_id) / "release.json")
    print(
        json.dumps(
            {"releaseId": release_id, "attested": True, "attestation": aggregate},
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_research_scale_promotion(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT)
    try:
        document, path = write_research_scale_promotion(
            release_id=str(args.release_id),
            promotion_id=str(args.promotion_id),
            campaign_evidence_path=Path(args.campaign_evidence),
            release_root=Path(args.release_root or (OUTPUT_ROOT / "data/releases")),
            output_root=output_root,
        )
    except (
        FileNotFoundError,
        ObjectTransactionError,
        ResearchScalePromotionError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release research-promote-scale] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**document, "receiptRef": path.relative_to(output_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_commercial_transition(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT)
    try:
        document, path = write_commercial_transition(
            research_release_id=str(args.research_release_id),
            commercial_release_id=str(args.commercial_release_id),
            transition_run_id=str(args.run_id),
            cleanup_evidence_path=Path(args.cleanup_evidence),
            release_root=Path(args.release_root or (OUTPUT_ROOT / "data/releases")),
            output_root=output_root,
        )
    except (
        CommercialTransitionError,
        FileNotFoundError,
        ObjectTransactionError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release commercial-transition] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**document, "receiptRef": path.relative_to(output_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_gc_plan(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT)
    publish_root = Path(args.publish_root or PUBLISH_ROOT)
    release_root = Path(args.release_root or (output_root / "data/releases"))
    try:
        document, path = plan_canonical_gc(
            plan_id=str(args.plan_id),
            output_root=output_root,
            publish_root=publish_root,
            release_root=release_root,
            min_age_hours=float(args.min_age_hours),
        )
    except (FileNotFoundError, ObjectTransactionError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release gc plan] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**document, "planRef": path.relative_to(output_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_gc_apply(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT)
    publish_root = Path(args.publish_root or PUBLISH_ROOT)
    release_root = Path(args.release_root or (output_root / "data/releases"))
    try:
        document, path = apply_canonical_gc(
            plan_id=str(args.plan_id),
            plan_digest=str(args.plan_digest),
            output_root=output_root,
            publish_root=publish_root,
            release_root=release_root,
        )
    except (FileNotFoundError, ObjectTransactionError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release gc apply] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**document, "receiptRef": path.relative_to(output_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_campaign_scale_evidence(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT)
    release_root = Path(args.release_root or (output_root / "data/releases"))
    tasks_root = Path(args.tasks_root or (output_root / "data/tasks"))
    try:
        document, path = write_campaign_scale_evidence(
            evidence_id=str(args.evidence_id),
            release_id=str(args.release_id),
            campaign_plan_path=Path(args.campaign_plan),
            runtime_session_path=Path(args.runtime_session),
            calibration_preflight_receipt_path=Path(
                args.calibration_preflight_receipt
            ),
            tasks_root=tasks_root,
            release_root=release_root,
            output_root=output_root,
        )
    except (
        CampaignScaleEvidenceError,
        FileNotFoundError,
        ObjectTransactionError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release campaign-scale-evidence] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**document, "evidenceRef": path.relative_to(output_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("release", help="构建不可变的通用内容发布包")
    commands = parser.add_subparsers(dest="release_command", required=True)

    aggregate = commands.add_parser(
        "campaign-aggregate",
        help="只从 immutable campaign plan/current retry chain 聚合发布包",
    )
    aggregate.add_argument("--release-id", required=True)
    aggregate.add_argument("--root-execution-id", required=True)
    aggregate.add_argument("--output-root")
    aggregate.set_defaults(handler=handle_campaign_aggregate_release)

    identity_incident = commands.add_parser(
        "identity-incident",
        help="记录同一 releaseId 的冲突 immutable identity；不修改任何 release",
    )
    identity_incident.add_argument("--release-id", required=True)
    identity_incident.add_argument("--incident-id", required=True)
    identity_incident.add_argument(
        "--original-attestation",
        action="append",
        default=[],
        help="原始留存的 release attestation 文件；可重复",
    )
    identity_incident.add_argument(
        "--recovery-provenance",
        action="append",
        default=[],
        help="deterministic_byte_reconstruction 的 create-once provenance；可重复",
    )
    identity_incident.add_argument("--output-root")
    identity_incident.set_defaults(handler=handle_release_identity_incident)

    legacy_incident_migration = commands.add_parser(
        "identity-incident-migrate-legacy",
        help="将前 provenance 合同的原始 incident 投影为 source-bound 当前契约",
    )
    legacy_incident_migration.add_argument("--incident", required=True)
    legacy_incident_migration.add_argument(
        "--incident-sha256",
        required=True,
        help="迁移前人工核对的原始 incident 精确文件摘要",
    )
    legacy_incident_migration.add_argument("--output-root")
    legacy_incident_migration.set_defaults(
        handler=handle_release_identity_incident_legacy_migration
    )

    identity_recovery = commands.add_parser(
        "identity-recovery",
        help="按冻结 JSON 序列化合同写确定性 attestation 恢复物与 provenance",
    )
    identity_recovery.add_argument("--release-id", required=True)
    identity_recovery.add_argument("--recovery-id", required=True)
    identity_recovery.add_argument("--attestation-document", required=True)
    identity_recovery.add_argument("--template-attestation", required=True)
    identity_recovery.add_argument("--target-attestation-sha256", required=True)
    identity_recovery.add_argument("--writer-revision", required=True)
    identity_recovery.add_argument(
        "--writer-source",
        action="append",
        required=True,
        help="历史 writer 闭集，格式 <logicalRef>=<snapshotPath>；必须四项",
    )
    identity_recovery.add_argument("--recovered-recorded-at", required=True)
    identity_recovery.add_argument("--search-start-at", required=True)
    identity_recovery.add_argument("--search-end-at", required=True)
    identity_recovery.add_argument(
        "--evidence",
        action="append",
        required=True,
        help=(
            "独立证据，格式 <role>=<path>；必须各提供 "
            "release_identity 与 execution_closure"
        ),
    )
    identity_recovery.add_argument("--output-root")
    identity_recovery.set_defaults(handler=handle_release_identity_recovery)

    baseline = commands.add_parser(
        "baseline", help="创建仅用于 full-sync rollback 的空 desired-state 发布包"
    )
    baseline.add_argument("--release-id", required=True)
    baseline.add_argument("--publish-root")
    baseline.add_argument("--release-root")
    baseline.set_defaults(handler=handle_baseline_release)

    build_lookups = commands.add_parser(
        "build-lookups",
        help="为 immutable release 生成 create-once first-consumer lookup indexes",
    )
    build_lookups.add_argument("--release-id", required=True)
    build_lookups.add_argument("--publish-root")
    build_lookups.add_argument("--release-root")
    build_lookups.add_argument("--taxonomy-root")
    build_lookups.set_defaults(handler=handle_build_lookup_indexes)

    discard = commands.add_parser(
        "discard", help="删除无活跃写入的可重跑 release 输出及其环境证据"
    )
    discard.add_argument("--release-id", required=True)
    discard.set_defaults(handler=handle_discard)

    lifecycle_exit = commands.add_parser(
        "lifecycle-exit",
        help="从既有 original/rollback/replay run 写入 create-once Exit receipt",
    )
    lifecycle_exit.add_argument(
        "--env", required=True, choices=("alpha", "beta", "gamma", "prod")
    )
    lifecycle_exit.add_argument("--original-release-id", required=True)
    lifecycle_exit.add_argument("--original-import-run-id", required=True)
    lifecycle_exit.add_argument("--original-verify-run-id", required=True)
    lifecycle_exit.add_argument("--rollback-to-release-id", required=True)
    lifecycle_exit.add_argument("--rollback-run-id", required=True)
    lifecycle_exit.add_argument("--rollback-verify-run-id", required=True)
    lifecycle_exit.add_argument("--replay-import-run-id", required=True)
    lifecycle_exit.add_argument("--replay-verify-run-id", required=True)
    lifecycle_exit.add_argument(
        "--run-id", required=True, help="append-only Exit run id"
    )
    lifecycle_exit.set_defaults(handler=handle_lifecycle_exit)

    acceptance_lease = commands.add_parser(
        "acceptance-lease",
        help="为真实 UAT 写入 append-only acquire/revoke lease event",
    )
    lease_actions = acceptance_lease.add_subparsers(
        dest="acceptance_lease_action",
        required=True,
    )
    acquire = lease_actions.add_parser("acquire")
    acquire.add_argument(
        "--env", required=True, choices=("alpha", "beta", "gamma", "prod")
    )
    acquire.add_argument("--release-id", required=True)
    acquire.add_argument("--import-run-id", required=True)
    acquire.add_argument("--verify-run-id", required=True)
    acquire.add_argument("--lease-id", required=True)
    acquire.add_argument("--event-id", default="")
    acquire.set_defaults(handler=handle_acceptance_lease)
    revoke = lease_actions.add_parser("revoke")
    revoke.add_argument(
        "--env", required=True, choices=("alpha", "beta", "gamma", "prod")
    )
    revoke.add_argument("--release-id", required=True)
    revoke.add_argument("--lease-id", required=True)
    revoke.add_argument("--acquire-event-ref", required=True)
    revoke.add_argument("--event-id", default="")
    revoke.set_defaults(handler=handle_acceptance_lease)

    reset_canonical = commands.add_parser(
        "reset-canonical",
        help="在空基线 full-sync 回执后清空 canonical publish 输出",
    )
    reset_canonical.add_argument("--empty-baseline-release", required=True)
    reset_canonical.add_argument(
        "--env", required=True, help="已应用空基线的目标环境，逗号分隔"
    )
    reset_canonical.set_defaults(handler=handle_reset_canonical)

    attest = commands.add_parser(
        "attest", help="校验 immutable release 的唯一 aggregate attestation"
    )
    attest.add_argument("--release-id", required=True)
    attest.add_argument("--release-root")
    attest.set_defaults(handler=handle_attest_release)

    research_promote = commands.add_parser(
        "research-promote-scale",
        help="由四载体 M100 与资源隔离/恢复证据写入 create-once promotion receipt",
    )
    research_promote.add_argument("--release-id", required=True)
    research_promote.add_argument("--promotion-id", required=True)
    research_promote.add_argument("--campaign-evidence", required=True)
    research_promote.add_argument("--release-root")
    research_promote.add_argument("--output-root")
    research_promote.set_defaults(handler=handle_research_scale_promotion)

    commercial_transition = commands.add_parser(
        "commercial-transition",
        help="从 research/commercial release 与四环境清理回读写逐资产迁移 receipt",
    )
    commercial_transition.add_argument("--research-release-id", required=True)
    commercial_transition.add_argument("--commercial-release-id", required=True)
    commercial_transition.add_argument("--run-id", required=True)
    commercial_transition.add_argument("--cleanup-evidence", required=True)
    commercial_transition.add_argument("--release-root")
    commercial_transition.add_argument("--output-root")
    commercial_transition.set_defaults(handler=handle_commercial_transition)

    gc = commands.add_parser(
        "gc",
        help="按 execution/retry/release/publish 可达性审计并回收派生输出",
    )
    gc_actions = gc.add_subparsers(dest="release_gc_action", required=True)
    gc_plan = gc_actions.add_parser("plan", help="只写 create-once GC 计划，不删除输出")
    gc_plan.add_argument("--plan-id", required=True)
    gc_plan.add_argument("--min-age-hours", type=float, default=168.0)
    gc_plan.add_argument("--output-root")
    gc_plan.add_argument("--publish-root")
    gc_plan.add_argument("--release-root")
    gc_plan.set_defaults(handler=handle_gc_plan)
    gc_apply = gc_actions.add_parser("apply", help="复核可达性并应用指定 plan digest")
    gc_apply.add_argument("--plan-id", required=True)
    gc_apply.add_argument("--plan-digest", required=True)
    gc_apply.add_argument("--output-root")
    gc_apply.add_argument("--publish-root")
    gc_apply.add_argument("--release-root")
    gc_apply.set_defaults(handler=handle_gc_apply)

    scale_evidence = commands.add_parser(
        "campaign-scale-evidence",
        help="从四 lane canonical 真相源派生 research M100 scale evidence",
    )
    scale_evidence.add_argument("--evidence-id", required=True)
    scale_evidence.add_argument("--release-id", required=True)
    scale_evidence.add_argument("--campaign-plan", required=True)
    scale_evidence.add_argument("--runtime-session", required=True)
    scale_evidence.add_argument(
        "--calibration-preflight-receipt",
        required=True,
        help="fresh sol_calibration preflight+soak receipt",
    )
    scale_evidence.add_argument("--tasks-root")
    scale_evidence.add_argument("--release-root")
    scale_evidence.add_argument("--output-root")
    scale_evidence.set_defaults(handler=handle_campaign_scale_evidence)
