"""Import-count closure for release readiness."""

from __future__ import annotations

from pathlib import Path

from content.release.environment.release_readiness_closure import (
    Any,
    Mapping,
    ReleaseReadinessClosureError,
)


def _assert_import_counts(
    *,
    import_report: Mapping[str, Any],
    creator_report: Mapping[str, Any],
    desired: Mapping[str, list[str]],
) -> None:
    content_counts = import_report.get("counts")
    creator_counts = creator_report.get("counts")
    if not isinstance(content_counts, Mapping) or (
        content_counts.get("postsLoaded") != len(desired["posts"])
        or content_counts.get("entitiesLoaded") != len(desired["entities"])
    ):
        raise ReleaseReadinessClosureError(
            "content import counts drift from immutable desiredRefs"
        )
    if not isinstance(creator_counts, Mapping) or creator_counts.get(
        "creatorsLoaded"
    ) != len(desired["creators"]):
        raise ReleaseReadinessClosureError(
            "creator import counts drift from immutable desiredRefs"
        )


def _object(path: Path, *, label: str) -> dict[str, Any]:
    from content.release.environment.release_readiness_closure import (
        Mapping,
        ReleaseReadinessClosureError,
        read_json,
    )

    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise ReleaseReadinessClosureError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, Mapping):
        raise ReleaseReadinessClosureError(f"{label} must be an object: {path}")
    return dict(value)


def _normalized_ref(value: object, *, kind: str) -> str:
    from content.release.environment.release_readiness_closure import (
        ReleaseReadinessClosureError,
        _text,
    )

    result = _text(value, label=f"{kind} ref").strip("/")
    singular = {
        "creators": "creator",
        "entities": "entity",
        "posts": "post",
        "tags": "tag",
    }.get(kind)
    if singular is None:
        raise ReleaseReadinessClosureError(f"unsupported release object kind: {kind}")
    prefixes = (f"{kind}/", f"{singular}/")
    for prefix in prefixes:
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break
    if not result or ".." in Path(result).parts:
        raise ReleaseReadinessClosureError(f"unsafe {kind} ref: {value}")
    return result
