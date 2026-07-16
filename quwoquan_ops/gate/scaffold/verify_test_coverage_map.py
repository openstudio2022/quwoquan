#!/usr/bin/env python3
"""Verify acceptance recorded evidence and page/journey reverse bindings."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

from test_directory_inventory_lib import (
    PAGE_INVENTORY_PATH,
    REQUIRED_PAGE_CASE_SUFFIXES,
    ROOT,
    iter_canonical_files,
    recorded_file_is_canonical,
)


FEATURE_TREE = ROOT / "specs" / "feature-tree"
OUTPUT_REPORT = ROOT / ".qwq_output" / "env" / "repo" / "runs" / "tests" / "coverage-map" / "report.json"
JOURNEY_REGISTRY_PATH = FEATURE_TREE / "journey_scenario_registry.yaml"
STRICT_TRACEABILITY_PATHS = {
    "specs/feature-tree/runtime/runtime-test-pyramid/acceptance.yaml",
    "specs/feature-tree/runtime/runtime-testinfra/acceptance.yaml",
    "specs/feature-tree/chat-conversation/list-detail-message-delivery/voice-message/acceptance.yaml",
    "specs/feature-tree/chat-conversation/list-detail-message-delivery/realtime-push-and-offline-sync/acceptance.yaml",
    "specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/acceptance.yaml",
    "specs/feature-tree/object-homepage-network/acceptance.yaml",
    "specs/feature-tree/shared-homepage-network/homepage-review-and-content-journey/homepage-overview-and-module-shell/acceptance.yaml",
    "specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/acceptance.yaml",
    "specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management--persona-lifecycle-contract/acceptance.yaml",
    "specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/acceptance.yaml",
    "specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/acceptance.yaml",
    "specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/acceptance.yaml",
    "specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/acceptance.yaml",
    "specs/feature-tree/discovery-content/feed-orchestration-recommendation/acceptance.yaml",
    "specs/feature-tree/discovery-content/feed-orchestration-recommendation/realtime-feed-baseline/acceptance.yaml",
    "specs/feature-tree/discovery-content/feed-orchestration-recommendation/personalized-ranking/acceptance.yaml",
    "specs/feature-tree/discovery-content/exposure-governance/exposure-observability-capacity/acceptance.yaml",
    "specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/acceptance.yaml",
    "specs/feature-tree/platform-ops-governance/config-and-reliability-governance/acceptance.yaml",
    "specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/acceptance.yaml",
    "specs/feature-tree/global-search-experience/cross-domain-search-journey/xiaoqu-entry-handoff/acceptance.yaml",
    "specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/acceptance.yaml",
    "specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/acceptance.yaml",
    "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/acceptance.yaml",
}
STRICT_TRACEABILITY_ITEMS = {
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT1",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT2",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT3",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT4",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT5",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT6",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT7",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT8",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT9",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT10",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT11",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT12",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT13",
    "specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/acceptance.yaml#GWT14",
}
UI_SURFACES_PATH = ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "ui_surfaces.yaml"
APP_ROUTES_PATH = ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "app_routes.yaml"
ACCEPTANCE_GROUPS = (
    "uat_acceptance",
    "domain_acceptance",
    "sit_acceptance",
    "gwt_acceptance",
    "contract_acceptance",
)
DONE_STATUSES = {"implemented", "completed"}
QUALITY_FACETS = (
    "functional",
    "contract",
    "reliability",
    "availability",
    "observability",
    "experience",
    "security",
    "performance",
    "data_consistency",
)
FACET_HINTS = {
    "contract": ("contract", "metadata", "schema", "dto", "api_contract"),
    "reliability": ("reliability", "retry", "timeout", "offline", "failure", "recover"),
    "availability": ("availability", "health", "degrade", "fallback", "rollback"),
    "observability": ("observability", "telemetry", "metric", "metrics", "trace", "log", "audit", "event"),
    "experience": ("experience", "journey", "page", "widget", "ui", "empty", "permission"),
    "security": ("security", "auth", "permission", "privacy", "token", "secret", "redact", "audit"),
    "performance": ("performance", "latency", "capacity", "p95", "p99", "budget", "startup"),
    "data_consistency": ("data_consistency", "consistency", "idempot", "projection", "outbox", "publish", "import", "stable"),
}


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def exit_code(self) -> int:
        if not self.items:
            print(f"[verify] OK: coverage map checked ({OUTPUT_REPORT.relative_to(ROOT)})")
            return 0
        for item in self.items:
            print(f"[verify] FAIL: {item}", file=sys.stderr)
        return 1

    def exit_code_value(self) -> int:
        return 0 if not self.items else 1


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def infer_quality_facet(path_text: str) -> str:
    text = path_text.lower()
    for facet, hints in FACET_HINTS.items():
        if any(hint in text for hint in hints):
            return facet
    return "functional"


def collect_coverage_index() -> dict[str, Any]:
    canonical_files: list[dict[str, str]] = []
    counts: dict[str, dict[str, int]] = {
        "area": {},
        "layer": {},
        "quality_facet": {facet: 0 for facet in QUALITY_FACETS},
    }
    for area, path, layer in iter_canonical_files():
        rel_path = path.relative_to(ROOT).as_posix()
        facet = infer_quality_facet(rel_path)
        canonical_files.append(
            {
                "area": area,
                "layer": layer,
                "quality_facet": facet,
                "source_file": rel_path,
            }
        )
        counts["area"][area] = counts["area"].get(area, 0) + 1
        counts["layer"][layer] = counts["layer"].get(layer, 0) + 1
        counts["quality_facet"][facet] = counts["quality_facet"].get(facet, 0) + 1

    acceptance_quality_facets: dict[str, int] = {facet: 0 for facet in QUALITY_FACETS}
    for path in FEATURE_TREE.rglob("acceptance.yaml"):
        data = load_yaml(path)
        for group_name in ACCEPTANCE_GROUPS:
            group = data.get(group_name) or {}
            if not isinstance(group, dict):
                continue
            for item in group.values():
                if not isinstance(item, dict):
                    continue
                for facet in item.get("quality_facets") or []:
                    facet_text = str(facet)
                    if facet_text in acceptance_quality_facets:
                        acceptance_quality_facets[facet_text] += 1
                test_evidence = item.get("test_evidence") or {}
                for bucket_name in ("primary", "supporting"):
                    for entry in test_evidence.get(bucket_name) or []:
                        if not isinstance(entry, dict):
                            continue
                        facet_text = str(entry.get("quality_facet") or "")
                        if facet_text in acceptance_quality_facets:
                            acceptance_quality_facets[facet_text] += 1

    return {
        "counts": counts,
        "acceptance_quality_facets": acceptance_quality_facets,
        "canonical_files": canonical_files,
    }


def write_coverage_report(index: dict[str, Any], failures: Failures) -> None:
    OUTPUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "suite_id": "test_coverage_map",
        "exit_code": failures.exit_code_value(),
        "status": "passed" if not failures.items else "failed",
        "case_results": [
            {
                "case_id": "local_contract.runtime.test_governance.coverage_map",
                "status": "passed" if not failures.items else "failed",
            }
        ],
        "coverage": index,
    }
    OUTPUT_REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_record(record: Any) -> tuple[str | None, str | None]:
    if isinstance(record, dict):
        if record.get("file"):
            return "file", str(record["file"]).strip()
        if record.get("artifact"):
            return "artifact", str(record["artifact"]).strip()
        if record.get("command"):
            return "command", str(record["command"]).strip()
        return None, None
    text = str(record).strip()
    if not text:
        return None, None
    if text.startswith("file:"):
        return "file", text.split(":", 1)[1].strip()
    if text.startswith("artifact:"):
        return "artifact", text.split(":", 1)[1].strip()
    if text.startswith("command:"):
        return "command", text.split(":", 1)[1].strip()
    return "file", text


def canonical_layer_from_path(path_text: str) -> str | None:
    if path_text.startswith("quwoquan_app/test/"):
        for layer in ("local_contract", "api_integration", "user_acceptance"):
            if path_text.startswith(f"quwoquan_app/test/{layer}/"):
                return layer
        return None
    if path_text.startswith("quwoquan_app/packages/"):
        parts = Path(path_text).parts
        if len(parts) >= 6 and parts[3] == "test" and parts[4] in {
            "local_contract",
            "api_integration",
            "user_acceptance",
        }:
            return parts[4]
        return None
    if path_text.startswith("quwoquan_data/tests/"):
        for layer in ("local_contract", "api_integration", "user_acceptance"):
            if path_text.startswith(f"quwoquan_data/tests/{layer}/"):
                return layer
        return None
    if path_text.startswith("quwoquan_ops/tests/local_contract/"):
        return "local_contract"
    if path_text.startswith("quwoquan_ops/tests/acceptance/api_integration/"):
        return "api_integration"
    if path_text.startswith("quwoquan_ops/tests/acceptance/user_acceptance/"):
        return "user_acceptance"
    if path_text.startswith("quwoquan_service/"):
        if "/tests/support/" in path_text:
            return None
        if "/tests/local_contract/" in path_text:
            return "local_contract"
        if "/tests/api_integration/" in path_text:
            return "api_integration"
        if path_text.endswith("__local_contract_test.go"):
            return "local_contract"
        if path_text.endswith("__api_integration_test.go"):
            return "api_integration"
    return None


def load_report_case_ids(report_path: Path, failures: Failures, owner: str) -> set[str]:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - CLI boundary
        failures.add(f"{owner} report cannot be parsed as JSON: {report_path.relative_to(ROOT)} ({exc})")
        return set()
    case_results = payload.get("case_results")
    if not isinstance(case_results, list):
        failures.add(f"{owner} report missing case_results list: {report_path.relative_to(ROOT)}")
        return set()
    case_ids: set[str] = set()
    for result in case_results:
        if not isinstance(result, dict):
            continue
        case_id = result.get("case_id") or result.get("caseId") or result.get("id")
        if isinstance(case_id, str) and case_id.strip():
            case_ids.add(case_id.strip())
    if not case_ids:
        failures.add(f"{owner} report case_results has no case ids: {report_path.relative_to(ROOT)}")
    return case_ids


def verify_acceptance_recorded_refs(failures: Failures) -> None:
    for path in FEATURE_TREE.rglob("acceptance.yaml"):
        data = load_yaml(path)
        rel_path = path.relative_to(ROOT).as_posix()
        for group_name in ACCEPTANCE_GROUPS:
            group = data.get(group_name) or {}
            if not isinstance(group, dict):
                continue
            for item_id, item in group.items():
                if not isinstance(item, dict):
                    continue
                tests = item.get("tests") or {}
                recorded = tests.get("recorded") or []
                status = str(item.get("status") or "").strip()
                recorded_files_by_layer: dict[str, set[str]] = {}
                artifact_case_ids: set[str] = set()
                has_report_artifact = False
                for record in recorded:
                    kind, value = normalize_record(record)
                    if not value:
                        continue
                    if kind == "command":
                        failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} recorded command is retired: {value}")
                        continue
                    if kind == "artifact":
                        has_report_artifact = True
                        if not (value.startswith(".qwq_output/env/repo/runs/tests/") and value.endswith("report.json")):
                            failures.add(
                                f"{path.relative_to(ROOT)} {group_name}.{item_id} recorded artifact must be .qwq_output/env/repo/runs/tests/**/report.json: {value}"
                            )
                        elif not (ROOT / value).exists():
                            failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} artifact missing: {value}")
                        else:
                            artifact_case_ids.update(
                                load_report_case_ids(
                                    ROOT / value,
                                    failures,
                                    f"{path.relative_to(ROOT)} {group_name}.{item_id}",
                                )
                            )
                        continue
                    if not recorded_file_is_canonical(value):
                        failures.add(
                            f"{path.relative_to(ROOT)} {group_name}.{item_id} recorded file is not canonical: {value}"
                        )
                    elif not (ROOT / value).exists():
                        failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} recorded file missing: {value}")
                    else:
                        layer = canonical_layer_from_path(value)
                        if layer is None:
                            failures.add(
                                f"{path.relative_to(ROOT)} {group_name}.{item_id} cannot infer canonical layer for recorded file: {value}"
                            )
                        else:
                            recorded_files_by_layer.setdefault(layer, set()).add(value)
                test_evidence = item.get("test_evidence") or {}
                primary = test_evidence.get("primary") or []
                supporting = test_evidence.get("supporting") or []
                layers = {
                    str(entry.get("layer"))
                    for entry in [*primary, *supporting]
                    if isinstance(entry, dict) and entry.get("layer")
                }
                evidence_entries = [
                    entry for entry in [*primary, *supporting] if isinstance(entry, dict) and entry.get("layer")
                ]
                if (
                    status in DONE_STATUSES
                    and "user_acceptance" in layers
                    and not {"local_contract", "api_integration"} <= layers
                ):
                    failures.add(
                        f"{path.relative_to(ROOT)} {group_name}.{item_id} user_acceptance entry must reverse-bind local_contract and api_integration"
                    )
                if status in DONE_STATUSES and not recorded:
                    failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} done status lacks recorded evidence")
                strict_item_ref = f"{rel_path}#{item_id}"
                if status in DONE_STATUSES and (
                    rel_path in STRICT_TRACEABILITY_PATHS
                    or strict_item_ref in STRICT_TRACEABILITY_ITEMS
                    or has_report_artifact
                ):
                    for entry in evidence_entries:
                        layer = str(entry.get("layer") or "").strip()
                        cases = {
                            str(case_id).strip()
                            for case_id in (entry.get("cases") or [])
                            if str(case_id).strip()
                        }
                        if not layer or not cases:
                            continue
                        if recorded_files_by_layer.get(layer):
                            continue
                        if cases & artifact_case_ids:
                            continue
                        failures.add(
                            f"{path.relative_to(ROOT)} {group_name}.{item_id} {layer} cases {sorted(cases)} have no traceable canonical recorded file or report case_results"
                        )


def verify_page_inventory(failures: Failures) -> None:
    if not PAGE_INVENTORY_PATH.exists():
        failures.add(f"missing page inventory: {PAGE_INVENTORY_PATH.relative_to(ROOT)}")
        return
    page_inventory = load_yaml(PAGE_INVENTORY_PATH)
    surfaces_meta = load_yaml(UI_SURFACES_PATH).get("surfaces") or []
    routes_meta = load_yaml(APP_ROUTES_PATH).get("routes") or []
    surfaces = page_inventory.get("surfaces") or []
    route_only = page_inventory.get("route_only") or []
    surface_by_id = {str(item["surface_id"]): item for item in surfaces if isinstance(item, dict) and item.get("surface_id")}
    route_only_ids = {str(item["route_id"]) for item in route_only if isinstance(item, dict) and item.get("route_id")}
    meta_surface_ids = {str(item["id"]) for item in surfaces_meta if isinstance(item, dict) and item.get("id")}
    missing_surfaces = sorted(meta_surface_ids - set(surface_by_id))
    extra_surfaces = sorted(set(surface_by_id) - meta_surface_ids)
    if missing_surfaces:
        failures.add(f"page inventory missing metadata surfaces: {', '.join(missing_surfaces[:5])}")
    if extra_surfaces:
        failures.add(f"page inventory has stale surfaces: {', '.join(extra_surfaces[:5])}")

    surface_route_ids = set()
    for meta in surfaces_meta:
        if not isinstance(meta, dict):
            continue
        surface_id = str(meta.get("id") or "")
        owner = str(meta.get("owner") or "")
        route_id = str(meta.get("route_id") or "")
        inventory_row = surface_by_id.get(surface_id)
        if inventory_row is None:
            continue
        if inventory_row.get("owner") != owner:
            failures.add(f"surface {surface_id} owner mismatch: inventory={inventory_row.get('owner')} metadata={owner}")
        if inventory_row.get("route_id") != route_id:
            failures.add(
                f"surface {surface_id} route mismatch: inventory={inventory_row.get('route_id')} metadata={route_id}"
            )
        surface_route_ids.add(route_id)
        source_tests = inventory_row.get("source_tests") or []
        if not isinstance(source_tests, list) or not source_tests:
            failures.add(f"surface {surface_id} missing source_tests")
            continue
        for source in source_tests:
            source_text = str(source)
            if not recorded_file_is_canonical(source_text):
                failures.add(f"surface {surface_id} source test not canonical: {source_text}")
            elif not (ROOT / source_text).exists():
                failures.add(f"surface {surface_id} source test missing: {source_text}")
        canonical_locals = [
            source_text
            for source_text in (str(source) for source in source_tests)
            if canonical_layer_from_path(source_text) == "local_contract"
        ]
        if not canonical_locals:
            failures.add(f"surface {surface_id} has no reverse-bound local_contract canonical tests")
        api_tests = inventory_row.get("api_integration_tests") or []
        if not isinstance(api_tests, list) or not api_tests:
            failures.add(f"surface {surface_id} missing api_integration_tests")
        else:
            for api_test in api_tests:
                api_text = str(api_test)
                if not recorded_file_is_canonical(api_text):
                    failures.add(f"surface {surface_id} api_integration test not canonical: {api_text}")
                elif not (ROOT / api_text).exists():
                    failures.add(f"surface {surface_id} api_integration test missing: {api_text}")
    meta_route_ids = {str(item["id"]) for item in routes_meta if isinstance(item, dict) and item.get("id")}
    covered_route_ids = surface_route_ids | route_only_ids
    missing_routes = sorted(meta_route_ids - covered_route_ids)
    extra_routes = sorted(covered_route_ids - meta_route_ids)
    if missing_routes:
        failures.add(f"page inventory missing route ownership rows: {', '.join(missing_routes[:5])}")
    if extra_routes:
        failures.add(f"page inventory has stale route rows: {', '.join(extra_routes[:5])}")

    for row in route_only:
        if not isinstance(row, dict):
            continue
        route_id = str(row.get("route_id") or "")
        owner = str(row.get("owner") or "")
        if not route_id or not owner:
            failures.add(f"route_only row must declare route_id and owner: {row!r}")
            continue
        for source in row.get("source_tests") or []:
            source_text = str(source)
            if not (ROOT / source_text).exists():
                failures.add(f"route_only {route_id} source test missing: {source_text}")


def verify_page_case_ids(failures: Failures) -> None:
    acceptance_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in FEATURE_TREE.rglob("acceptance.yaml")
    )
    if "user_acceptance.page." not in acceptance_text:
        failures.add("feature-tree acceptance has no user_acceptance.page.* case id")

    page_inventory = load_yaml(PAGE_INVENTORY_PATH) if PAGE_INVENTORY_PATH.exists() else {}
    for surface in page_inventory.get("surfaces") or []:
        if not isinstance(surface, dict):
            continue
        surface_id = str(surface.get("surface_id") or "")
        if not surface_id:
            continue
        for suffix in REQUIRED_PAGE_CASE_SUFFIXES:
            case_id = f"user_acceptance.page.{surface_id}.{suffix}"
            if case_id not in acceptance_text:
                failures.add(f"missing acceptance case id: {case_id}")


def verify_journey_scenario_bindings(failures: Failures) -> None:
    if not JOURNEY_REGISTRY_PATH.exists():
        failures.add(f"missing journey registry: {JOURNEY_REGISTRY_PATH.relative_to(ROOT)}")
        return
    registry = load_yaml(JOURNEY_REGISTRY_PATH)
    journeys = registry.get("journeys") or []
    scenarios = registry.get("scenarios") or []
    journey_by_id = {
        str(item.get("id")): item
        for item in journeys
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    scenario_by_id = {
        str(item.get("id")): item
        for item in scenarios
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    journey_uat_refs = {
        str(journey.get("id") or ""): {str(ref) for ref in (journey.get("uat_refs") or []) if str(ref).strip()}
        for journey in journeys
        if isinstance(journey, dict) and str(journey.get("id") or "").strip()
    }

    for path in FEATURE_TREE.rglob("acceptance.yaml"):
        data = load_yaml(path)
        rel_path = path.relative_to(ROOT).as_posix()
        for group_name in ACCEPTANCE_GROUPS:
            group = data.get(group_name) or {}
            if not isinstance(group, dict):
                continue
            for item_id, item in group.items():
                if not isinstance(item, dict):
                    continue
                item_ref = f"{rel_path}#{item_id}"
                scenario_refs = [str(ref) for ref in (item.get("scenario_refs") or []) if str(ref).strip()]
                if group_name == "uat_acceptance":
                    if not any(item_id in refs for refs in journey_uat_refs.values()):
                        failures.add(f"{rel_path} {group_name}.{item_id} is not referenced by any journey uat_refs")
                for scenario_ref in scenario_refs:
                    journey = journey_by_id.get(scenario_ref)
                    if journey is not None:
                        if group_name == "uat_acceptance" and item_id not in {
                            str(ref) for ref in (journey.get("uat_refs") or []) if str(ref).strip()
                        }:
                            failures.add(
                                f"{rel_path} {group_name}.{item_id} journey {scenario_ref} missing reverse uat_ref {item_id}"
                            )
                        continue
                    scenario = scenario_by_id.get(scenario_ref)
                    if scenario is None:
                        failures.add(f"{rel_path} {group_name}.{item_id} scenario_ref missing from registry: {scenario_ref}")
                        continue
                    acceptance_refs = {
                        str(ref)
                        for ref in (scenario.get("acceptance_refs") or [])
                        if str(ref).strip()
                    }
                    if item_ref not in acceptance_refs:
                        failures.add(
                            f"{rel_path} {group_name}.{item_id} scenario {scenario_ref} missing reverse acceptance_ref {item_ref}"
                        )


def main() -> int:
    failures = Failures()
    verify_acceptance_recorded_refs(failures)
    verify_page_inventory(failures)
    verify_page_case_ids(failures)
    verify_journey_scenario_bindings(failures)
    write_coverage_report(collect_coverage_index(), failures)
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
