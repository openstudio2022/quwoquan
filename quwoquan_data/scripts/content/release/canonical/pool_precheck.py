"""Read-only pool-build precheck for the production handoff gate.

The precheck answers the one question a production session cannot otherwise
answer without writing release artifacts: would ``release pool-build`` actually
select the objects that are already in the canonical pool? It reuses the exact
judgment chain of ``prepare_pool_release`` -- candidate discovery, delivery
issues, version de-duplication, ``candidate_closure``, cross-post media identity
and slice conflicts, the reselection loop, the standalone entity closure and the
milestone budget -- and writes nothing.

Two stages are reported separately on purpose. The milestone selector raises
``DATA.POOL.MILESTONE_SHORTFALL`` before any object reaches
``candidate_closure``, and the counts carried by that error are the optimistic
pre-closure counts. So a carrier-agnostic stage runs the full chain first to
establish which objects are genuinely selectable, and the milestone stage then
decides whether that set satisfies the milestone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from content.release.canonical.aggregate_release_pool import (
    _exclusion,
    _selection_exclusion,
    pool_entity_refs,
    pool_post_refs,
    prepare_pool_release,
)
from content.release.canonical.aggregate_release_pool_closure import (
    candidate_closure,
)
from content.release.canonical.content_pool_handoff import (
    project_content_pool_handoff,
)
from content.release.canonical.environment_release_selection import (
    MILESTONE_TARGETS,
    select_all_publishable_release_posts,
)
from content.release.canonical.environment_release_support import (
    pool_error_code,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)

HOMEPAGE_CARRIER = "homepage"

_PRECHECK_FAILURES = (ObjectTransactionError, OSError, TypeError, ValueError)


@dataclass(frozen=True, slots=True)
class PrecheckBlocker:
    stage: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class CarrierGap:
    carrier: str
    target: int
    selectable: int
    gap: int


@dataclass(frozen=True, slots=True)
class PoolPrecheckReport:
    """A verdict, never an absence.

    ``status`` is ``passed`` only when the milestone stage selected a release
    under the real judgment chain. A pool that cannot satisfy the milestone is
    reported as ``blocked`` with typed blockers, which is a present value rather
    than a failure of the precheck itself.
    """

    status: str
    milestone: str
    release_mode: str
    pool_digest: str
    selectable_post_refs: tuple[str, ...]
    carrier_counts: Mapping[str, int]
    carrier_gaps: tuple[CarrierGap, ...]
    homepage_observation: Mapping[str, int]
    excluded: tuple[Mapping[str, str], ...]
    excluded_by_code: Mapping[str, int]
    exclusion_source: str
    blockers: tuple[PrecheckBlocker, ...]
    milestone_post_refs: tuple[str, ...]

    def as_document(self, *, details: bool) -> dict[str, object]:
        document: dict[str, object] = {
            "status": self.status,
            "milestone": self.milestone,
            "releaseMode": self.release_mode,
            "poolDigest": self.pool_digest,
            "selectableCounts": dict(self.carrier_counts),
            "carrierGaps": [
                {
                    "carrier": gap.carrier,
                    "target": gap.target,
                    "selectable": gap.selectable,
                    "gap": gap.gap,
                }
                for gap in self.carrier_gaps
            ],
            "homepageObservation": dict(self.homepage_observation),
            "excludedByCode": dict(self.excluded_by_code),
            "exclusionSource": self.exclusion_source,
            "blockers": [
                {
                    "stage": blocker.stage,
                    "code": blocker.code,
                    "message": blocker.message,
                }
                for blocker in self.blockers
            ],
        }
        if details:
            document["selectablePostRefs"] = list(self.selectable_post_refs)
            document["milestonePostRefs"] = list(self.milestone_post_refs)
            document["excluded"] = [dict(row) for row in self.excluded]
        return document


def milestone_carriers(milestone: str) -> tuple[str, ...]:
    """Derive the content carriers from the milestone policy itself."""

    targets = MILESTONE_TARGETS.get(str(milestone).strip())
    if targets is None:
        raise ObjectTransactionError(
            f"DATA.POOL.MILESTONE_INVALID: {str(milestone).strip()!r}"
        )
    return tuple(
        carrier for carrier in sorted(targets) if carrier != HOMEPAGE_CARRIER
    )


def _replayed_exclusions(
    *,
    publish_root: Path,
    release_class: str,
) -> tuple[Mapping[str, str], ...]:
    """Recover the per-object reasons when the full chain rejects everything.

    ``prepare_pool_release`` raises ``DATA.RELEASE.NO_ELIGIBLE_CONTENT`` carrying
    only a count, which is exactly the situation where a production session most
    needs the reasons. Both stages that produced those reasons are replayed with
    the same functions the chain itself uses: the selector reports its own
    exclusions instead of raising, and ``candidate_closure`` is re-run per object
    to attribute the closure-stage rejections that the reselection loop folded
    into the single aggregate error.
    """

    try:
        selection = select_all_publishable_release_posts(
            publish_root=publish_root,
            post_refs=pool_post_refs(publish_root),
            release_class=release_class,
            strict_admission=True,
        )
    except _PRECHECK_FAILURES:
        return ()
    rows: list[Mapping[str, str]] = [
        _selection_exclusion(row) for row in selection.excluded
    ]
    for post_ref in selection.post_refs:
        try:
            candidate_closure(
                publish_root,
                post_ref=post_ref,
                release_mode=selection.release_mode,
            )
        except _PRECHECK_FAILURES as exc:
            rows.append(_exclusion(post_ref, exc))
    return tuple(rows)


def _homepage_observation(
    *,
    publish_root: Path,
    post_refs: Sequence[str],
    release_mode: str,
    homepage_target: int,
) -> dict[str, int]:
    """Report the homepage budget inputs without re-deciding the budget.

    ``prepare_pool_release`` owns the verdict. This is the same closure and the
    same admission predicate, surfaced early so a production session can see a
    budget collision coming before it produces a hundred objects.
    """

    required_entity_refs: set[str] = set()
    for post_ref in post_refs:
        closure = candidate_closure(
            publish_root,
            post_ref=post_ref,
            release_mode=release_mode,
        )
        required_entity_refs.update(closure[0])
    admitted = 0
    for entity_ref in pool_entity_refs(publish_root):
        handoff = project_content_pool_handoff(
            publish_root=publish_root,
            object_type=HOMEPAGE_CARRIER,
            object_ref=entity_ref,
        )
        if handoff is not None:
            admitted += 1
    return {
        "homepageTarget": homepage_target,
        "admittedHomepageObjects": admitted,
        "entityRefsRequiredBySelectablePosts": len(required_entity_refs),
    }


def precheck_pool_release(
    *,
    publish_root: Path,
    milestone: str,
    release_class: str = "research",
) -> PoolPrecheckReport:
    """Decide whether pool-build would select a release, writing nothing."""

    milestone_name = str(milestone).strip()
    targets = MILESTONE_TARGETS.get(milestone_name)
    if targets is None:
        raise ObjectTransactionError(
            f"DATA.POOL.MILESTONE_INVALID: {milestone_name!r}"
        )
    carriers = milestone_carriers(milestone_name)

    blockers: list[PrecheckBlocker] = []
    release_mode = ""
    pool_digest = ""
    selectable_post_refs: tuple[str, ...] = ()
    carrier_counts: dict[str, int] = {carrier: 0 for carrier in carriers}
    excluded: tuple[Mapping[str, str], ...] = ()
    exclusion_source = "chain"
    homepage_observation: dict[str, int] = {
        "homepageTarget": int(targets[HOMEPAGE_CARRIER]),
    }

    try:
        preparation = prepare_pool_release(
            publish_root=publish_root,
            all_publishable=True,
            release_class=release_class,
        )
    except _PRECHECK_FAILURES as exc:
        blockers.append(
            PrecheckBlocker(
                stage="selectable",
                code=pool_error_code(exc),
                message=str(exc),
            )
        )
        excluded = _replayed_exclusions(
            publish_root=publish_root,
            release_class=release_class,
        )
        exclusion_source = "replayed"
    else:
        selection = preparation.environment_selection
        release_mode = selection.release_mode
        pool_digest = selection.pool_digest
        selectable_post_refs = tuple(sorted(selection.post_refs))
        carrier_counts = {
            carrier: sum(
                candidate.content_type == carrier
                for candidate in selection.candidates
            )
            for carrier in carriers
        }
        excluded = tuple(dict(row) for row in preparation.excluded)
        try:
            homepage_observation = _homepage_observation(
                publish_root=publish_root,
                post_refs=selectable_post_refs,
                release_mode=release_mode,
                homepage_target=int(targets[HOMEPAGE_CARRIER]),
            )
        except _PRECHECK_FAILURES as exc:
            blockers.append(
                PrecheckBlocker(
                    stage="homepage",
                    code=pool_error_code(exc),
                    message=str(exc),
                )
            )

    milestone_post_refs: tuple[str, ...] = ()
    try:
        milestone_preparation = prepare_pool_release(
            publish_root=publish_root,
            milestone=milestone_name,
            release_class="research",
        )
    except _PRECHECK_FAILURES as exc:
        blockers.append(
            PrecheckBlocker(
                stage="milestone",
                code=pool_error_code(exc),
                message=str(exc),
            )
        )
    else:
        milestone_post_refs = tuple(
            sorted(milestone_preparation.environment_selection.post_refs)
        )

    homepage_selectable = int(
        homepage_observation.get("admittedHomepageObjects", 0)
    )
    carrier_gaps = tuple(
        CarrierGap(
            carrier=carrier,
            target=int(targets[carrier]),
            selectable=(
                homepage_selectable
                if carrier == HOMEPAGE_CARRIER
                else carrier_counts.get(carrier, 0)
            ),
            gap=max(
                int(targets[carrier])
                - (
                    homepage_selectable
                    if carrier == HOMEPAGE_CARRIER
                    else carrier_counts.get(carrier, 0)
                ),
                0,
            ),
        )
        for carrier in sorted(targets)
    )
    excluded_by_code: dict[str, int] = {}
    for row in excluded:
        code = str(row.get("code") or "")
        excluded_by_code[code] = excluded_by_code.get(code, 0) + 1

    return PoolPrecheckReport(
        status="blocked" if blockers else "passed",
        milestone=milestone_name,
        release_mode=release_mode,
        pool_digest=pool_digest,
        selectable_post_refs=selectable_post_refs,
        carrier_counts=carrier_counts,
        carrier_gaps=carrier_gaps,
        homepage_observation=homepage_observation,
        excluded=excluded,
        excluded_by_code=dict(sorted(excluded_by_code.items())),
        exclusion_source=exclusion_source,
        blockers=tuple(blockers),
        milestone_post_refs=milestone_post_refs,
    )


__all__ = [
    "CarrierGap",
    "PoolPrecheckReport",
    "PrecheckBlocker",
    "milestone_carriers",
    "precheck_pool_release",
]
