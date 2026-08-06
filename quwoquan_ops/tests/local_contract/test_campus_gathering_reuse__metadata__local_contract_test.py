"""校园场景复用 Gathering 的 metadata contract。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
PROFILE_PATH = (
    ROOT
    / "quwoquan_service/services/circle-service/contracts/"
    "circle_management/gathering/ui_config.yaml"
)
ROUTES_PATH = (
    ROOT / "quwoquan_service/contracts/metadata/_shared/app_routes.yaml"
)
SURFACES_PATH = (
    ROOT / "quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml"
)
TOOLS_PATH = (
    ROOT
    / "quwoquan_service/services/assistant-service/contracts/"
    "_shared/assistant_tool_metadata/catalog.yaml"
)
SKILLS_ROOT = (
    ROOT
    / "quwoquan_service/services/assistant-service/resources/"
    "skill_packages/official"
)
TAXONOMY_ROOT = (
    ROOT / "quwoquan_data/control_plane/governance/taxonomy"
)

TRAVEL_PACKAGE_ID = "gathering.travel.shared-action"
CAMPUS_PACKAGE_ID = "gathering.campus.newcomer-interest-meetup"
EXPECTED_STAGE_IDS = (
    "create",
    "discovery",
    "approval",
    "chat",
    "board",
    "plan",
    "outcome",
)


def _load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise AssertionError(f"{path} must contain a mapping")
    return document


def _by_id(entries: object, key: str) -> dict[str, dict[str, Any]]:
    assert isinstance(entries, list)
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        assert isinstance(entry, dict)
        identifier = entry.get(key)
        assert isinstance(identifier, str) and identifier
        assert identifier not in result
        result[identifier] = entry
    return result


def _canonical_operation_ids() -> set[str]:
    operation_ids: set[str] = set()
    services_root = ROOT / "quwoquan_service/services"
    for service_dir in services_root.iterdir():
        contracts_root = service_dir / "contracts"
        domain_path = contracts_root / "domain.yaml"
        if not domain_path.is_file():
            continue
        domain = _load_yaml(domain_path).get("domain")
        assert isinstance(domain, str) and domain
        for operations_path in contracts_root.glob("*/*/operations.yaml"):
            relative = operations_path.relative_to(contracts_root)
            object_name = relative.parts[1]
            document = _load_yaml(operations_path)
            for route in document.get("api_routes") or []:
                assert isinstance(route, dict)
                operation = route.get("operation")
                assert isinstance(operation, str) and operation
                operation_ids.add(f"{domain}.{object_name}.{operation}")
    return operation_ids


def _canonical_object_ids() -> set[str]:
    object_ids: set[str] = set()
    services_root = ROOT / "quwoquan_service/services"
    for service_dir in services_root.iterdir():
        contracts_root = service_dir / "contracts"
        domain_path = contracts_root / "domain.yaml"
        if not domain_path.is_file():
            continue
        domain = _load_yaml(domain_path).get("domain")
        assert isinstance(domain, str) and domain
        for object_path in contracts_root.glob("*/*/object.yaml"):
            relative = object_path.relative_to(contracts_root)
            object_ids.add(f"{domain}.{relative.parts[1]}")
    return object_ids


def _resolved_contract(
    package: dict[str, Any],
    *,
    behavior_contracts: dict[str, dict[str, Any]],
    placement_profiles: dict[str, dict[str, Any]],
    distribution_scenes: dict[str, dict[str, Any]],
) -> dict[str, tuple[str, ...]]:
    behavior = behavior_contracts[package["behavior_contract_ref"]]
    placement = placement_profiles[package["placement_profile_ref"]]
    scene = distribution_scenes[package["distribution_scene_ref"]]
    assert scene["placement_profile_ref"] == package["placement_profile_ref"]

    operation_ids: list[str] = []
    stages = behavior["stages"]
    assert isinstance(stages, list)
    for stage in stages:
        assert isinstance(stage, dict)
        operation_ids.extend(stage["operation_ids"])

    placements = placement["placements"]
    assert isinstance(placements, list)
    return {
        "operation_ids": tuple(operation_ids),
        "route_ids": tuple(item["route_id"] for item in placements),
        "surface_ids": tuple(item["surface_id"] for item in placements),
        "tool_ids": tuple(behavior["tool_ids"]),
        "skill_refs": tuple(package["skill_refs"]),
        "object_refs": tuple(package["object_refs"]),
    }


def _all_mapping_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_all_mapping_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_mapping_keys(child))
    return keys


# spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
def test_travel_and_campus_profiles_resolve_the_same_behavior_contract() -> None:
    document = _load_yaml(PROFILE_PATH)
    assert document["schema"] == "gathering-experience-package"

    behavior_contracts = _by_id(document["behavior_contracts"], "id")
    placement_profiles = _by_id(document["placement_profiles"], "id")
    distribution_scenes = _by_id(document["distribution_scenes"], "id")
    packages = _by_id(document["experience_packages"], "id")

    assert set(packages) == {TRAVEL_PACKAGE_ID, CAMPUS_PACKAGE_ID}
    travel = packages[TRAVEL_PACKAGE_ID]
    campus = packages[CAMPUS_PACKAGE_ID]
    assert tuple(stage["id"] for stage in behavior_contracts[
        travel["behavior_contract_ref"]
    ]["stages"]) == EXPECTED_STAGE_IDS

    travel_contract = _resolved_contract(
        travel,
        behavior_contracts=behavior_contracts,
        placement_profiles=placement_profiles,
        distribution_scenes=distribution_scenes,
    )
    campus_contract = _resolved_contract(
        campus,
        behavior_contracts=behavior_contracts,
        placement_profiles=placement_profiles,
        distribution_scenes=distribution_scenes,
    )
    assert travel_contract == campus_contract

    package_difference_keys = {
        key for key in set(travel) | set(campus) if travel.get(key) != campus.get(key)
    }
    assert package_difference_keys == {"id", "scenario_id", "tag_refs", "topic_refs"}


# spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
def test_profile_references_only_existing_contract_metadata_and_skill_assets() -> None:
    document = _load_yaml(PROFILE_PATH)
    behavior_contracts = _by_id(document["behavior_contracts"], "id")
    placement_profiles = _by_id(document["placement_profiles"], "id")
    distribution_scenes = _by_id(document["distribution_scenes"], "id")
    packages = _by_id(document["experience_packages"], "id")

    resolved = _resolved_contract(
        packages[CAMPUS_PACKAGE_ID],
        behavior_contracts=behavior_contracts,
        placement_profiles=placement_profiles,
        distribution_scenes=distribution_scenes,
    )
    assert set(resolved["operation_ids"]) <= _canonical_operation_ids()
    assert set(resolved["object_refs"]) <= _canonical_object_ids()

    routes = _by_id(_load_yaml(ROUTES_PATH)["routes"], "id")
    surfaces = _by_id(_load_yaml(SURFACES_PATH)["surfaces"], "id")
    for surface_id, route_id in zip(
        resolved["surface_ids"],
        resolved["route_ids"],
        strict=True,
    ):
        assert route_id in routes
        assert surface_id in surfaces
        assert surfaces[surface_id]["route_id"] == route_id

    tools = _by_id(_load_yaml(TOOLS_PATH)["tools"], "toolName")
    assert set(resolved["tool_ids"]) <= set(tools)
    for skill_ref in resolved["skill_refs"]:
        manifest_path = SKILLS_ROOT / skill_ref / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["skillId"] == skill_ref


# spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
def test_campus_taxonomy_is_reused_and_uat_requires_real_release_activation() -> None:
    document = _load_yaml(PROFILE_PATH)
    packages = _by_id(document["experience_packages"], "id")
    campus = packages[CAMPUS_PACKAGE_ID]

    for tag_ref in [*campus["topic_refs"], *campus["tag_refs"]]:
        definition_path = TAXONOMY_ROOT / tag_ref / "_definition.json"
        assert definition_path.is_file(), tag_ref

    activation = document["data_activation"]
    assert activation == {
        "source": "quwoquan_data",
        "immutable_release_required": True,
        "environment_import_receipt_required": True,
        "production_fixture_allowed": False,
        "uat_state_without_activation": "open",
    }
    assert document["observability"]["dimensions"] == ["topicRef"]
    assert all(
        forbidden not in key.lower()
        for key in _all_mapping_keys(document)
        for forbidden in ("platform", "vertical")
    )
    assert not (
        ROOT / "quwoquan_service/services/campus-service"
    ).exists()
