from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from content.release.canonical import handler as handler_owner
from content.release.canonical.supply_chain_drill import (
    DrillDependencies,
    FormalCommand,
    FormalCommandResult,
    run_supply_chain_drill,
)
from core.io import write_json
from core.schema import assert_valid


RELEASE_ID = "content-alpha-drill-001"
PREVIOUS_RELEASE_ID = "content-alpha-previous-001"
DIGEST = "sha256:" + "a" * 64
PREVIOUS_DIGEST = "sha256:" + "b" * 64


def _release(output_root: Path, release_id: str, digest: str) -> Path:
    release = output_root / "data/releases" / release_id
    write_json(
        release / "payload/release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": release_id,
            "sourceOwner": "qwq_data",
            "counts": {"article": 1, "image": 1, "video": 1, "total": 3},
        },
    )
    write_json(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": {
                "creators": ["creator-a"],
                "entities": ["地点/景区/测试"],
                "posts": ["article/a", "image/a", "video/a"],
                "tags": [],
            },
        },
    )
    write_json(
        release / "attestations/release.json",
        {
            "schema": "quwoquan_data.aggregate_release_attestation",
            "releaseId": release_id,
            "payloadSha256": digest,
        },
    )
    return release


def _candidate_and_previous_evidence(output_root: Path) -> None:
    candidate_import = (
        output_root
        / "env/alpha/runs/data-release"
        / RELEASE_ID
        / "apply-existing/import.json"
    )
    write_json(
        candidate_import,
        {
            "schema": "quwoquan.content_import_report",
            "releaseId": RELEASE_ID,
            "manifestDigest": DIGEST,
            "auditEvents": [
                "DataReleasePrepared",
                f"PreviousDataRelease|{PREVIOUS_RELEASE_ID}|{PREVIOUS_DIGEST}",
                "DataReleaseActivated",
            ],
        },
    )
    write_json(
        output_root
        / "env/alpha/runs/data-release"
        / RELEASE_ID
        / "verify-existing/release-readiness.json",
        {
            "schema": "quwoquan_data.environment_release_readiness",
            "environment": "alpha",
            "releaseId": RELEASE_ID,
            "manifestDigest": DIGEST,
            "importRunId": "apply-existing",
            "verifyRunId": "verify-existing",
            "readinessPhase": "research",
            "contentImportReportRef": candidate_import.relative_to(
                output_root
            ).as_posix(),
            "postIds": ["post-a", "post-b", "post-c"],
            "verifiedAt": "2026-08-11T00:00:00Z",
            "passed": True,
        },
    )
    write_json(
        output_root
        / "env/alpha/runs/data-release"
        / PREVIOUS_RELEASE_ID
        / "verify-previous/release-readiness.json",
        {
            "schema": "quwoquan_data.environment_release_readiness",
            "environment": "alpha",
            "releaseId": PREVIOUS_RELEASE_ID,
            "manifestDigest": PREVIOUS_DIGEST,
            "importRunId": "apply-previous",
            "verifyRunId": "verify-previous",
            "readinessPhase": "research",
            "postIds": ["post-previous"],
            "verifiedAt": "2026-08-10T00:00:00Z",
            "passed": True,
        },
    )


class _Clock:
    def __init__(self) -> None:
        self.instant = datetime(2026, 8, 11, tzinfo=timezone.utc)
        self.elapsed = 0.0

    def now(self) -> datetime:
        value = self.instant
        self.instant += timedelta(milliseconds=1)
        return value

    def monotonic(self) -> float:
        self.elapsed += 0.01
        return self.elapsed


def _dependencies(
    calls: list[FormalCommand],
    *,
    fail_stage: str = "",
) -> DrillDependencies:
    clock = _Clock()

    def run(command: FormalCommand) -> FormalCommandResult:
        calls.append(command)
        if command.name == fail_stage:
            return FormalCommandResult(
                returncode=2,
                payload={},
                evidence_ref=command.evidence_ref,
                first_blocker="DATA.TEST.DRILL_STAGE_FAILED",
            )
        payload: dict[str, object] = {}
        if command.name == "content-delivery":
            payload = {
                "schema": "quwoquan_ops.content_delivery_verification",
                "result": "ready",
                "counts": {
                    "manifestPosts": 3,
                    "importedPosts": 3,
                    "activePosts": 3,
                    "searchablePosts": 3,
                    "recommendablePosts": 3,
                },
            }
        return FormalCommandResult(
            returncode=0,
            payload=payload,
            evidence_ref=command.evidence_ref,
            first_blocker="",
        )

    return DrillDependencies(
        run_command=run,
        read_runtime=lambda _target: {"status": "stopped", "workload": ""},
        now=clock.now,
        monotonic=clock.monotonic,
    )


def test_inspect_is_read_only_and_writes_one_schema_valid_receipt(
    tmp_path: Path,
) -> None:
    _release(tmp_path, RELEASE_ID, DIGEST)
    calls: list[FormalCommand] = []

    document, receipt = run_supply_chain_drill(
        release_id=RELEASE_ID,
        environment="alpha",
        profile="inspect",
        output_root=tmp_path,
        dependencies=_dependencies(calls),
    )

    assert calls == []
    assert receipt.is_file()
    assert list(receipt.parent.glob("*.json")) == [receipt]
    assert document["result"] == "ready"
    assert document["counts"] == {
        "expected": 3,
        "imported": None,
        "active": None,
        "searchable": None,
        "recommendable": None,
    }
    assert document["stages"][0]["name"] == "inspect"
    assert_valid(document, "release", "supply_chain_drill_receipt")


def test_delivery_uses_only_formal_ship_and_content_delivery(
    tmp_path: Path,
) -> None:
    _release(tmp_path, RELEASE_ID, DIGEST)
    calls: list[FormalCommand] = []

    document, _receipt = run_supply_chain_drill(
        release_id=RELEASE_ID,
        environment="alpha",
        profile="delivery",
        output_root=tmp_path,
        dependencies=_dependencies(calls),
    )

    assert [item.name for item in calls] == [
        "ship-apply",
        "ship-verify",
        "content-delivery",
    ]
    assert calls[0].argv[1:4] == ("ship", "apply", "--release-id")
    assert "--full-sync" in calls[0].argv
    assert calls[1].argv[1:4] == ("ship", "verify", "--release-id")
    assert calls[2].argv[1:4] == ("verify", "--env", "alpha")
    assert "content-delivery" in calls[2].argv
    assert document["result"] == "ready"
    assert document["counts"] == {
        "expected": 3,
        "imported": 3,
        "active": 3,
        "searchable": 3,
        "recommendable": 3,
    }


def test_rehearsal_locks_previous_verified_release_and_restores_runtime(
    tmp_path: Path,
) -> None:
    _release(tmp_path, RELEASE_ID, DIGEST)
    _release(tmp_path, PREVIOUS_RELEASE_ID, PREVIOUS_DIGEST)
    _candidate_and_previous_evidence(tmp_path)
    calls: list[FormalCommand] = []

    document, _receipt = run_supply_chain_drill(
        release_id=RELEASE_ID,
        environment="alpha",
        profile="rehearsal",
        platform="android",
        device_id="emulator-5554",
        output_root=tmp_path,
        dependencies=_dependencies(calls),
    )

    assert [item.name for item in calls] == [
        "package",
        "up",
        "app-content-uat",
        "rollback",
        "rollback-verify",
        "replay",
        "replay-verify",
        "down",
    ]
    rollback = calls[3].argv
    assert rollback[1:4] == ("ship", "rollback", "--to-release")
    assert PREVIOUS_RELEASE_ID in rollback
    assert RELEASE_ID in rollback
    replay = calls[5].argv
    assert replay[1:4] == ("ship", "apply", "--release-id")
    assert RELEASE_ID in replay
    assert document["result"] == "ready"
    assert document["runtimeRestored"] is True


def test_rehearsal_failure_still_runs_bounded_down_and_blocks(
    tmp_path: Path,
) -> None:
    _release(tmp_path, RELEASE_ID, DIGEST)
    _release(tmp_path, PREVIOUS_RELEASE_ID, PREVIOUS_DIGEST)
    _candidate_and_previous_evidence(tmp_path)
    calls: list[FormalCommand] = []

    document, _receipt = run_supply_chain_drill(
        release_id=RELEASE_ID,
        environment="alpha",
        profile="rehearsal",
        platform="ios-simulator",
        device_id="simulator-a",
        output_root=tmp_path,
        dependencies=_dependencies(calls, fail_stage="app-content-uat"),
    )

    assert [item.name for item in calls] == [
        "package",
        "up",
        "app-content-uat",
        "down",
    ]
    assert document["result"] == "blocked"
    assert document["runtimeRestored"] is True
    assert document["stages"][2]["firstBlocker"] == (
        "DATA.TEST.DRILL_STAGE_FAILED"
    )


def test_rehearsal_restores_an_initial_full_runtime(tmp_path: Path) -> None:
    _release(tmp_path, RELEASE_ID, DIGEST)
    _release(tmp_path, PREVIOUS_RELEASE_ID, PREVIOUS_DIGEST)
    _candidate_and_previous_evidence(tmp_path)
    calls: list[FormalCommand] = []
    dependencies = replace(
        _dependencies(calls),
        read_runtime=lambda _target: {"status": "running", "workload": "full"},
    )

    document, _receipt = run_supply_chain_drill(
        release_id=RELEASE_ID,
        environment="alpha",
        profile="rehearsal",
        platform="android",
        device_id="device-a",
        output_root=tmp_path,
        dependencies=dependencies,
    )

    assert [item.name for item in calls] == [
        "runtime-pause",
        "package",
        "up",
        "app-content-uat",
        "rollback",
        "rollback-verify",
        "replay",
        "replay-verify",
        "down",
        "runtime-restore",
    ]
    assert document["result"] == "ready"
    assert document["runtimeRestored"] is True


def test_prod_rehearsal_never_invokes_an_activation_command(tmp_path: Path) -> None:
    _release(tmp_path, RELEASE_ID, DIGEST)
    calls: list[FormalCommand] = []

    document, _receipt = run_supply_chain_drill(
        release_id=RELEASE_ID,
        environment="prod",
        profile="rehearsal",
        platform="android",
        device_id="physical-a",
        output_root=tmp_path,
        dependencies=_dependencies(calls),
    )

    assert calls == []
    assert document["result"] == "blocked"
    assert document["stages"][0]["firstBlocker"] == (
        "DATA.SUPPLY_CHAIN_DRILL.PROD_ACTIVATION_FORBIDDEN"
    )


def test_release_cli_exposes_supply_chain_drill_and_pool_batch_view() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    handler_owner.register_parser(subparsers)

    args = parser.parse_args(
        [
            "release",
            "supply-chain-drill",
            "--release-id",
            RELEASE_ID,
            "--env",
            "gamma",
            "--profile",
            "rehearsal",
            "--platform",
            "android",
            "--device-id",
            "device-a",
        ]
    )
    assert args.release_id == RELEASE_ID
    assert args.env == "gamma"
    assert args.profile == "rehearsal"
    assert args.platform == "android"
    assert args.device_id == "device-a"

    pool_args = parser.parse_args(["release", "pool-inspect", "--by-task"])
    assert pool_args.by_task is True
