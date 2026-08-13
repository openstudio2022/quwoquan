"""CLI main：派生映射、迁移清单与现状基线并落盘。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from quwoquan_ops.cli.lib.output_paths import repo_runs_root

from .claims import check_cloud_layer_rule_mirror
from .constants import (
    APP_APPEND_PORT_NAMING,
    APP_CROSS_CUTTING_ROOTS,
    APP_LAYERS,
    APP_OPERATION_REQUIREMENT_SOURCE,
    APP_PROCESS_PORT_NAMING,
    APP_SESSION_PORT_NAMING,
    APP_TO_CLOUD_LAYER_EQUIVALENCE,
    CLIENT_INVARIANT_REQUIREMENT_SOURCE,
    CLOUD_LAYERS,
    CONTRACT_GRAPH_PATH,
    FORBIDDEN_APP_LAYERS_BY_KIND,
    OUTPUT_DIR_NAME,
    PAGE_OBJECT_CONTRACT_PATH,
    PRESENTATION_REQUIREMENT_SOURCE,
    APP_CLIENT_INVARIANT_REQUIRED_LAYERS,
    APP_OPERATION_REQUIRED_LAYERS,
    APP_PAGE_OWNER_REQUIRED_LAYERS,
    REQUIRED_CLOUD_LAYERS_BY_KIND,
    ROOT,
    RULE_ID,
)
from .render import build_context_diff, render_baseline_report, render_manifest
from .roster import ObjectRoster
from .scan import load_page_claims, scan_app, scan_cloud
from .views import build_baseline, build_object_view


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _json_dump(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="派生 business object → 端云物理文件映射、迁移清单与现状基线"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="覆盖输出目录（默认 .qwq_output/env/repo/runs/object-path-map）",
    )
    arguments = parser.parse_args(argv)

    drift = check_cloud_layer_rule_mirror()
    if drift:
        print("[object-path-map] FAIL")
        for issue in drift:
            print(f"  - {issue}")
        return 1

    graph_path = ROOT / CONTRACT_GRAPH_PATH
    graph_bytes = graph_path.read_bytes()
    graph = json.loads(graph_bytes)
    roster = ObjectRoster(graph)

    page_claims, pages = load_page_claims()
    cloud_rows, cloud_findings, cloud_support_paths = scan_cloud(roster)
    app_rows, app_findings = scan_app(roster, page_claims)
    findings = sorted(
        cloud_findings + app_findings,
        key=lambda item: (item["kind"], item["path"]),
    )
    object_view = build_object_view(
        roster,
        cloud_rows,
        app_rows,
        page_claims,
        pages,
    )
    context_diff = build_context_diff(roster)
    baseline = build_baseline(roster, cloud_rows, app_rows, pages, object_view)
    baseline["cloudTestSupportFileTotal"] = len(cloud_support_paths)

    output_dir = (
        Path(arguments.output_dir)
        if arguments.output_dir
        else repo_runs_root() / OUTPUT_DIR_NAME
    )
    mapping_payload = {
        "ruleId": RULE_ID,
        "inputs": {
            "contractGraph": {
                "path": CONTRACT_GRAPH_PATH.as_posix(),
                "sha256": hashlib.sha256(graph_bytes).hexdigest(),
            },
            "pageObjectContract": PAGE_OBJECT_CONTRACT_PATH.as_posix(),
            "appOperationRequirementSource": APP_OPERATION_REQUIREMENT_SOURCE,
            "presentationRequirementSource": PRESENTATION_REQUIREMENT_SOURCE,
            "clientInvariantRequirementSource": CLIENT_INVARIANT_REQUIREMENT_SOURCE,
        },
        "layerRules": {
            "cloudLayers": list(CLOUD_LAYERS),
            "appLayers": list(APP_LAYERS),
            "appToCloudLayerEquivalence": APP_TO_CLOUD_LAYER_EQUIVALENCE,
            "requiredCloudLayersByKind": {
                kind: list(layers)
                for kind, layers in sorted(REQUIRED_CLOUD_LAYERS_BY_KIND.items())
            },
            "requiredAppLayersByCapability": {
                "clientContractOperation": list(APP_OPERATION_REQUIRED_LAYERS),
                "pagePhysicalOwner": list(APP_PAGE_OWNER_REQUIRED_LAYERS),
                "clientInvariant": list(APP_CLIENT_INVARIANT_REQUIRED_LAYERS),
            },
            "forbiddenAppLayersByKind": {
                kind: list(layers)
                for kind, layers in sorted(FORBIDDEN_APP_LAYERS_BY_KIND.items())
            },
            "appProcessPortNaming": dict(sorted(APP_PROCESS_PORT_NAMING.items())),
            "appAppendPortNaming": dict(sorted(APP_APPEND_PORT_NAMING.items())),
            "appSessionPortNaming": {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in sorted(APP_SESSION_PORT_NAMING.items())
            },
            "appCrossCuttingRoots": APP_CROSS_CUTTING_ROOTS,
        },
        "boundedContextDiff": context_diff,
        "objects": {
            object_id: object_view[object_id] for object_id in sorted(object_view)
        },
    }
    _write(output_dir / "object_path_map.json", _json_dump(mapping_payload))
    _write(
        output_dir / "migration_manifest.tsv",
        render_manifest([*cloud_rows, *app_rows]),
    )
    _write(
        output_dir / "derivation_findings.json",
        _json_dump({"ruleId": RULE_ID, "findings": findings}),
    )
    _write(
        output_dir / "baseline_report.md",
        render_baseline_report(roster, baseline, object_view, context_diff),
    )
    _write(
        output_dir / "baseline_summary.json",
        _json_dump({"ruleId": RULE_ID, "baseline": baseline}),
    )

    try:
        printable_output_dir = output_dir.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        printable_output_dir = output_dir.as_posix()
    print("[object-path-map] OK")
    print(
        _json_dump(
            {
                "ruleId": RULE_ID,
                "outputDir": printable_output_dir,
                "domains": len(roster.domains),
                "boundedContexts": len(roster.context_ids),
                "objects": len(roster.objects),
                "cloudFiles": len(cloud_rows),
                "appFiles": len(app_rows),
                "findings": len(findings),
                "appUnownedFileTotal": baseline["appUnownedFileTotal"],
                "appCrossCuttingFileTotal": baseline["appCrossCuttingFileTotal"],
                "objectsMissingRequiredAppLayers": len(
                    baseline["objectsMissingRequiredAppLayers"]
                ),
                "objectsMissingRequiredCloudLayers": len(
                    baseline["objectsMissingRequiredCloudLayers"]
                ),
            }
        ).strip()
    )
    return 0
