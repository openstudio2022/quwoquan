"""Canonical CLI writer for one immutable active-workload envelope set."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.source_digest import current_source_digest

from content.execution.campaign.lane import (
    CAMPAIGN_CARRIERS,
    normalize_active_carriers,
)
from content.execution.campaign.prepare_input import (
    parse_requested_workloads as _requested_workloads,
    parse_source_selection as _parsed_source_selection,
)
from content.execution.campaign.request_envelope import (
    write_scale_envelopes,
)
from content.execution.campaign.scale import (
    campaign_workload_targets,
    resolve_campaign_scale,
)
from content.execution.controller.execute.pre_acquisition_handoff import (
    write_pre_acquisition_handoff,
)
from content.execution.model_contract import (
    CURSOR_GROK_SEMANTIC_SELECTION_ID,
    SEMANTIC_SELECTION_IDS,
)
from content.execution.workspace import entity_catalog_digest


def _declarations(
    rows: Iterable[Iterable[str]] | None,
    *,
    kind: str,
    acquisition_root_ref: str,
) -> list[dict[str, str]]:
    declarations: list[dict[str, str]] = []
    for row in rows or ():
        values = tuple(str(value or "").strip() for value in row)
        if len(values) != 2 or not all(values):
            raise ValueError(
                "external input requires one manifestRef and one receiptRef"
            )
        declarations.append(
            {
                "kind": kind,
                "acquisitionRootRef": acquisition_root_ref,
                "manifestRef": values[0],
                "receiptRef": values[1],
            }
        )
    return declarations


def _retry_predecessors(args: argparse.Namespace) -> dict[str, str]:
    rows = {
        carrier: str(getattr(args, f"{carrier}_retry_of", "") or "").strip()
        for carrier in CAMPAIGN_CARRIERS
    }
    return {carrier: value for carrier, value in rows.items() if value}


def _resolved_scale(args: argparse.Namespace, workloads: dict[str, int] | None) -> str:
    return resolve_campaign_scale(
        scale=(str(args.scale).strip() if str(args.scale or "").strip() else None),
        quota=(max(workloads.values()) if workloads and not args.scale else None),
    ).scale


def _summary(paths: dict[str, Path]) -> dict[str, Any]:
    envelopes = {carrier: read_json(path) for carrier, path in paths.items()}
    first = next(iter(envelopes.values()))
    active = tuple(first["activeCarriers"])
    root_execution_id = str(first["rootExecutionId"])

    def submit_command(carrier: str) -> list[str]:
        envelope = envelopes[carrier]
        command = [
            "python3",
            "quwoquan_data/scripts/cli.py",
            "task",
            "execute",
            "--execution-id",
            str(envelope["executionId"]),
            "--campaign-root-execution-id",
            root_execution_id,
            "--family",
            str(envelope["familyRef"]),
            "--region-ref",
            str(envelope["regionRef"]),
            "--selector",
            str(envelope["selector"]),
            "--quota",
            str(envelope["quota"]),
            "--count",
            str(envelope["count"]),
            *(
                [
                    "--capacity-calibration-receipt",
                    str(
                        envelope["executionAuthority"]["calibration"][
                            "calibrationReceiptRef"
                        ]
                    ),
                ]
                if envelope["executionAuthority"]["mode"]
                == "governed_calibration"
                else []
            ),
            "--semantic-selection-id",
            str(envelope["semanticSelectionId"]),
            "--semantic-preflight-receipt",
            str(envelope["semanticPreflightReceipt"]["receiptRef"]),
            "--campaign-envelope",
            paths[carrier].resolve().as_posix(),
            "--stage",
            "submit-only",
        ]
        host_binding = envelope.get("workerHostSetBinding")
        if isinstance(host_binding, dict):
            command.extend(
                [
                    "--worker-host-set-binding-json",
                    json.dumps(host_binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                ]
            )
        if envelope.get("retryOf"):
            command.extend(["--retry-of", str(envelope["retryOf"])])
        if envelope.get("topic"):
            command.extend(["--topic", str(envelope["topic"])])
        for provider in envelope.get("sourceProviders") or []:
            command.extend(["--source-provider", str(provider)])
        for target in envelope.get("targetNames") or []:
            command.extend(["--target", str(target)])
        pool = envelope.get("scaleSourcePool")
        selection = envelope.get("sourcePoolSelection")
        if isinstance(pool, dict) and isinstance(selection, dict):
            command.extend(
                [
                    "--scale-source-pool-id", str(pool["poolId"]),
                    "--scale-source-pool-target-scale", str(pool["targetScale"]),
                    "--scale-source-pool-plan-ref", str(pool["planRef"]),
                    "--scale-source-pool-plan-digest", str(pool["planDigest"]),
                    "--scale-source-pool-plan-file-sha256", str(pool["planFileSha256"]),
                    "--source-pool-source-revision", str(pool["sourceRevision"]),
                    "--source-pool-source-digest", str(pool["sourceDigest"]),
                    "--source-pool-entity-catalog-digest", str(pool["entityCatalogDigest"]),
                    "--source-pool-evidence-root-ref", str(envelope["sourcePoolEvidenceRootRef"]),
                    "--source-pool-carrier", str(selection["carrier"]),
                    "--source-pool-selection-digest", str(selection["selectionDigest"]),
                ]
            )
            for candidate_id in selection["candidateIds"]:
                command.extend(["--source-pool-candidate-id", str(candidate_id)])
        return command

    def coordination_command(stage: str) -> list[str]:
        return [
            "python3",
            "quwoquan_data/scripts/cli.py",
            "task",
            "execute",
            "--execution-id",
            root_execution_id,
            "--campaign-root-execution-id",
            root_execution_id,
            "--stage",
            stage,
        ]

    return {
        "schema": "quwoquan_data.campaign_envelope_prepare_result",
        "scale": first["scale"],
        "workloadMode": first["workloadMode"],
        "activeCarriers": list(active),
        "workloads": dict(first["workloads"]),
        "rootExecutionId": root_execution_id,
        "sourceRevision": first["sourceRevision"],
        "sourceDigest": first["sourceDigest"]["digest"],
        "entityCatalogDigest": first["entityCatalogDigest"],
        "preAcquisitionHandoff": first["preAcquisitionHandoff"],
        "semanticSelectionId": first["semanticSelectionId"],
        "semanticPreflightReceipt": first["semanticPreflightReceipt"],
        "articleExternalInputMode": "execution_source_unit_freeze",
        "envelopes": {
            carrier: {
                "executionId": envelopes[carrier]["executionId"],
                "retryOf": envelopes[carrier]["retryOf"],
                "requestDigest": envelopes[carrier]["requestDigest"],
                "path": path.resolve().as_posix(),
                "submitCommand": submit_command(carrier),
                "laneRunCommand": [
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "task",
                    "execute",
                    "--execution-id",
                    str(envelopes[carrier]["executionId"]),
                    "--campaign-root-execution-id",
                    root_execution_id,
                    "--stage",
                    "campaign-lane-run",
                ],
            }
            for carrier, path in paths.items()
        },
        "coordination": {
            "freezeAfterAllSubmissions": coordination_command("campaign-freeze"),
            "finalizeAfterAllLaneRuns": coordination_command("campaign-finalize"),
        },
    }


def _missing(args: argparse.Namespace, *names: str) -> list[str]:
    return [
        name
        for name in names
        if not getattr(args, name, None)
    ]


def _require_phase_args(args: argparse.Namespace) -> None:
    phase = str(args.phase)
    workloads = _requested_workloads(args)
    if not str(args.scale or "").strip() and workloads is None:
        raise ValueError("prepare-campaign requires --scale or at least one --workload")
    scale = _resolved_scale(args, workloads)
    active = normalize_active_carriers(
        workloads.keys() if workloads is not None else CAMPAIGN_CARRIERS
    )
    if phase == "handoff":
        missing = _missing(
            args,
            "handoff_id",
            "handoff_revision",
            "vertical",
            "lifecycle",
            "scope_type",
            "source_selection_rows",
        )
        envelope_only = [
            name
            for name in (
                "handoff_ref",
                "semantic_preflight_receipt",
                "capacity_calibration_receipt",
                "homepage_image_input",
                "image_input",
                "video_input",
                "predecessor_reconciliation_receipt",
                "promotion_receipt",
                "scale_source_pool",
                "source_pool_evidence_root",
            )
            if getattr(args, name, None)
        ]
        retry_fields = [
            f"{carrier}_retry_of"
            for carrier in CAMPAIGN_CARRIERS
            if getattr(args, f"{carrier}_retry_of", None)
        ]
        flag_names = {"source_selection_rows": "source-selection"}
        if missing:
            raise ValueError(
                "handoff phase requires: "
                + ", ".join(
                    "--" + flag_names.get(name, name.replace("_", "-"))
                    for name in missing
                )
            )
        if envelope_only or retry_fields:
            raise ValueError(
                "handoff phase forbids envelope/execution arguments: "
                + ", ".join(
                    f"--{name.replace('_', '-')}"
                    for name in (*envelope_only, *retry_fields)
                )
            )
        return
    # capacity_calibration_receipt 是否必需由 envelope builder 的互斥
    # executionAuthority 判定裁决：bounded 小批禁止携带，governed 缺失即
    # CALIBRATION_REQUIRED。CLI 只透传，不复制判定。
    required_inputs = [
        "handoff_ref",
        "semantic_preflight_receipt",
    ]
    if "homepage" in active:
        required_inputs.append("homepage_image_input")
    if "image" in active:
        required_inputs.append("image_input")
    if "video" in active:
        required_inputs.append("video_input")
    missing = _missing(args, *required_inputs)
    handoff_only = [
        name
        for name in (
            "handoff_id",
            "handoff_revision",
            "supersedes_handoff_ref",
            "campaign_retry_of",
            "vertical",
            "lifecycle",
            "scope_type",
            "region_ref",
            "primary_topic_ref",
            "related_topic_refs",
            "source_selection_rows",
        )
        if getattr(args, name, None)
    ]
    if missing:
        raise ValueError(
            "envelopes phase requires: "
            + ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        )
    if handoff_only:
        raise ValueError(
            "envelopes phase forbids handoff creation arguments: "
            + ", ".join(f"--{name.replace('_', '-')}" for name in handoff_only)
        )
    pool_values = (
        getattr(args, "scale_source_pool", None),
        getattr(args, "source_pool_evidence_root", None),
    )
    if any(pool_values) and not all(pool_values):
        raise ValueError(
            "--scale-source-pool and --source-pool-evidence-root must be provided together"
        )
def _workload_targets(scale: str) -> dict[str, int]:
    return campaign_workload_targets(scale)


def _handle_handoff(args: argparse.Namespace) -> None:
    repo_root = paths.REPO_ROOT.resolve()
    vertical = str(args.vertical or "").strip().lower()
    if not vertical:
        raise ValueError(
            "handoff phase requires an explicit --vertical; silent defaults are forbidden"
        )
    region_ref = str(args.region_ref or "").strip() or None
    entity_root = repo_root / "quwoquan_data" / "reference" / vertical / "entities"
    discovery = entity_root / region_ref if region_ref else entity_root
    if not discovery.is_dir():
        raise ValueError(f"entity reference does not exist: {discovery}")
    from core.source_digest import (
        current_execution_bundle_identity,
        current_source_definition_snapshot,
    )

    source = current_source_definition_snapshot(repo_root=repo_root).to_document()
    execution_bundle = current_execution_bundle_identity(
        repo_root=repo_root
    ).to_document()
    requested_workloads = _requested_workloads(args)
    scale = _resolved_scale(args, requested_workloads)
    handoff, handoff_path = write_pre_acquisition_handoff(
        handoff_id=str(args.handoff_id),
        handoff_revision=int(args.handoff_revision),
        supersedes_handoff=(
            Path(str(args.supersedes_handoff_ref)).expanduser().resolve()
            if str(args.supersedes_handoff_ref or "").strip()
            else None
        ),
        scale=scale,
        vertical=vertical,
        lifecycle=str(args.lifecycle),
        scope_type=str(args.scope_type),
        region_ref=region_ref,
        primary_topic_ref=(
            str(args.primary_topic_ref).strip()
            if str(args.primary_topic_ref or "").strip()
            else None
        ),
        related_topic_refs=tuple(args.related_topic_refs or ()),
        source_selection=_parsed_source_selection(args),
        run_date=str(args.run_date),
        campaign_sequence=int(args.sequence),
        campaign_retry_of=(
            str(args.campaign_retry_of).strip()
            if str(args.campaign_retry_of or "").strip()
            else None
        ),
        source_digest=source,
        execution_bundle=execution_bundle,
        entity_catalog_digest=entity_catalog_digest(
            discovery.relative_to(repo_root).as_posix()
        ),
        workload_targets=(requested_workloads or _workload_targets(scale)),
    )
    print(
        json.dumps(
            {
                "schema": "quwoquan_data.pre_acquisition_handoff_prepare_result",
                "handoff": handoff,
                "handoffPath": handoff_path.as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _handle_envelopes(args: argparse.Namespace) -> None:
    preflight = Path(str(args.semantic_preflight_receipt)).expanduser().resolve()
    external_inputs = {
        "homepage": _declarations(
            args.homepage_image_input,
            kind="professional_image_acquisition",
            acquisition_root_ref=".",
        ),
        "article": [],
        "image": _declarations(
            args.image_input,
            kind="professional_image_acquisition",
            acquisition_root_ref=".",
        ),
        "video": _declarations(
            args.video_input,
            kind="professional_video_acquisition",
            acquisition_root_ref="video",
        ),
    }
    requested_workloads = _requested_workloads(args)
    paths = write_scale_envelopes(
        _resolved_scale(args, requested_workloads),
        workloads=requested_workloads,
        target_names=tuple(args.target_names or ()),
        source_providers=tuple(args.source_providers or ()),
        day=str(args.run_date),
        sequence=int(args.sequence),
        semantic_selection_id=str(args.semantic_selection_id),
        semantic_preflight_receipt=preflight,
        capacity_calibration_receipt=(
            Path(str(args.capacity_calibration_receipt)).expanduser()
            if str(getattr(args, "capacity_calibration_receipt", "") or "").strip()
            else None
        ),
        predecessor_execution_ids_by_carrier=_retry_predecessors(args),
        predecessor_reconciliation_receipt=(
            Path(str(args.predecessor_reconciliation_receipt))
            .expanduser()
            .resolve()
            if str(args.predecessor_reconciliation_receipt or "").strip()
            else None
        ),
        promotion_receipt=(
            Path(str(args.promotion_receipt)).expanduser().resolve()
            if str(args.promotion_receipt or "").strip()
            else None
        ),
        pre_acquisition_handoff=Path(str(args.handoff_ref))
        .expanduser()
        .resolve(),
        external_input_refs_by_carrier=external_inputs,
        scale_source_pool=(
            Path(str(getattr(args, "scale_source_pool", ""))).expanduser().resolve()
            if str(getattr(args, "scale_source_pool", "") or "").strip()
            else None
        ),
        source_pool_evidence_root=(
            Path(str(getattr(args, "source_pool_evidence_root", ""))).expanduser().resolve()
            if str(getattr(args, "source_pool_evidence_root", "") or "").strip()
            else None
        ),
    )
    print(json.dumps(_summary(paths), ensure_ascii=False, indent=2))


def handle_prepare_campaign(args: argparse.Namespace) -> None:
    try:
        _require_phase_args(args)
        if str(args.phase) == "handoff":
            _handle_handoff(args)
        else:
            _handle_envelopes(args)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task prepare-campaign] GATE_BLOCK {exc}") from exc


def register_prepare_campaign_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "prepare-campaign",
        help=(
            "先冻结 create-once pre-acquisition handoff revision，再由显式 "
            "handoff/acquisition/preflight 生成 active workload envelopes"
        ),
    )
    parser.add_argument("--phase", choices=("handoff", "envelopes"), required=True)
    parser.add_argument("--scale")
    parser.add_argument(
        "--workload",
        dest="workload_rows",
        action="append",
        default=[],
        metavar="CARRIER=QUOTA",
        help="显式 active workload；可重复，未提供时 --scale 作为四载体 preset",
    )
    parser.add_argument(
        "--vertical",
        help="handoff 阶段必填的显式垂类；禁止任何静默默认",
    )
    parser.add_argument("--lifecycle", choices=("research", "commercial"))
    parser.add_argument(
        "--scope-type",
        choices=("vertical", "region", "topic", "region_topic"),
    )
    parser.add_argument("--region-ref")
    parser.add_argument("--run-date", required=True, help="YYYYMMDD；retry 保持前序日期")
    parser.add_argument("--sequence", required=True, type=int)
    parser.add_argument("--primary-topic-ref", help="canonical Topic/** 引用")
    parser.add_argument(
        "--related-topic-ref",
        dest="related_topic_refs",
        action="append",
        default=[],
        help="canonical Topic/** 引用；可重复，不含 primary",
    )
    parser.add_argument(
        "--source-selection",
        dest="source_selection_rows",
        action="append",
        default=[],
        metavar="CARRIER=MODE:PROVIDER[,PROVIDER...]",
        help="按载体来源策略；MODE 为 site_primary 或 search_supplement",
    )
    parser.add_argument(
        "--target", dest="target_names", action="append", default=[]
    )
    parser.add_argument(
        "--source-provider", dest="source_providers", action="append", default=[]
    )
    parser.add_argument(
        "--semantic-selection-id",
        choices=SEMANTIC_SELECTION_IDS,
        default=CURSOR_GROK_SEMANTIC_SELECTION_ID,
    )
    parser.add_argument("--handoff-id")
    parser.add_argument("--handoff-revision", type=int)
    parser.add_argument("--supersedes-handoff-ref")
    parser.add_argument("--campaign-retry-of")
    parser.add_argument("--handoff-ref")
    parser.add_argument("--semantic-preflight-receipt")
    parser.add_argument("--capacity-calibration-receipt")
    parser.add_argument("--predecessor-reconciliation-receipt")
    parser.add_argument("--promotion-receipt")
    parser.add_argument("--scale-source-pool")
    parser.add_argument("--source-pool-evidence-root")
    for carrier in CAMPAIGN_CARRIERS:
        parser.add_argument(f"--{carrier}-retry-of")
    parser.add_argument(
        "--homepage-image-input",
        nargs=2,
        action="append",
        metavar=("MANIFEST_REF", "RECEIPT_REF"),
    )
    parser.add_argument(
        "--image-input",
        nargs=2,
        action="append",
        metavar=("MANIFEST_REF", "RECEIPT_REF"),
    )
    parser.add_argument(
        "--video-input",
        nargs=2,
        action="append",
        metavar=("MANIFEST_REF", "RECEIPT_REF"),
    )
    parser.set_defaults(handler=handle_prepare_campaign)


__all__ = ["handle_prepare_campaign", "register_prepare_campaign_parser"]
