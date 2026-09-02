"""Shared identities, roots, digests, and errors for campaign release selection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.execution.source_pool.external_inputs import payload_digest
from content.release.canonical.campaign_submission_reader import campaign_root
from content.release.canonical.object_transaction_contract import _safe_id
from core import paths
from core.io import read_json

PUBLISH_BINDING_FIELDS = (
    "executionPublishRef",
    "executionPublishSha256",
    "campaignRunId",
    "campaignGeneration",
    "campaignFencingToken",
)
PUBLISH_BINDING_CONTRACT_REQUEST = (
    "content_campaign_lane_receipt must freeze the tasks-root canonical "
    "executionPublishRef + executionPublishSha256 and the authoring "
    "campaignRunId/campaignGeneration/campaignFencingToken when its writer "
    "reads publish_ref.json and current controller state"
)


class CampaignReleaseError(RuntimeError):
    """Typed fail-closed campaign-to-release selection error."""

    def __init__(
        self, code: str, detail: str, *, evidence_path: Path | None = None
    ) -> None:
        suffix = f"; evidence={evidence_path}" if evidence_path is not None else ""
        super().__init__(f"GATE_BLOCK {code}: {detail}{suffix}")
        self.code = code
        self.evidence_path = evidence_path


@dataclass(frozen=True, slots=True)
class CampaignReleaseRoots:
    """The one canonical output topology consumed by campaign selection."""

    output_root: Path
    campaigns_root: Path
    tasks_root: Path
    publish_root: Path
    release_root: Path

    @classmethod
    def defaults(cls) -> CampaignReleaseRoots:
        output_root = paths.OUTPUT_ROOT.resolve()
        return cls(
            output_root=output_root,
            campaigns_root=(
                output_root / "data/local/workspace/content-campaign-submissions"
            ).resolve(),
            tasks_root=(output_root / "data/tasks").resolve(),
            publish_root=paths.PUBLISH_ROOT.resolve(),
            release_root=(output_root / "data/releases").resolve(),
        )

    def validated(self) -> CampaignReleaseRoots:
        normalized = CampaignReleaseRoots(
            output_root=self.output_root.resolve(),
            campaigns_root=self.campaigns_root.resolve(),
            tasks_root=self.tasks_root.resolve(),
            publish_root=self.publish_root.resolve(),
            release_root=self.release_root.resolve(),
        )
        expected = {
            "campaigns_root": (
                normalized.output_root
                / "data/local/workspace/content-campaign-submissions"
            ).resolve(),
            "tasks_root": (normalized.output_root / "data/tasks").resolve(),
            "release_root": (normalized.output_root / "data/releases").resolve(),
        }
        drift = [
            name
            for name, value in expected.items()
            if getattr(normalized, name) != value
        ]
        if drift:
            raise CampaignReleaseError(
                "DATA.CAMPAIGN.RELEASE_ROOT_DRIFT",
                "canonical runtime roots drift: " + ", ".join(drift),
            )
        return normalized


def selection_attestation_path(
    root_execution_id: str,
    release_id: str,
    *,
    roots: CampaignReleaseRoots,
) -> Path:
    return (
        campaign_root(root_execution_id, root=roots.campaigns_root)
        / "release_selections"
        / f"{_safe_id(release_id, label='releaseId')}.json"
    )


def typed_error(
    code: str, detail: str, *, evidence: Path | None = None
) -> CampaignReleaseError:
    return CampaignReleaseError(
        f"DATA.CAMPAIGN.RELEASE_{code}", detail, evidence_path=evidence
    )


def canonical_digest(value: object) -> str:
    return payload_digest(value)


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def read_regular(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise typed_error(
            "EVIDENCE_MISSING", f"{label} must be one regular file", evidence=path
        )
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise typed_error(
            "EVIDENCE_INVALID", f"{label} is unreadable", evidence=path
        ) from exc
    if not isinstance(payload, dict):
        raise typed_error(
            "EVIDENCE_INVALID", f"{label} must be an object", evidence=path
        )
    return payload


def output_ref(path: Path, *, roots: CampaignReleaseRoots, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise typed_error(
            "EVIDENCE_MISSING", f"{label} must be one regular file", evidence=path
        )
    try:
        return path.resolve().relative_to(roots.output_root).as_posix()
    except ValueError as exc:
        raise typed_error(
            "ROOT_DRIFT", f"{label} is outside output root", evidence=path
        ) from exc


__all__ = [
    "PUBLISH_BINDING_CONTRACT_REQUEST",
    "PUBLISH_BINDING_FIELDS",
    "CampaignReleaseError",
    "CampaignReleaseRoots",
    "canonical_digest",
    "file_digest",
    "output_ref",
    "read_regular",
    "selection_attestation_path",
    "typed_error",
]
