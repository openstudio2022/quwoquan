"""跨 execution 累计的「每实体已产出对象数」，以及据此做准入的选取闸门。

`entity_diversity` 的两条约束都按累计计数评估，而单个 execution 看不到累计——
它只看得见自己那一批。累计真相源是 canonical publish 树里已收口的对象包本身：
实体主页是 ``entities/<domain>/<type>/<name>/_entity.json``，其余载体是
``posts/**/manifest.json`` 里的 ``contentType`` 与 ``entityRef``。这里只读这些
对象包，不读任何派生索引，因为派生索引会带来第二份状态台账。

闸门跨轮有状态：配额追逐会分多轮抽取，第 1 轮已准入的候选必须计入第 2 轮的
分布投影，否则同一实体会在同一批次内被反复放行，累计上限形同虚设。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import PUBLISH_ROOT
from governance.coverage.entity_diversity import (
    CARRIERS,
    EntityDiversityError,
    EntityDiversityPolicy,
    admit_diverse_entities,
    load_content_diversity_policy,
)
from governance.coverage.entity_type_taxonomy import entity_ref, require_domain_etype

ENTITY_OBJECT_CARRIER = "homepage"


def normalize_entity_ref(raw: Any) -> str:
    """把任意写法的实体引用收敛成 ``<domain>/<type>/<name>``。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    parts = [part for part in text.strip("/").split("/") if part]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    return "/".join(parts[:3])


def _manifest_entity_refs(manifest: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("entityRef", "normalizedEntityRef"):
        ref = normalize_entity_ref(manifest.get(key))
        if ref:
            refs.append(ref)
    for key in ("entityRefs", "normalizedEntityRefs"):
        for raw in manifest.get(key) or []:
            ref = normalize_entity_ref(raw)
            if ref:
                refs.append(ref)
    # 一篇对象可能同时挂多个实体引用；累计计数按去重后的实体记一次。
    return sorted(set(refs))


def cumulative_entity_counts(
    *, publish_root: Path | None = None
) -> dict[str, dict[str, int]]:
    """返回 ``{carrier: {entityRef: 已收口对象数}}``；没有该载体时为空映射。"""
    root = publish_root or PUBLISH_ROOT
    counts: dict[str, dict[str, int]] = {carrier: {} for carrier in CARRIERS}
    entities_root = root / "entities"
    if entities_root.is_dir():
        for path in sorted(entities_root.rglob("_entity.json")):
            ref = normalize_entity_ref(
                path.parent.relative_to(entities_root).as_posix()
            )
            if not ref:
                continue
            lane = counts[ENTITY_OBJECT_CARRIER]
            lane[ref] = lane.get(ref, 0) + 1
    posts_root = root / "posts"
    if posts_root.is_dir():
        for path in sorted(posts_root.rglob("manifest.json")):
            manifest = read_json(path)
            if not isinstance(manifest, Mapping):
                continue
            carrier = str(manifest.get("contentType") or "").strip()
            if carrier not in counts:
                continue
            for ref in _manifest_entity_refs(manifest):
                lane = counts[carrier]
                lane[ref] = lane.get(ref, 0) + 1
    return counts


@dataclass(frozen=True, slots=True)
class DiversityRejection:
    """一个候选被哪条约束、在哪个载体上挡下。"""

    entity_ref: str
    carrier: str
    constraint: str
    reason: str

    def to_document(self) -> dict[str, str]:
        return {
            "entityRef": self.entity_ref,
            "carrier": self.carrier,
            "constraint": self.constraint,
            "reason": self.reason,
        }


@dataclass(slots=True)
class EntityDiversityGate:
    """按累计分布对候选做多样性准入，跨轮累积自己的投影。"""

    carriers: tuple[str, ...]
    policy: EntityDiversityPolicy
    projected: dict[str, dict[str, int]]
    admitted_refs: list[str] = field(default_factory=list)
    rejections: list[DiversityRejection] = field(default_factory=list)

    @classmethod
    def for_carriers(
        cls,
        carriers: Iterable[str],
        *,
        publish_root: Path | None = None,
        policy: EntityDiversityPolicy | None = None,
        cumulative_counts: Mapping[str, Mapping[str, int]] | None = None,
    ) -> EntityDiversityGate:
        active = tuple(
            carrier
            for carrier in CARRIERS
            if carrier in {str(name).strip() for name in carriers}
        )
        if not active:
            raise EntityDiversityError(
                "diversity gate requires at least one active carrier"
            )
        counts = (
            cumulative_counts
            if cumulative_counts is not None
            else cumulative_entity_counts(publish_root=publish_root)
        )
        return cls(
            carriers=active,
            policy=policy or load_content_diversity_policy(),
            projected={
                carrier: {
                    str(ref): int(value)
                    for ref, value in (counts.get(carrier) or {}).items()
                }
                for carrier in active
            },
        )

    def admit_entity_refs(self, entity_refs: Sequence[str]) -> tuple[str, ...]:
        """准入仍有载体余量的候选，并把准入结果并入投影。

        任一在场载体还有余量就放行：文章/图片/视频都是在已选实体上产出的，
        全部载体都到顶才说明这个实体对本批次已经没有产能价值。
        """
        admitted: list[str] = []
        for raw in entity_refs:
            ref = normalize_entity_ref(raw)
            if not ref:
                raise EntityDiversityError(
                    "diversity gate candidate entityRef must be non-empty"
                )
            granted: list[str] = []
            refused: list[DiversityRejection] = []
            for carrier in self.carriers:
                outcome = admit_diverse_entities(
                    (ref,),
                    carrier=carrier,
                    cumulative_counts=self.projected[carrier],
                    policy=self.policy,
                )
                if outcome.admitted:
                    granted.append(carrier)
                    continue
                for _ref, reason in outcome.entity_cap_rejected:
                    refused.append(
                        DiversityRejection(ref, carrier, "entity_cap", reason)
                    )
                for _ref, reason in outcome.concentration_rejected:
                    refused.append(
                        DiversityRejection(ref, carrier, "concentration", reason)
                    )
            if not granted:
                self.rejections.extend(refused)
                continue
            for carrier in granted:
                lane = self.projected[carrier]
                lane[ref] = lane.get(ref, 0) + 1
            admitted.append(ref)
            self.admitted_refs.append(ref)
        return tuple(admitted)

    def admit_rows(
        self, rows: Sequence[Mapping[str, Any]]
    ) -> list[Mapping[str, Any]]:
        """按候选行的 ``name``/``entityType`` 派生实体引用后做准入。"""
        by_ref: dict[str, list[Mapping[str, Any]]] = {}
        ordered_refs: list[str] = []
        for row in rows:
            ref = self.row_entity_ref(row)
            if ref not in by_ref:
                by_ref[ref] = []
                ordered_refs.append(ref)
            by_ref[ref].append(row)
        admitted = set(self.admit_entity_refs(tuple(ordered_refs)))
        return [
            row
            for ref in ordered_refs
            if ref in admitted
            for row in by_ref[ref]
        ]

    @staticmethod
    def row_entity_ref(row: Mapping[str, Any]) -> str:
        name = str(row.get("name") or "").strip()
        if not name:
            raise EntityDiversityError("diversity候选行缺 name，无法派生实体引用")
        domain, entity_type = require_domain_etype(
            row.get("entityType"), context=f"diversity候选[{name}]"
        )
        return normalize_entity_ref(entity_ref(domain, entity_type, name))

    def report(self) -> dict[str, Any]:
        return {
            "policyId": self.policy.policy_id,
            "carriers": list(self.carriers),
            "admittedCount": len(self.admitted_refs),
            "rejectedCount": len(self.rejections),
            "rejected": [row.to_document() for row in self.rejections],
            "topEntityShare": {
                carrier: round(self.policy.top_entity_share(counts), 4)
                for carrier, counts in sorted(self.projected.items())
            },
        }


__all__ = [
    "ENTITY_OBJECT_CARRIER",
    "DiversityRejection",
    "EntityDiversityGate",
    "cumulative_entity_counts",
    "normalize_entity_ref",
]
