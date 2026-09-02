"""CLI adapter for current-identity pre-acquisition handoff freezing."""
from __future__ import annotations

import argparse
from pathlib import Path

from core import paths
from core.source_digest import (
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)
from content.execution.workspace import entity_catalog_digest
from content.source.pre_acquisition_handoff import write_pre_acquisition_handoff
from content.source.research.handler_cli_io import print_document, typed_error


def source_selection(values: list[str]) -> dict[str, dict[str, object]]:
    selections: dict[str, dict[str, object]] = {}
    for raw in values:
        carrier, separator, declaration = str(raw).partition("=")
        mode, mode_separator, providers_text = declaration.partition(":")
        providers = [value.strip() for value in providers_text.split(",") if value.strip()]
        if (
            not separator
            or not mode_separator
            or carrier in selections
            or not carrier.strip()
            or not mode.strip()
            or not providers
        ):
            raise ValueError(
                "--source-selection must be unique CARRIER=MODE:PROVIDER[,PROVIDER...] values"
            )
        selections[carrier.strip()] = {"mode": mode.strip(), "providers": providers}
    return selections


def handle_prepare_handoff(
    args: argparse.Namespace, *, workload_targets: dict[str, int]
) -> None:
    try:
        repo_root = paths.REPO_ROOT.resolve()
        vertical = str(args.vertical).strip().lower()
        region_ref = str(args.region_ref or "").strip() or None
        entity_root = repo_root / "quwoquan_data" / "reference" / vertical / "entities"
        discovery = entity_root / region_ref if region_ref else entity_root
        if not discovery.is_dir():
            raise ValueError(f"entity reference does not exist: {discovery}")
        source = current_source_definition_snapshot(repo_root=repo_root).to_document()
        execution_bundle = current_execution_bundle_identity(
            repo_root=repo_root
        ).to_document()
        handoff, destination = write_pre_acquisition_handoff(
            handoff_id=args.handoff_id,
            handoff_revision=args.handoff_revision,
            supersedes_handoff=(
                Path(args.supersedes_handoff_ref).expanduser().resolve()
                if args.supersedes_handoff_ref
                else None
            ),
            scale=f"M{max(workload_targets.values())}",
            vertical=vertical,
            lifecycle=args.lifecycle,
            scope_type=args.scope_type,
            region_ref=region_ref,
            primary_topic_ref=args.primary_topic_ref,
            related_topic_refs=args.related_topic_ref,
            source_selection=source_selection(args.source_selection),
            run_date=args.run_date,
            campaign_sequence=args.sequence,
            campaign_retry_of=args.retry_of,
            source_digest=source,
            execution_bundle=execution_bundle,
            entity_catalog_digest=entity_catalog_digest(
                discovery.relative_to(repo_root).as_posix()
            ),
            workload_targets=workload_targets,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[source-pool prepare-handoff] GATE_BLOCK {typed_error(exc)}"
        ) from exc
    print_document(
        {
            "schema": "quwoquan_data.pre_acquisition_handoff_prepare_result",
            "handoffRef": destination.relative_to(paths.OUTPUT_ROOT).as_posix(),
            "handoffDigest": handoff["handoffDigest"],
            "sourceRevision": handoff["sourceRevision"],
            "sourceDigest": handoff["sourceDigest"]["digest"],
            "executionBundleDigest": handoff["executionBundle"]["digest"],
            "entityCatalogDigest": handoff["entityCatalogDigest"],
            "activeCarriers": handoff["activeCarriers"],
            "workloadTargets": handoff["workloadTargets"],
        }
    )


__all__ = ["handle_prepare_handoff", "source_selection"]
