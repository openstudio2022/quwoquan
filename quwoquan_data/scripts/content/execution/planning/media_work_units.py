"""Project immutable accepted media assets into exact content work objects."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

_SHA256_PREFIX = "sha256:"
_UNMAPPED = "DATA.SOURCE.ENTITY_CATALOG_UNMAPPED"
_AMBIGUOUS = "DATA.SOURCE.ENTITY_CATALOG_AMBIGUOUS"


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _SHA256_PREFIX + hashlib.sha256(encoded).hexdigest()


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"media work-unit candidate {field} must be non-empty")
    return value.strip()


def _sha256(payload: Mapping[str, Any], field: str) -> str:
    value = _required_text(payload, field)
    if (
        len(value) != 71
        or not value.startswith(_SHA256_PREFIX)
        or any(char not in "0123456789abcdef" for char in value[7:])
    ):
        raise ValueError(f"media work-unit candidate {field} must be sha256")
    return value


def _names(values: Iterable[object]) -> tuple[str, ...]:
    result = tuple(
        dict.fromkeys(str(value).strip() for value in values if str(value).strip())
    )
    if not result:
        raise ValueError("media work-unit candidate requires entity identity")
    return result


@dataclass(frozen=True, slots=True)
class MediaWorkUnitCandidate:
    carrier: str
    manifest_ref: str
    manifest_digest: str
    receipt_ref: str
    receipt_digest: str
    asset_id: str
    content_sha256: str
    source_entity_id: str
    source_entity_aliases: tuple[str, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MediaWorkUnitCandidate":
        carrier = _required_text(payload, "carrier")
        if carrier not in {"image", "video"}:
            raise ValueError("media work-unit carrier must be image or video")
        source_entity_id = _required_text(payload, "sourceEntityId")
        aliases = _names(
            [source_entity_id, *(payload.get("sourceEntityAliases") or [])]
        )[1:]
        return cls(
            carrier=carrier,
            manifest_ref=_required_text(payload, "manifestRef"),
            manifest_digest=_sha256(payload, "manifestDigest"),
            receipt_ref=_required_text(payload, "receiptRef"),
            receipt_digest=_sha256(payload, "receiptDigest"),
            asset_id=_required_text(payload, "assetId"),
            content_sha256=_sha256(payload, "contentSha256"),
            source_entity_id=source_entity_id,
            source_entity_aliases=aliases,
        )

    @property
    def candidate_names(self) -> tuple[str, ...]:
        return _names((self.source_entity_id, *self.source_entity_aliases))

    def evidence_dict(self) -> dict[str, str]:
        return {
            "carrier": self.carrier,
            "manifestRef": self.manifest_ref,
            "manifestDigest": self.manifest_digest,
            "receiptRef": self.receipt_ref,
            "receiptDigest": self.receipt_digest,
            "assetId": self.asset_id,
            "contentSha256": self.content_sha256,
            "sourceEntityId": self.source_entity_id,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.evidence_dict(),
            "sourceEntityAliases": list(self.source_entity_aliases),
        }


@dataclass(frozen=True, slots=True)
class MediaWorkUnitProjection:
    work_units: tuple[dict[str, Any], ...]
    exclusions: tuple[dict[str, Any], ...]
    coverage_target_names: tuple[str, ...]

    @property
    def mapped_object_count(self) -> int:
        return len(self.work_units)

    def shortfall(self, approved_quota: int) -> int:
        return max(0, approved_quota - self.mapped_object_count)


def _target_names(target: Mapping[str, Any]) -> tuple[str, ...]:
    return _names(
        (
            target.get("name"),
            target.get("sourceName"),
            *(target.get("aliases") or []),
        )
    )


def project_media_work_units(
    candidates: Iterable[Mapping[str, Any]],
    coverage_targets: Iterable[Mapping[str, Any]],
) -> MediaWorkUnitProjection:
    """Bind each accepted asset to exactly one governed catalog entity.

    No target is synthesized here. Missing and ambiguous catalog identities are
    frozen as typed per-asset exclusions so one bad asset cannot fail siblings.
    """
    parsed = tuple(MediaWorkUnitCandidate.from_mapping(row) for row in candidates)
    if not parsed:
        return MediaWorkUnitProjection((), (), ())
    targets = tuple(dict(row) for row in coverage_targets)
    target_keys: tuple[tuple[str, str, frozenset[str]], ...] = tuple(
        (
            _required_text(target, "name"),
            _required_text(target, "entityType"),
            frozenset(value.casefold() for value in _target_names(target)),
        )
        for target in targets
    )
    asset_keys: set[tuple[str, str]] = set()
    content_digests: set[str] = set()
    work_units: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    coverage_order: list[str] = []
    for candidate in parsed:
        asset_key = (candidate.receipt_ref, candidate.asset_id)
        if asset_key in asset_keys:
            raise ValueError(
                "media work-unit candidates contain duplicate receipt/asset identity"
            )
        if candidate.content_sha256 in content_digests:
            raise ValueError("media work-unit candidates contain duplicate contentSha256")
        asset_keys.add(asset_key)
        content_digests.add(candidate.content_sha256)
        primary_key = candidate.source_entity_id.casefold()
        exact_primary_matches = [
            (name, entity_type)
            for name, entity_type, _names in target_keys
            if name.casefold() == primary_key
        ]
        primary_matches = [
            (name, entity_type)
            for name, entity_type, names in target_keys
            if primary_key in names
        ]
        alias_key = frozenset(
            value.casefold() for value in candidate.source_entity_aliases
        )
        alias_matches = [
            (name, entity_type)
            for name, entity_type, names in target_keys
            if names & alias_key
        ]
        # ``sourceEntityId`` is the manifest's object identity; aliases only
        # normalize it when the primary name is absent from the governed
        # catalog.  Combining both sets up front lets one unrelated alias turn
        # a direct canonical match into a false ambiguity (for example a
        # ``都江堰`` asset whose historical aliases also mention 熊猫谷).
        matches = (
            exact_primary_matches
            or primary_matches
            or alias_matches
        )
        if len(matches) != 1:
            evidence = candidate.evidence_dict()
            exclusions.append(
                {
                    "workUnitCandidateId": _digest(
                        {**evidence, "candidateNames": list(candidate.candidate_names)}
                    ),
                    **evidence,
                    "candidateNames": list(candidate.candidate_names),
                    "code": _UNMAPPED if not matches else _AMBIGUOUS,
                }
            )
            continue
        target_name, target_type = matches[0]
        stable = {
            **candidate.evidence_dict(),
            "coverageTarget": {
                "name": target_name,
                "entityType": target_type,
            },
        }
        work_units.append({"workUnitId": _digest(stable), **stable})
        if target_name not in coverage_order:
            coverage_order.append(target_name)
    return MediaWorkUnitProjection(
        work_units=tuple(work_units),
        exclusions=tuple(exclusions),
        coverage_target_names=tuple(coverage_order),
    )


@dataclass(frozen=True, slots=True)
class MediaWorkUnitObjectBinding:
    """一个 workUnit 到一个 content object 的唯一身份绑定。

    brief 与 content object 必须共享 ``object_identity()`` 返回的同一映射，
    identity 只在此处物化一次，调用方不得各自拼装。
    """

    work_unit_id: str
    carrier: str
    coverage_target_name: str
    coverage_target_type: str
    receipt_ref: str
    asset_id: str
    content_sha256: str

    def object_identity(self) -> dict[str, str]:
        return {"workUnitId": self.work_unit_id}

    def object_ref(self, *, target: str) -> str:
        normalized = str(target or "").strip()
        if not normalized:
            raise ValueError("media work-unit object ref requires a coverage target")
        short = self.work_unit_id.removeprefix(_SHA256_PREFIX)[:12]
        return f"{normalized}_{self.carrier}_{short}".replace("/", "_")


@dataclass(frozen=True, slots=True)
class MediaWorkUnitObjectBindingSet:
    bindings: tuple[MediaWorkUnitObjectBinding, ...]
    exclusions: tuple[dict[str, Any], ...]

    def by_work_unit_id(self) -> dict[str, MediaWorkUnitObjectBinding]:
        return {binding.work_unit_id: binding for binding in self.bindings}


def _object_binding_exclusion(
    raw: Mapping[str, Any],
    *,
    code: str,
) -> dict[str, Any]:
    """把无法唯一映射的单资产写成 typed exclusion，不牵连同批其它资产。"""

    candidate = MediaWorkUnitCandidate.from_mapping(raw)
    evidence = candidate.evidence_dict()
    candidate_names = list(candidate.candidate_names)
    return {
        "workUnitCandidateId": _digest(
            {**evidence, "candidateNames": candidate_names}
        ),
        **evidence,
        "candidateNames": candidate_names,
        "code": code,
    }


def media_work_unit_object_bindings(
    rows: Iterable[Mapping[str, Any]],
    *,
    carrier: str,
) -> MediaWorkUnitObjectBindingSet:
    """把冻结 workUnit 投影为逐一对应的 content object 身份绑定。

    无法唯一映射的资产（缺 canonical coverage target、workUnitId 摘要漂移或
    同一 identity 重复出现）只写该资产的 typed exclusion，其余资产照常绑定。
    """

    if carrier not in {"image", "video"}:
        raise ValueError("media work-unit carrier must be image or video")
    bindings: list[MediaWorkUnitObjectBinding] = []
    exclusions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_assets: set[tuple[str, str]] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise TypeError("media workUnit rows must contain objects")
        if str(raw.get("carrier") or "").strip() != carrier:
            continue
        candidate = MediaWorkUnitCandidate.from_mapping(raw)
        target = raw.get("coverageTarget")
        if not isinstance(target, Mapping):
            exclusions.append(_object_binding_exclusion(raw, code=_UNMAPPED))
            continue
        try:
            target_name = _required_text(target, "name")
            target_type = _required_text(target, "entityType")
        except TypeError:
            exclusions.append(_object_binding_exclusion(raw, code=_UNMAPPED))
            continue
        stable = {
            **candidate.evidence_dict(),
            "coverageTarget": {"name": target_name, "entityType": target_type},
        }
        try:
            work_unit_id = _sha256(raw, "workUnitId")
        except (TypeError, ValueError):
            exclusions.append(_object_binding_exclusion(raw, code=_AMBIGUOUS))
            continue
        asset_key = (candidate.receipt_ref, candidate.asset_id)
        if work_unit_id != _digest(stable) or work_unit_id in seen_ids or asset_key in seen_assets:
            exclusions.append(_object_binding_exclusion(raw, code=_AMBIGUOUS))
            continue
        seen_ids.add(work_unit_id)
        seen_assets.add(asset_key)
        bindings.append(
            MediaWorkUnitObjectBinding(
                work_unit_id=work_unit_id,
                carrier=carrier,
                coverage_target_name=target_name,
                coverage_target_type=target_type,
                receipt_ref=candidate.receipt_ref,
                asset_id=candidate.asset_id,
                content_sha256=candidate.content_sha256,
            )
        )
    return MediaWorkUnitObjectBindingSet(
        bindings=tuple(bindings),
        exclusions=tuple(exclusions),
    )


def work_unit_object_binding(
    candidate: Mapping[str, Any],
    *,
    carrier: str,
) -> MediaWorkUnitObjectBinding | None:
    """解析单个 plan candidate 声明的 workUnit 身份。

    ``None`` 表示该 candidate 未声明 workUnit 身份（quota-only 模式）；
    声明了但无法唯一映射时抛错，绝不静默产出无身份对象。
    """

    declared = candidate.get("workUnitId")
    if declared is None:
        return None
    binding_set = media_work_unit_object_bindings(
        [{**dict(candidate), "carrier": carrier}],
        carrier=carrier,
    )
    if len(binding_set.bindings) != 1:
        raise ValueError(
            "media plan candidate declares a workUnitId that cannot be bound to "
            "exactly one content object"
        )
    return binding_set.bindings[0]


def work_units_by_target(spec: Mapping[str, Any], *, carrier: str) -> dict[str, tuple[dict[str, Any], ...]]:
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in content.get("workUnits") or []:
        if not isinstance(raw, Mapping) or str(raw.get("carrier") or "") != carrier:
            continue
        target = raw.get("coverageTarget")
        if not isinstance(target, Mapping):
            continue
        name = str(target.get("name") or "").strip()
        if name:
            grouped.setdefault(name, []).append(dict(raw))
    return {name: tuple(rows) for name, rows in grouped.items()}


def validate_frozen_work_units(rows: object) -> tuple[dict[str, Any], ...]:
    if rows is None:
        return ()
    if not isinstance(rows, list):
        raise TypeError("execution content.workUnits must be an array")
    frozen: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise TypeError("execution content.workUnits must contain objects")
        candidate = MediaWorkUnitCandidate.from_mapping(raw)
        target = raw.get("coverageTarget")
        if not isinstance(target, Mapping):
            raise TypeError("media workUnit coverageTarget must be an object")
        stable: dict[str, Any] = {
            **candidate.evidence_dict(),
            "coverageTarget": {
                "name": _required_text(target, "name"),
                "entityType": _required_text(target, "entityType"),
            },
        }
        work_unit_id = _sha256(raw, "workUnitId")
        if work_unit_id != _digest(stable):
            raise ValueError("media workUnitId digest drift")
        if work_unit_id in seen_ids:
            raise ValueError("execution content.workUnits contains duplicate ids")
        seen_ids.add(work_unit_id)
        frozen.append({"workUnitId": work_unit_id, **stable})
    return tuple(frozen)


def validate_frozen_work_unit_exclusions(rows: object) -> tuple[dict[str, Any], ...]:
    if rows is None:
        return ()
    if not isinstance(rows, list):
        raise TypeError("execution content.workUnitExclusions must be an array")
    frozen: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise TypeError("execution content.workUnitExclusions must contain objects")
        candidate = MediaWorkUnitCandidate.from_mapping(raw)
        candidate_names = _names(raw.get("candidateNames") or ())
        code = _required_text(raw, "code")
        if code not in {_UNMAPPED, _AMBIGUOUS}:
            raise ValueError("media work-unit exclusion code is unsupported")
        evidence = candidate.evidence_dict()
        candidate_id = _sha256(raw, "workUnitCandidateId")
        if candidate_id != _digest(
            {**evidence, "candidateNames": list(candidate_names)}
        ):
            raise ValueError("media workUnitCandidateId digest drift")
        if candidate_id in seen_ids:
            raise ValueError("execution content.workUnitExclusions contains duplicate ids")
        seen_ids.add(candidate_id)
        frozen.append(
            {
                "workUnitCandidateId": candidate_id,
                **evidence,
                "candidateNames": list(candidate_names),
                "code": code,
            }
        )
    return tuple(frozen)


__all__ = [
    "MediaWorkUnitCandidate",
    "MediaWorkUnitObjectBinding",
    "MediaWorkUnitObjectBindingSet",
    "MediaWorkUnitProjection",
    "media_work_unit_object_bindings",
    "project_media_work_units",
    "validate_frozen_work_unit_exclusions",
    "validate_frozen_work_units",
    "work_unit_object_binding",
    "work_units_by_target",
]
