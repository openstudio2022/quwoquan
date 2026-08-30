"""Cross-execution entity diversity admission.

Content concentrating on a handful of entities is a supply defect that no
single execution can see: each batch stays inside its own quota while the
cumulative catalog keeps re-covering the same places. Both constraints here are
therefore evaluated against cumulative counts across executions, not against
one batch.

A candidate over its cap is *not admitted*; that is a selection outcome, not a
failure. Only when capping leaves the pool below the approved quota does the
pursuit loop turn it into a typed shortfall.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.schema import assert_valid

POLICY_PATH = (
    Path(__file__).resolve().parents[3]
    / "control_plane/_shared/content_diversity.policy.yaml"
)

CARRIERS = ("homepage", "article", "image", "video")


class EntityDiversityError(ValueError):
    """The diversity policy itself is unusable (GATE_BLOCK)."""


@dataclass(frozen=True, slots=True)
class HotEntityAllowance:
    """A raised cap for one entity, valid only with its full explicit evidence."""

    entity_ref: str
    caps: tuple[tuple[str, int], ...]
    signal: str
    observed_at: str
    reviewer: str
    justification: str

    def __post_init__(self) -> None:
        # A raised cap without its evidence is a default bypass wearing an
        # allowance's name, so the evidence is checked at the type boundary and
        # not only on the YAML path.
        for label, value in (
            ("entityRef", self.entity_ref),
            ("evidence.signal", self.signal),
            ("evidence.observedAt", self.observed_at),
            ("evidence.reviewer", self.reviewer),
            ("evidence.justification", self.justification),
        ):
            if not str(value).strip():
                raise EntityDiversityError(
                    f"hot entity allowance requires a non-empty {label}"
                )
        if not self.caps:
            raise EntityDiversityError(
                "hot entity allowance requires at least one raised carrier cap"
            )

    def cap(self, carrier: str) -> int | None:
        """The raised cap for one carrier, or absent when this entity has none."""

        for name, value in self.caps:
            if name == carrier:
                return value
        return None


@dataclass(frozen=True, slots=True)
class EntityDiversityPolicy:
    policy_id: str
    default_caps: tuple[tuple[str, int], ...]
    top_entity_count: int
    top_entity_share_ceiling: float
    minimum_cumulative_objects: int
    hot_entities: tuple[HotEntityAllowance, ...]

    def __post_init__(self) -> None:
        caps = dict(self.default_caps)
        missing = [carrier for carrier in CARRIERS if carrier not in caps]
        if missing:
            raise EntityDiversityError(
                "diversity policy maxObjectsPerEntity is missing carriers: "
                + ", ".join(missing)
            )
        if not 0 < self.top_entity_share_ceiling <= 1:
            raise EntityDiversityError(
                "diversity policy topEntityShareCeiling must be in (0, 1]"
            )
        refs = [row.entity_ref for row in self.hot_entities]
        if len(refs) != len(set(refs)):
            raise EntityDiversityError(
                "diversity policy hotEntities must not repeat an entityRef"
            )
        for row in self.hot_entities:
            for carrier, value in row.caps:
                if carrier not in caps:
                    raise EntityDiversityError(
                        f"hot entity {row.entity_ref} names an unknown carrier: {carrier}"
                    )
                if value <= caps[carrier]:
                    raise EntityDiversityError(
                        f"hot entity {row.entity_ref} {carrier} allowance "
                        f"{value} does not exceed the default cap {caps[carrier]}; "
                        "remove the entry instead of restating the default"
                    )

    def entity_cap(self, entity_ref: str, *, carrier: str) -> int:
        """The cumulative cap for one entity and carrier.

        Hot entities raise the cap only through a registered allowance; an
        unregistered entity always gets the default, never a bypass.
        """

        caps = dict(self.default_caps)
        if carrier not in caps:
            raise EntityDiversityError(f"unsupported diversity carrier: {carrier}")
        for row in self.hot_entities:
            if row.entity_ref != entity_ref:
                continue
            raised = row.cap(carrier)
            if raised is not None:
                return raised
        return caps[carrier]

    def top_entity_share(self, counts: Mapping[str, int]) -> float:
        """Share of cumulative objects held by the most-covered top-N entities."""

        total = sum(int(value) for value in counts.values())
        if total <= 0:
            return 0.0
        top = sum(
            value
            for _ref, value in Counter(
                {ref: int(value) for ref, value in counts.items()}
            ).most_common(self.top_entity_count)
        )
        return top / total

    def concentration_exceeded(self, counts: Mapping[str, int]) -> bool:
        """Whether the Top-N share is above the ceiling on a meaningful sample.

        The share carries no information on two sample shapes, so the constraint
        stays dormant on both: too few cumulative objects, and an entity
        population no larger than the Top-N window, where the share is 1.0 by
        construction no matter how the objects are spread.
        """

        total = sum(int(value) for value in counts.values())
        if total < self.minimum_cumulative_objects:
            return False
        if len([ref for ref, value in counts.items() if int(value) > 0]) <= (
            self.top_entity_count
        ):
            return False
        return self.top_entity_share(counts) > self.top_entity_share_ceiling


@dataclass(frozen=True, slots=True)
class DiversityAdmission:
    """Which candidates the diversity constraints admit, and why the rest were not."""

    admitted: tuple[str, ...]
    entity_cap_rejected: tuple[tuple[str, str], ...]
    concentration_rejected: tuple[tuple[str, str], ...]

    def report(self) -> dict[str, Any]:
        return {
            "admittedCount": len(self.admitted),
            "entityCapRejectedCount": len(self.entity_cap_rejected),
            "concentrationRejectedCount": len(self.concentration_rejected),
            "entityCapRejected": [
                {"entityRef": ref, "reason": reason}
                for ref, reason in self.entity_cap_rejected
            ],
            "concentrationRejected": [
                {"entityRef": ref, "reason": reason}
                for ref, reason in self.concentration_rejected
            ],
        }


def load_content_diversity_policy(
    *, policy_path: Path = POLICY_PATH
) -> EntityDiversityPolicy:
    try:
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EntityDiversityError(
            f"content diversity policy is unreadable: {policy_path}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise EntityDiversityError("content diversity policy must be an object")
    assert_valid(
        dict(raw),
        "governance",
        "content_diversity_policy",
        label="content_diversity_policy",
    )
    concentration = raw["entityConcentration"]
    return EntityDiversityPolicy(
        policy_id=str(raw["policyId"]),
        default_caps=tuple(
            (carrier, int(concentration["maxObjectsPerEntity"][carrier]))
            for carrier in CARRIERS
        ),
        top_entity_count=int(concentration["topEntityCount"]),
        top_entity_share_ceiling=float(concentration["topEntityShareCeiling"]),
        minimum_cumulative_objects=int(concentration["minimumCumulativeObjects"]),
        hot_entities=tuple(
            HotEntityAllowance(
                entity_ref=str(row["entityRef"]),
                caps=tuple(
                    (carrier, int(value))
                    for carrier, value in sorted(row["maxObjectsPerEntity"].items())
                ),
                signal=str(row["evidence"]["signal"]),
                observed_at=str(row["evidence"]["observedAt"]),
                reviewer=str(row["evidence"]["reviewer"]),
                justification=str(row["evidence"]["justification"]),
            )
            for row in raw["hotEntities"]
        ),
    )


def admit_diverse_entities(
    candidate_entity_refs: tuple[str, ...],
    *,
    carrier: str,
    cumulative_counts: Mapping[str, int],
    policy: EntityDiversityPolicy | None = None,
) -> DiversityAdmission:
    """Admit candidates in order while both diversity constraints still hold.

    ``cumulative_counts`` is the cross-execution count of already finalized
    objects per entity for this carrier. Admissions are projected into that
    distribution one at a time so the Top-N ceiling is evaluated against the
    catalog the batch would actually produce, not against its starting point.
    """

    resolved = policy or load_content_diversity_policy()
    projected = {str(ref): int(value) for ref, value in cumulative_counts.items()}
    admitted: list[str] = []
    cap_rejected: list[tuple[str, str]] = []
    concentration_rejected: list[tuple[str, str]] = []
    for entity_ref in candidate_entity_refs:
        ref = str(entity_ref).strip()
        if not ref:
            raise EntityDiversityError("diversity candidate entityRef must be non-empty")
        cap = resolved.entity_cap(ref, carrier=carrier)
        current = projected.get(ref, 0)
        if current >= cap:
            cap_rejected.append((ref, f"cumulative {current} reached cap {cap}"))
            continue
        candidate_counts = dict(projected)
        candidate_counts[ref] = current + 1
        # An already-over-ceiling catalog is repaired by covering tail entities,
        # so the ceiling may only reject an admission that fails to improve the
        # share. Rejecting every admission while over the ceiling would deadlock
        # the exact situation the constraint exists to fix.
        if resolved.concentration_exceeded(candidate_counts) and resolved.top_entity_share(
            candidate_counts
        ) >= resolved.top_entity_share(projected):
            concentration_rejected.append(
                (
                    ref,
                    "top-%d share %.3f would not improve on %.3f while above the "
                    "%.2f ceiling"
                    % (
                        resolved.top_entity_count,
                        resolved.top_entity_share(candidate_counts),
                        resolved.top_entity_share(projected),
                        resolved.top_entity_share_ceiling,
                    ),
                )
            )
            continue
        projected = candidate_counts
        admitted.append(ref)
    return DiversityAdmission(
        admitted=tuple(admitted),
        entity_cap_rejected=tuple(cap_rejected),
        concentration_rejected=tuple(concentration_rejected),
    )


__all__ = [
    "CARRIERS",
    "POLICY_PATH",
    "DiversityAdmission",
    "EntityDiversityError",
    "EntityDiversityPolicy",
    "HotEntityAllowance",
    "admit_diverse_entities",
    "load_content_diversity_policy",
]
