# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
"""Acceptance leases are time-bounded, fenced, and expose canonical CLI entrypoints."""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical import acceptance_lease  # noqa: E402
from core.io import write_json  # noqa: E402


def _event(root: Path, *, expired: bool) -> Path:
    expires = datetime.now(timezone.utc) + timedelta(seconds=-1 if expired else 3600)
    document = {
        "schema": acceptance_lease.SCHEMA,
        "environment": "gamma",
        "releaseId": "release-a",
        "sourceOwner": "qwq_data",
        "manifestDigest": "sha256:" + "a" * 64,
        "leaseId": "device-uat-a",
        "generation": 1,
        "fencingToken": "gamma:release-a:device-uat-a:1:sha256:" + "a" * 64,
        "expiresAt": expires.isoformat(),
        "eventId": "acquire-a",
        "action": "acquire",
        "holder": "stackctl.content-uat",
        "purpose": "user_acceptance",
        "importRunId": "apply-a",
        "verifyRunId": "verify-a",
        "readinessRef": "env/gamma/runs/data-release/release-a/verify-a/release-readiness.json",
        "predecessorEventRef": "",
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    document["verificationChecksum"] = acceptance_lease.event_checksum(document)
    path = acceptance_lease.event_path(
        output_root=root,
        environment="gamma",
        release_id="release-a",
        lease_id="device-uat-a",
        event_id="acquire-a",
    )
    write_json(path, document)
    return path


def test_active_lease_ignores_expired_generation(tmp_path: Path) -> None:
    _event(tmp_path, expired=True)
    assert acceptance_lease.active_acceptance_lease_refs(
        output_root=tmp_path,
        environment="gamma",
    ) == ()


def test_active_lease_returns_unexpired_fenced_generation(tmp_path: Path) -> None:
    path = _event(tmp_path, expired=False)
    assert acceptance_lease.active_acceptance_lease_refs(
        output_root=tmp_path,
        environment="gamma",
    ) == (path,)


def test_release_cli_exposes_acceptance_and_lifecycle_entrypoints() -> None:
    from content.release.canonical import handler as release_handler

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    release_handler.register_parser(commands)
    acquire = parser.parse_args([
        "release", "acceptance-lease", "acquire", "--env", "gamma",
        "--release-id", "release-a", "--lease-id", "lease-a",
        "--import-run-id", "apply-a", "--verify-run-id", "verify-a",
        "--ttl-seconds", "900",
    ])
    assert acquire.acceptance_lease_action == "acquire"
    assert acquire.ttl_seconds == 900
    lifecycle = parser.parse_args([
        "release", "lifecycle-exit", "--env", "gamma",
        "--original-release-id", "release-a", "--original-import-run-id", "apply-a",
        "--original-verify-run-id", "verify-a", "--rollback-to-release-id", "release-b",
        "--rollback-run-id", "rollback-b", "--rollback-verify-run-id", "verify-b",
        "--replay-import-run-id", "replay-a", "--replay-verify-run-id", "replay-verify-a",
        "--run-id", "exit-a",
    ])
    assert lifecycle.original_release_id == "release-a"
    assert lifecycle.run_id == "exit-a"
