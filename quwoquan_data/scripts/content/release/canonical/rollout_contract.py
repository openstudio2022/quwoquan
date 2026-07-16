"""Static contract for the Zhejiang/Sichuan homepage rollout."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from core.paths import REPO_ROOT
from core.control_types import (
    MILESTONE_ORDER,
    MILESTONE_PREDECESSOR,
    ContentType,
    ReplacementPolicy,
    RolloutMilestone,
    SelectionPolicy,
)
from content.execution.identity import ExecutionIdentity
from governance.coverage.master_list import (
    iter_master_leaves,
    load_master_list_file,
    master_list_files,
)


ROLLOUT_PATH = (
    REPO_ROOT
    / "quwoquan_data/verticals/travel/coverage/two_province_homepage_rollout.yaml"
)
class RolloutMilestoneError(ValueError):
    """A release or execution does not meet the immutable rollout contract."""


@dataclass(frozen=True, slots=True)
class ProvinceContract:
    province: str
    scope: str
    canary_targets: tuple[str, ...]
    canary_entity_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RolloutContract:
    rollout_id: str
    vertical: str
    content_type: ContentType
    intent: str
    release_scope: str
    provinces: tuple[ProvinceContract, ...]
    selection_policy: SelectionPolicy
    replacement_policy: ReplacementPolicy
    uat_shard_size: int
    milestone_batch_targets: Mapping[RolloutMilestone, Mapping[str, int]]
    milestone_cumulative_targets: Mapping[RolloutMilestone, Mapping[str, int]]

    def province_for_scope(self, scope: str) -> ProvinceContract:
        for province in self.provinces:
            if province.scope == scope:
                return province
        raise RolloutMilestoneError(f"scope is not part of {self.rollout_id}: {scope}")

    def batch_count(self, milestone: RolloutMilestone, province: ProvinceContract) -> int:
        target = self.milestone_batch_targets.get(milestone)
        if not isinstance(target, Mapping):
            raise RolloutMilestoneError(f"invalid milestone batch target: {milestone}")
        value = target.get(province.province)
        if not isinstance(value, int) or value < 1:
            raise RolloutMilestoneError(
                f"invalid {milestone} batch target for {province.province}"
            )
        return value

    def cumulative_count(self, milestone: RolloutMilestone, province: ProvinceContract) -> int:
        target = self.milestone_cumulative_targets.get(milestone)
        if not isinstance(target, Mapping):
            raise RolloutMilestoneError(f"invalid milestone cumulative target: {milestone}")
        value = target.get(province.province)
        if not isinstance(value, int) or value < 1:
            raise RolloutMilestoneError(
                f"invalid {milestone} cumulative target for {province.province}"
            )
        return value


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RolloutMilestoneError(f"{label} must be an object")
    return value


def _master_entity_refs(province: str, names: tuple[str, ...]) -> tuple[str, ...]:
    wanted = set(names)
    found: dict[str, str] = {}
    for path in master_list_files(provinces=[province]):
        data = load_master_list_file(path)
        for _district, leaf in iter_master_leaves(data):
            name = str(leaf.get("canonicalName") or leaf.get("name") or "").strip()
            if name not in wanted:
                continue
            entity_type = str(leaf.get("entityType") or "").strip().strip("/")
            if len(entity_type.split("/")) != 2:
                raise RolloutMilestoneError(
                    f"master list entityType is invalid for {province}/{name}"
                )
            ref = f"{entity_type}/{name}"
            previous = found.setdefault(name, ref)
            if previous != ref:
                raise RolloutMilestoneError(
                    f"master list has conflicting refs for {province}/{name}"
                )
    missing = [name for name in names if name not in found]
    if missing:
        raise RolloutMilestoneError(
            f"canary target missing from master list for {province}: {', '.join(missing)}"
        )
    return tuple(found[name] for name in names)


def load_rollout_contract(path: Path = ROLLOUT_PATH) -> RolloutContract:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RolloutMilestoneError(f"rollout contract unreadable: {path}: {exc}") from exc
    doc = _mapping(raw, label="rollout contract")
    if doc.get("schemaVersion") != "quwoquan.travel.homepage_rollout/3":
        raise RolloutMilestoneError("rollout contract schemaVersion is invalid")
    required = ("rolloutId", "vertical", "contentType", "intent", "releaseScope")
    values = {key: str(doc.get(key) or "").strip() for key in required}
    if not all(values.values()):
        raise RolloutMilestoneError("rollout contract identity is incomplete")
    raw_provinces = doc.get("provinces")
    if not isinstance(raw_provinces, list) or len(raw_provinces) != 2:
        raise RolloutMilestoneError("rollout contract must define exactly two provinces")
    provinces: list[ProvinceContract] = []
    for index, raw_province in enumerate(raw_provinces):
        row = _mapping(raw_province, label=f"provinces[{index}]")
        province = str(row.get("province") or "").strip()
        scope = str(row.get("scope") or "").strip()
        targets = row.get("canaryTargets")
        if not province or not scope or not isinstance(targets, list) or not targets:
            raise RolloutMilestoneError(f"provinces[{index}] is incomplete")
        normalized_targets = tuple(str(item).strip() for item in targets if str(item).strip())
        if len(normalized_targets) != len(set(normalized_targets)):
            raise RolloutMilestoneError(f"provinces[{index}] canaryTargets are duplicated")
        provinces.append(
            ProvinceContract(
                province,
                scope,
                normalized_targets,
                _master_entity_refs(province, normalized_targets),
            )
        )
    if len({item.province for item in provinces}) != 2 or len({item.scope for item in provinces}) != 2:
        raise RolloutMilestoneError("rollout provinces or scopes are duplicated")

    try:
        content_type = ContentType(values["contentType"])
        selection_policy = SelectionPolicy(str(doc.get("selectionPolicy") or ""))
        replacement_policy = ReplacementPolicy(str(doc.get("replacementPolicy") or ""))
    except ValueError as exc:
        raise RolloutMilestoneError(f"rollout closed vocabulary is invalid: {exc}") from exc
    verification = _mapping(doc.get("verification"), label="verification")
    uat_shard_size = verification.get("appUatShardSize")
    if not isinstance(uat_shard_size, int) or isinstance(uat_shard_size, bool) or uat_shard_size < 1:
        raise RolloutMilestoneError("verification.appUatShardSize must be a positive integer")

    raw_milestones = _mapping(doc.get("milestones"), label="milestones")
    batch_targets: dict[RolloutMilestone, Mapping[str, int]] = {}
    cumulative_targets: dict[RolloutMilestone, Mapping[str, int]] = {}
    for milestone in MILESTONE_PREDECESSOR:
        row = _mapping(raw_milestones.get(milestone.value), label=f"milestones.{milestone.value}")
        for field, destination in (
            ("batchTarget", batch_targets),
            ("cumulativeTarget", cumulative_targets),
        ):
            values_by_province = _mapping(
                row.get(field), label=f"milestones.{milestone.value}.{field}"
            )
            normalized: dict[str, int] = {}
            for province in provinces:
                count = values_by_province.get(province.province)
                if not isinstance(count, int) or count < 1:
                    raise RolloutMilestoneError(
                        f"milestones.{milestone.value}.{field} is invalid for {province.province}"
                    )
                normalized[province.province] = count
            if set(values_by_province) != set(normalized):
                raise RolloutMilestoneError(
                    f"milestones.{milestone.value}.{field} has unknown province target"
                )
            destination[milestone] = normalized

    contract = RolloutContract(
        values["rolloutId"],
        values["vertical"],
        content_type,
        values["intent"],
        values["releaseScope"],
        tuple(provinces),
        selection_policy,
        replacement_policy,
        uat_shard_size,
        batch_targets,
        cumulative_targets,
    )
    for province in contract.provinces:
        if contract.batch_count(RolloutMilestone.CANARY, province) != len(province.canary_targets):
            raise RolloutMilestoneError(
                f"canary target count does not match canaryTargets for {province.province}"
            )
        running = 0
        for milestone in MILESTONE_ORDER:
            running += contract.batch_count(milestone, province)
            if contract.cumulative_count(milestone, province) != running:
                raise RolloutMilestoneError(
                    f"{milestone.value} cumulative target does not equal batch sum for {province.province}"
                )
    return contract


def identity_matches(identity: ExecutionIdentity, contract: RolloutContract) -> bool:
    return (
        identity.vertical == contract.vertical
        and identity.content_type == contract.content_type
        and identity.intent == contract.intent
    )


__all__ = [
    "MILESTONE_ORDER",
    "MILESTONE_PREDECESSOR",
    "ProvinceContract",
    "RolloutContract",
    "RolloutMilestoneError",
    "identity_matches",
    "load_rollout_contract",
]
