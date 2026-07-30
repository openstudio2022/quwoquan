# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
"""Acceptance protection is a Data-owned append-only acquire/revoke event log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical import acceptance_lease, discard  # noqa: E402
from content.release.environment.ship_dispatch import dispatch_ship  # noqa: E402
from core.control_types import ReleaseRunKind  # noqa: E402

RELEASE_ID = "20260728--android-homepage--pilot-002"
RELEASE_B = "20260728--android-homepage--pilot-003"
DIGEST = "sha256:" + "a" * 64


def test_acceptance_lease__acquire_revoke_are_append_only_and_derived__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        acceptance_lease,
        "_readiness_binding",
        lambda **_kwargs: (
            f"env/gamma/runs/data-release/{RELEASE_ID}/verify-001/release-readiness.json",
            DIGEST,
        ),
    )
    acquire, acquire_path = acceptance_lease.acquire_acceptance_lease(
        environment="gamma",
        release_id=RELEASE_ID,
        import_run_id="apply-001",
        verify_run_id="verify-001",
        lease_id="android-uat-001",
        event_id="acquire-001",
        release_root=tmp_path / "releases",
        output_root=tmp_path,
    )
    assert acceptance_lease.validate_lease_event(
        acquire,
        path=acquire_path,
        output_root=tmp_path,
    ) == []
    assert discard._acceptance_protection_refs(
        output_root=tmp_path,
        release_id=RELEASE_ID,
        evidence_roots=(),
    ) == (acquire_path,)

    acquire_ref = acquire_path.relative_to(tmp_path).as_posix()
    revoke, revoke_path = acceptance_lease.revoke_acceptance_lease(
        environment="gamma",
        release_id=RELEASE_ID,
        lease_id="android-uat-001",
        acquire_event_ref=acquire_ref,
        event_id="revoke-001",
        output_root=tmp_path,
    )

    assert acquire_path.is_file()
    assert revoke_path.is_file()
    assert revoke["predecessorEventRef"] == acquire_ref
    assert discard._acceptance_protection_refs(
        output_root=tmp_path,
        release_id=RELEASE_ID,
        evidence_roots=(),
    ) == ()
    readiness_root = tmp_path / "env/gamma/runs/data-release" / RELEASE_ID
    readiness = readiness_root / "verify-001/release-readiness.json"
    readiness.parent.mkdir(parents=True)
    readiness.write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.environment_release_readiness",
                "releaseId": RELEASE_ID,
                "passed": True,
            }
        ),
        encoding="utf-8",
    )
    assert discard._acceptance_protection_refs(
        output_root=tmp_path,
        release_id=RELEASE_ID,
        evidence_roots=(readiness_root,),
    ) == (readiness,)
    with pytest.raises(acceptance_lease.AcceptanceLeaseError, match="already revoked"):
        acceptance_lease.revoke_acceptance_lease(
            environment="gamma",
            release_id=RELEASE_ID,
            lease_id="android-uat-001",
            acquire_event_ref=acquire_ref,
            event_id="revoke-002",
            output_root=tmp_path,
        )


def test_acceptance_lease__checksum_drift_fails_closed__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        acceptance_lease,
        "_readiness_binding",
        lambda **_kwargs: (
            f"env/gamma/runs/data-release/{RELEASE_ID}/verify-001/release-readiness.json",
            DIGEST,
        ),
    )
    acquire, path = acceptance_lease.acquire_acceptance_lease(
        environment="gamma",
        release_id=RELEASE_ID,
        import_run_id="apply-001",
        verify_run_id="verify-001",
        lease_id="android-uat-002",
        event_id="acquire-001",
        release_root=tmp_path / "releases",
        output_root=tmp_path,
    )
    acquire["manifestDigest"] = "sha256:" + "0" * 64

    assert any(
        "verificationChecksum drift" in issue
        for issue in acceptance_lease.validate_lease_event(
            acquire,
            path=path,
            output_root=tmp_path,
        )
    )


def test_acceptance_lease__single_active_lease_per_environment__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        acceptance_lease,
        "_readiness_binding",
        lambda **kwargs: (
            "env/"
            f"{kwargs['environment']}/runs/data-release/{kwargs['release_id']}/"
            f"{kwargs['verify_run_id']}/release-readiness.json",
            DIGEST,
        ),
    )
    acquire, acquire_path = acceptance_lease.acquire_acceptance_lease(
        environment="gamma",
        release_id=RELEASE_ID,
        import_run_id="apply-001",
        verify_run_id="verify-001",
        lease_id="android-uat-active",
        event_id="acquire-001",
        release_root=tmp_path / "data/releases",
        output_root=tmp_path,
    )

    with pytest.raises(
        acceptance_lease.AcceptanceLeaseError,
        match="already has an active acceptance lease",
    ):
        acceptance_lease.acquire_acceptance_lease(
            environment="gamma",
            release_id=RELEASE_B,
            import_run_id="apply-001",
            verify_run_id="verify-001",
            lease_id="android-uat-competing",
            event_id="acquire-002",
            release_root=tmp_path / "data/releases",
            output_root=tmp_path,
        )

    assert acceptance_lease.active_acceptance_lease_refs(
        output_root=tmp_path,
        environment="gamma",
    ) == (acquire_path,)
    assert acceptance_lease.active_acceptance_lease_refs(
        output_root=tmp_path,
        release_id=RELEASE_ID,
        environment="gamma",
    ) == (acquire_path,)
    beta_acquire, beta_path = acceptance_lease.acquire_acceptance_lease(
        environment="beta",
        release_id=RELEASE_B,
        import_run_id="apply-001",
        verify_run_id="verify-001",
        lease_id="android-uat-beta",
        event_id="acquire-beta-001",
        release_root=tmp_path / "data/releases",
        output_root=tmp_path,
    )
    assert beta_acquire["environment"] == "beta"
    assert acceptance_lease.active_acceptance_lease_refs(
        output_root=tmp_path,
        environment="beta",
    ) == (beta_path,)
    acquire_ref = acquire_path.relative_to(tmp_path).as_posix()
    acceptance_lease.revoke_acceptance_lease(
        environment="gamma",
        release_id=RELEASE_ID,
        lease_id=str(acquire["leaseId"]),
        acquire_event_ref=acquire_ref,
        event_id="revoke-001",
        output_root=tmp_path,
    )
    assert acceptance_lease.active_acceptance_lease_refs(
        output_root=tmp_path,
        release_id=RELEASE_ID,
        environment="gamma",
    ) == ()


def test_acceptance_lease__readiness_ref_identity_fails_closed__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        acceptance_lease,
        "_readiness_binding",
        lambda **_kwargs: (
            f"env/gamma/runs/data-release/{RELEASE_ID}/verify-001/release-readiness.json",
            DIGEST,
        ),
    )
    acquire, path = acceptance_lease.acquire_acceptance_lease(
        environment="gamma",
        release_id=RELEASE_ID,
        import_run_id="apply-001",
        verify_run_id="verify-001",
        lease_id="android-uat-readiness",
        event_id="acquire-001",
        release_root=tmp_path / "data/releases",
        output_root=tmp_path,
    )
    acquire["readinessRef"] = (
        f"env/gamma/runs/data-release/{RELEASE_ID}/verify-other/release-readiness.json"
    )
    acquire["verificationChecksum"] = acceptance_lease.event_checksum(acquire)

    assert any(
        "readinessRef does not bind" in issue
        for issue in acceptance_lease.validate_lease_event(
            acquire,
            path=path,
            output_root=tmp_path,
        )
    )


def test_ship__active_acceptance_lease_blocks_all_operations_for_other_release__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        acceptance_lease,
        "_readiness_binding",
        lambda **_kwargs: (
            f"env/gamma/runs/data-release/{RELEASE_ID}/verify-001/release-readiness.json",
            DIGEST,
        ),
    )
    acceptance_lease.acquire_acceptance_lease(
        environment="gamma",
        release_id=RELEASE_ID,
        import_run_id="apply-001",
        verify_run_id="verify-001",
        lease_id="android-uat-ship-block",
        event_id="acquire-001",
        release_root=tmp_path / "data/releases",
        output_root=tmp_path,
    )
    for ship_command, expected_call in (
        (ReleaseRunKind.APPLY, "apply"),
        (ReleaseRunKind.ROLLBACK, "rollback"),
        (ReleaseRunKind.VERIFY, "verify"),
    ):
        called: list[str] = []
        args = argparse.Namespace(
            ship_command=ship_command,
            release_id=RELEASE_B,
            to_release=RELEASE_B,
            env="gamma",
        )

        with pytest.raises(SystemExit, match="active acceptance lease"):
            dispatch_ship(
                args,
                release_root=tmp_path / "data/releases",
                apply=lambda _args: called.append("apply"),
                rollback=lambda _args: called.append("rollback"),
                verify=lambda _args: called.append("verify"),
            )
        assert called == []

        args.env = "beta"
        dispatch_ship(
            args,
            release_root=tmp_path / "data/releases",
            apply=lambda _args: called.append("apply"),
            rollback=lambda _args: called.append("rollback"),
            verify=lambda _args: called.append("verify"),
        )
        assert called == [expected_call]
