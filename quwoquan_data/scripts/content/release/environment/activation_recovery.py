"""Recover a failed non-Prod content activation through formal release replay."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from core.io import read_json


class ContentDeliveryRecoveryError(RuntimeError):
    """No verified previous release can be safely replayed."""


@dataclass(frozen=True, slots=True)
class PreviousVerifiedRelease:
    release_id: str
    manifest_digest: str
    verify_run_id: str
    readiness_path: Path


def _previous_active(import_report: Mapping[str, object]) -> tuple[str, str]:
    events = import_report.get("auditEvents")
    if not isinstance(events, list):
        return "", ""
    matches = [
        str(event).split("|", 2)
        for event in events
        if str(event).startswith("PreviousDataRelease|")
    ]
    if len(matches) != 1 or len(matches[0]) != 3:
        return "", ""
    return matches[0][1].strip(), matches[0][2].strip()


def previous_verified_release(
    *,
    output_root: Path,
    environment: str,
    import_report_path: Path,
) -> PreviousVerifiedRelease | None:
    """Resolve the previous active pointer only when a matching verify passed."""

    report = read_json(import_report_path)
    release_id, manifest_digest = _previous_active(report)
    if not release_id or not manifest_digest:
        return None
    readiness_root = (
        output_root
        / "env"
        / environment
        / "runs"
        / "data-release"
        / release_id
    )
    matches: list[tuple[str, Path, Mapping[str, object]]] = []
    for path in sorted(readiness_root.glob("*/release-readiness.json")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            readiness = read_json(path)
        except (OSError, TypeError, ValueError):
            continue
        if (
            readiness.get("schema")
            == "quwoquan_data.environment_release_readiness"
            and readiness.get("environment") == environment
            and readiness.get("releaseId") == release_id
            and readiness.get("manifestDigest") == manifest_digest
            and readiness.get("passed") is True
        ):
            matches.append(
                (
                    str(readiness.get("verifiedAt") or ""),
                    path,
                    readiness,
                )
            )
    if not matches:
        return None
    _verified_at, readiness_path, readiness = max(
        matches,
        key=lambda row: (row[0], row[1].as_posix()),
    )
    verify_run_id = str(readiness.get("verifyRunId") or readiness_path.parent.name)
    return PreviousVerifiedRelease(
        release_id=release_id,
        manifest_digest=manifest_digest,
        verify_run_id=verify_run_id,
        readiness_path=readiness_path,
    )


def restore_after_delivery_failure(
    *,
    output_root: Path,
    environment: str,
    failed_release_id: str,
    import_report_path: Path,
    replay_previous: Callable[[PreviousVerifiedRelease], None],
) -> PreviousVerifiedRelease:
    """Replay the verified previous release through the formal importer path."""

    if environment not in {"alpha", "beta", "gamma"}:
        raise ContentDeliveryRecoveryError(
            "DATA.DELIVERY_RESTORE_UNAVAILABLE: automatic restore is non-Prod only"
        )
    previous = previous_verified_release(
        output_root=output_root,
        environment=environment,
        import_report_path=import_report_path,
    )
    if previous is None or previous.release_id == failed_release_id:
        raise ContentDeliveryRecoveryError(
            "DATA.DELIVERY_RESTORE_UNAVAILABLE: no previous verified release; "
            "candidate activation must remain fail-closed"
        )
    replay_previous(previous)
    return previous


__all__ = [
    "ContentDeliveryRecoveryError",
    "PreviousVerifiedRelease",
    "previous_verified_release",
    "restore_after_delivery_failure",
]
