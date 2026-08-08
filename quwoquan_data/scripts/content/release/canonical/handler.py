"""CLI handlers for generic immutable content releases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.release.canonical.acceptance_lease import (
    handle_acceptance_lease,  # noqa: F401
)
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
from content.release.canonical.discard import handle_discard  # noqa: F401
from content.release.canonical.garbage_collection import (
    apply_canonical_gc,
    plan_canonical_gc,
)
from content.release.canonical.lifecycle_exit import (
    handle_lifecycle_exit,  # noqa: F401
)
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.publish_intermediate_cleanup import (
    apply_publish_intermediate_cleanup,
    plan_publish_intermediate_cleanup,
)
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
from content.release.canonical.reset import handle_reset_canonical  # noqa: F401
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
            target_scale=str(args.target_scale),
            predecessor_promotion_path=(
                Path(args.predecessor_promotion)
                if args.predecessor_promotion
                else None
            ),
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


def handle_publish_intermediate_cleanup_plan(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT).resolve()
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    try:
        document, path = plan_publish_intermediate_cleanup(
            cleanup_id=str(args.cleanup_id),
            publish_root=publish_root,
            output_root=output_root,
        )
    except (FileNotFoundError, ObjectTransactionError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[release publish-intermediate-cleanup plan] GATE_BLOCK {exc}"
        ) from exc
    print(
        json.dumps(
            {**document, "planRef": path.relative_to(output_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_publish_intermediate_cleanup_apply(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or OUTPUT_ROOT).resolve()
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    try:
        document, path = apply_publish_intermediate_cleanup(
            cleanup_id=str(args.cleanup_id),
            plan_digest=str(args.plan_digest),
            publish_root=publish_root,
            output_root=output_root,
        )
    except (FileNotFoundError, ObjectTransactionError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[release publish-intermediate-cleanup apply] GATE_BLOCK {exc}"
        ) from exc
    print(
        json.dumps(
            {**document, "receiptRef": path.relative_to(output_root).as_posix()},
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
            target_scale=str(args.target_scale),
            predecessor_promotion_path=(
                Path(args.predecessor_promotion)
                if args.predecessor_promotion
                else None
            ),
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

from content.release.canonical.handler_cli import register_parser  # noqa: F401
