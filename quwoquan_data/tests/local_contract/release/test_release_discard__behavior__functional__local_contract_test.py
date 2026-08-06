"""Release discard removes only inactive, disposable release output."""
from __future__ import annotations

import fcntl
import sys
from pathlib import Path

import pytest

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical import discard
from content.release.canonical.acceptance_lease import event_checksum
from content.release.canonical.release_identity_incident import (
    identity_protection_lock_path,
    record_release_identity_incident,
)
from core.io import write_json

RELEASE_ID = "20260725--travel-homepage-coverage--test-region--pilot-001"


def test_release_discard__removes_release_and_matching_environment_evidence__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    release = release_root / RELEASE_ID
    release.mkdir(parents=True)
    output_root = tmp_path
    evidence = output_root / "env/alpha/runs/data-release" / RELEASE_ID
    evidence.mkdir(parents=True)
    unrelated = output_root / "env/alpha/runs/data-release/unrelated-release"
    unrelated.mkdir(parents=True)
    monkeypatch.setattr(discard, "_active_release_processes", lambda _release_id: ())
    original_rmtree = discard.shutil.rmtree
    lock_observed: list[Path] = []

    def _locked_rmtree(path: Path) -> None:
        lock_path = identity_protection_lock_path(output_root=output_root)
        with lock_path.open("a+b") as handle:
            with pytest.raises(BlockingIOError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_observed.append(path)
        original_rmtree(path)

    monkeypatch.setattr(discard.shutil, "rmtree", _locked_rmtree)

    discard.discard_release(
        RELEASE_ID,
        release_root=release_root,
        output_root=output_root,
    )

    assert not release.exists()
    assert not evidence.exists()
    assert unrelated.is_dir()
    assert lock_observed == [release, evidence]


def test_release_discard__rejects_active_release_writer__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    release = release_root / RELEASE_ID
    release.mkdir(parents=True)
    monkeypatch.setattr(
        discard,
        "_active_release_processes",
        lambda _release_id: ("123 python cli.py ship apply --release-id ...",),
    )

    with pytest.raises(RuntimeError, match="active release command"):
        discard.discard_release(RELEASE_ID, release_root=release_root, output_root=tmp_path)

    assert release.is_dir()


def test_release_discard__rejects_identity_incident_source__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    release = release_root / RELEASE_ID
    release.mkdir(parents=True)
    attestations: list[Path] = []
    for name, payload_digest, canonical_merkle in (
        ("old", "sha256:" + "1" * 64, "sha256:" + "2" * 64),
        ("current", "sha256:" + "3" * 64, "sha256:" + "4" * 64),
    ):
        path = tmp_path / "incident-input" / f"{name}.json"
        write_json(
            path,
            {
                "releaseId": RELEASE_ID,
                "payloadSha256": payload_digest,
                "canonicalMerkle": canonical_merkle,
                "executionIds": [
                    "20260805--travel-homepage-adoption--china--pilot-001"
                ],
            },
        )
        attestations.append(path)
    record_release_identity_incident(
        release_id=RELEASE_ID,
        incident_id="release-discard-protection-001",
        original_attestations=attestations,
        recovery_provenances=(),
        output_root=tmp_path,
    )
    monkeypatch.setattr(discard, "_active_release_processes", lambda _release_id: ())

    with pytest.raises(RuntimeError, match="IDENTITY_INCIDENT_PROTECTED"):
        discard.discard_release(
            RELEASE_ID,
            release_root=release_root,
            output_root=tmp_path,
        )

    assert release.is_dir()


def test_release_discard__rejects_reviewed_adoption_source__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    release = release_root / RELEASE_ID
    release.mkdir(parents=True)
    monkeypatch.setattr(
        discard,
        "release_identity_incident_protected_release_ids",
        lambda _output_root: set(),
    )
    monkeypatch.setattr(
        discard,
        "reviewed_closure_adoption_protected_refs",
        lambda _output_root: ({RELEASE_ID}, set()),
    )

    with pytest.raises(RuntimeError, match="ADOPTION_SOURCE_PROTECTED"):
        discard.discard_release(
            RELEASE_ID,
            release_root=release_root,
            output_root=tmp_path,
        )

    assert release.is_dir()


def test_release_discard__fails_closed_for_missing_adoption_ref__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    release = release_root / RELEASE_ID
    release.mkdir(parents=True)
    adoption_root = (
        tmp_path / "data/local/reviewed-closure-adoptions/incomplete-adoption"
    )
    adoption_root.mkdir(parents=True)
    monkeypatch.setattr(discard, "_active_release_processes", lambda _release_id: ())

    with pytest.raises(RuntimeError, match="ADOPTION_EVIDENCE_INVALID"):
        discard.discard_release(
            RELEASE_ID,
            release_root=release_root,
            output_root=tmp_path,
        )

    assert release.is_dir()


def test_release_discard__rejects_passed_readiness_reference__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    release = release_root / RELEASE_ID
    release.mkdir(parents=True)
    readiness = (
        tmp_path
        / "env/gamma/runs/data-release"
        / RELEASE_ID
        / "verify-001/release-readiness.json"
    )
    write_json(
        readiness,
        {
            "schema": "quwoquan_data.environment_release_readiness",
            "releaseId": RELEASE_ID,
            "passed": True,
        },
    )
    monkeypatch.setattr(discard, "_active_release_processes", lambda _release_id: ())

    with pytest.raises(RuntimeError, match="protected by acceptance evidence"):
        discard.discard_release(
            RELEASE_ID,
            release_root=release_root,
            output_root=tmp_path,
        )

    assert release.is_dir()
    assert readiness.is_file()


def test_release_discard__rejects_cross_run_acceptance_lease__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    release = release_root / RELEASE_ID
    release.mkdir(parents=True)
    lease = (
        tmp_path
        / "env/prod/runs/release-acceptance"
        / RELEASE_ID
        / "uat-001/acquire-001/acceptance-lease.json"
    )
    event = {
        "schema": "quwoquan_data.release_acceptance_lease_event",
        "environment": "prod",
        "releaseId": RELEASE_ID,
        "sourceOwner": "qwq_data",
        "manifestDigest": "sha256:" + "a" * 64,
        "leaseId": "uat-001",
        "eventId": "acquire-001",
        "action": "acquire",
        "holder": "stackctl.content-uat",
        "purpose": "user_acceptance",
        "importRunId": "apply-001",
        "verifyRunId": "verify-001",
        "readinessRef": (
            f"env/prod/runs/data-release/{RELEASE_ID}/"
            "verify-001/release-readiness.json"
        ),
        "predecessorEventRef": "",
        "recordedAt": "2026-07-28T00:00:00Z",
    }
    event["verificationChecksum"] = event_checksum(event)
    write_json(lease, event)
    monkeypatch.setattr(discard, "_active_release_processes", lambda _release_id: ())

    with pytest.raises(RuntimeError, match="canonical acceptance revocation"):
        discard.discard_release(
            RELEASE_ID,
            release_root=release_root,
            output_root=tmp_path,
        )

    assert release.is_dir()
    assert lease.is_file()
