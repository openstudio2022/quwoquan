"""Shared object-level failure isolation for fresh supported-API image work."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar


_T = TypeVar("_T")


def typed_image_exclusion(
    asset_id: str,
    exc: BaseException,
    *,
    default_code: str,
) -> dict[str, str]:
    """Project one object-local failure without leaking it into sibling work."""
    code = getattr(exc, "code", "")
    detail = getattr(exc, "detail", "")
    if not isinstance(code, str) or not code:
        code = default_code
    if not isinstance(detail, str) or not detail:
        detail = f"{type(exc).__name__} while processing exact image asset"
    exclusion = {
        "assetId": asset_id,
        "failureCode": code,
        "failure": detail,
    }
    evidence_ref = getattr(exc, "evidence_ref", "")
    evidence_sha256 = getattr(exc, "evidence_sha256", "")
    if isinstance(evidence_ref, str) and evidence_ref:
        exclusion["evidenceRef"] = evidence_ref
    if isinstance(evidence_sha256, str) and evidence_sha256:
        exclusion["evidenceSha256"] = evidence_sha256
    return exclusion


def run_isolated_image_objects(
    objects: Sequence[tuple[str, _T]],
    *,
    worker: Callable[[str, _T], Mapping[str, Any]],
    default_failure_code: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Start all object work and retain successes when one business object fails."""
    if not objects:
        return [], []
    completed: dict[str, dict[str, Any]] = {}
    exclusions: list[dict[str, str]] = []
    fatal: BaseException | None = None
    with ThreadPoolExecutor(
        max_workers=len(objects),
        thread_name_prefix="professional-image",
    ) as executor:
        futures = [
            (asset_id, executor.submit(worker, asset_id, value))
            for asset_id, value in objects
        ]
        for asset_id, future in futures:
            try:
                completed[asset_id] = dict(future.result())
            except Exception as exc:  # noqa: BLE001 - one image object is isolated.
                if bool(getattr(exc, "batch_fatal", False)):
                    fatal = fatal or exc
                else:
                    exclusions.append(
                        typed_image_exclusion(
                            asset_id,
                            exc,
                            default_code=default_failure_code,
                        )
                    )
    if fatal is not None:
        raise fatal
    return (
        [completed[asset_id] for asset_id, _value in objects if asset_id in completed],
        exclusions,
    )


def image_batch_result(
    *,
    schema: str,
    execution_id: str,
    requested_ids: Sequence[str],
    results: Sequence[Mapping[str, Any]],
    exclusions: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    completed_count = len(results)
    status = (
        "ready"
        if completed_count == len(requested_ids) and not exclusions
        else ("partial" if completed_count else "blocked")
    )
    return {
        "schema": schema,
        "executionId": execution_id,
        "status": status,
        "requestedCount": len(requested_ids),
        "completedCount": completed_count,
        "excludedCount": len(exclusions),
        "results": [dict(row) for row in results],
        "exclusions": [dict(row) for row in exclusions],
    }


__all__ = [
    "image_batch_result",
    "run_isolated_image_objects",
    "typed_image_exclusion",
]
