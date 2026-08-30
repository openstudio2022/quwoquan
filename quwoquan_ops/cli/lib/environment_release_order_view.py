"""Pure projection of environment release order from acceptance facts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.environment_acceptance_fact import (
    ENVIRONMENTS,
    PREDECESSOR,
    EnvironmentAcceptanceFactError,
    load_environment_acceptance_fact,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "environments"
    / "evidence"
    / "environment_release_order_view.schema.json"
)
SCHEMA = "quwoquan_ops.environment_release_order_view"
AVAILABLE_ACTIONS = frozenset({"create_acceptance"})
_VIEW_KEYS = frozenset({"schema", "releaseId", "derivedAt", "environments"})
_ENVIRONMENT_KEYS = frozenset(
    {
        "environment",
        "state",
        "acceptanceRef",
        "acceptanceDigest",
        "predecessorSatisfied",
        "availableActions",
    }
)


class EnvironmentReleaseOrderViewError(ValueError):
    """A release-order projection input or output is malformed."""


def _timestamp(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise EnvironmentReleaseOrderViewError("derivedAt must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EnvironmentReleaseOrderViewError("derivedAt must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise EnvironmentReleaseOrderViewError("derivedAt must include a timezone")


def _explicit_refs(value: Mapping[str, str | None]) -> dict[str, str | None]:
    if not isinstance(value, Mapping):
        raise EnvironmentReleaseOrderViewError("acceptance_refs must be a mapping")
    unknown = set(value) - set(ENVIRONMENTS)
    if unknown:
        raise EnvironmentReleaseOrderViewError(
            f"acceptance_refs contains unknown environments: {sorted(unknown)}"
        )
    refs: dict[str, str | None] = {}
    for environment in ENVIRONMENTS:
        ref = value.get(environment)
        if ref is not None and (not isinstance(ref, str) or not ref.strip()):
            raise EnvironmentReleaseOrderViewError(
                f"acceptance_refs[{environment!r}] must be a non-empty ref or null"
            )
        refs[environment] = ref
    return refs


def derive_environment_release_order_view(
    *,
    release_id: str,
    derived_at: str,
    artifact_root: Path,
    acceptance_refs: Mapping[str, str | None],
) -> dict[str, Any]:
    """Recompute the view directly from explicitly selected fact bytes.

    Missing, unreadable, malformed, or cross-release facts project as
    ``no_acceptance``.  No failure document is persisted or promoted to a
    second state fact.
    """

    if not isinstance(release_id, str) or not release_id.strip():
        raise EnvironmentReleaseOrderViewError("release_id must be non-empty")
    _timestamp(derived_at)
    refs = _explicit_refs(acceptance_refs)
    loaded: dict[str, tuple[dict[str, Any], str, str] | None] = {}
    for environment in ENVIRONMENTS:
        ref = refs[environment]
        if ref is None:
            loaded[environment] = None
            continue
        try:
            fact, digest = load_environment_acceptance_fact(
                ref,
                evidence_root=artifact_root,
                verify_references=False,
            )
        except (EnvironmentAcceptanceFactError, OSError, TypeError, ValueError):
            loaded[environment] = None
            continue
        if (
            fact.get("environment") != environment
            or fact.get("releaseId") != release_id
        ):
            loaded[environment] = None
            continue
        loaded[environment] = (fact, ref, digest)

    rows: list[dict[str, Any]] = []
    chain_satisfied: dict[str, bool] = {}
    for environment in ENVIRONMENTS:
        selected = loaded[environment]
        predecessor = PREDECESSOR[environment]
        if predecessor is None:
            predecessor_satisfied = True
        else:
            previous = loaded[predecessor]
            predecessor_satisfied = bool(
                previous is not None and chain_satisfied.get(predecessor) is True
            )
            if predecessor_satisfied and selected is not None:
                previous_fact, previous_ref, previous_digest = previous  # type: ignore[misc]
                current_predecessor = selected[0].get("predecessorAcceptance")
                predecessor_satisfied = bool(
                    isinstance(current_predecessor, Mapping)
                    and current_predecessor.get("environment") == predecessor
                    and current_predecessor.get("factId") == previous_fact.get("factId")
                    and current_predecessor.get("ref") == previous_ref
                    and current_predecessor.get("digest") == previous_digest
                    and previous_fact.get("releaseId") == release_id
                )
        accepted = selected is not None and predecessor_satisfied
        chain_satisfied[environment] = accepted
        rows.append(
            {
                "environment": environment,
                "state": "accepted" if accepted else "no_acceptance",
                "acceptanceRef": selected[1] if accepted else None,
                "acceptanceDigest": selected[2] if accepted else None,
                "predecessorSatisfied": predecessor_satisfied,
                "availableActions": (
                    []
                    if accepted or not predecessor_satisfied
                    else ["create_acceptance"]
                ),
            }
        )
    return validate_environment_release_order_view(
        {
            "schema": SCHEMA,
            "releaseId": release_id,
            "derivedAt": derived_at,
            "environments": rows,
        }
    )


def validate_environment_release_order_view(payload: object) -> dict[str, Any]:
    """Validate the finite projection vocabulary and deterministic order."""

    if not isinstance(payload, dict) or set(payload) != _VIEW_KEYS:
        raise EnvironmentReleaseOrderViewError("release order view fields mismatch")
    if payload.get("schema") != SCHEMA:
        raise EnvironmentReleaseOrderViewError("release order view schema mismatch")
    if not isinstance(payload.get("releaseId"), str) or not payload["releaseId"]:
        raise EnvironmentReleaseOrderViewError("releaseId must be non-empty")
    _timestamp(payload.get("derivedAt"))
    rows = payload.get("environments")
    if not isinstance(rows, list) or len(rows) != len(ENVIRONMENTS):
        raise EnvironmentReleaseOrderViewError("release order view must contain four rows")
    for expected_environment, row in zip(ENVIRONMENTS, rows, strict=True):
        if not isinstance(row, dict) or set(row) != _ENVIRONMENT_KEYS:
            raise EnvironmentReleaseOrderViewError("release order environment fields mismatch")
        if row.get("environment") != expected_environment:
            raise EnvironmentReleaseOrderViewError("release order environment order drifted")
        state = row.get("state")
        if state not in {"no_acceptance", "accepted"}:
            raise EnvironmentReleaseOrderViewError("release order state is unknown")
        ref = row.get("acceptanceRef")
        digest = row.get("acceptanceDigest")
        if state == "accepted":
            if (
                not isinstance(ref, str)
                or not ref
                or not isinstance(digest, str)
                or not digest.startswith("sha256:")
                or len(digest) != 71
                or any(character not in "0123456789abcdef" for character in digest[7:])
            ):
                raise EnvironmentReleaseOrderViewError("accepted row lacks exact acceptance")
        elif ref is not None or digest is not None:
            raise EnvironmentReleaseOrderViewError("no_acceptance row must not bind a fact")
        if not isinstance(row.get("predecessorSatisfied"), bool):
            raise EnvironmentReleaseOrderViewError("predecessorSatisfied must be boolean")
        actions = row.get("availableActions")
        if (
            not isinstance(actions, list)
            or len(actions) != len(set(actions))
            or not set(actions).issubset(AVAILABLE_ACTIONS)
        ):
            raise EnvironmentReleaseOrderViewError("availableActions is outside the closed set")
    return payload


derive_release_order_view = derive_environment_release_order_view


__all__ = [
    "AVAILABLE_ACTIONS",
    "SCHEMA",
    "SCHEMA_PATH",
    "EnvironmentReleaseOrderViewError",
    "derive_environment_release_order_view",
    "derive_release_order_view",
    "validate_environment_release_order_view",
]
