"""Reclaiming an inadmissible test-live receipt is probe-gated and archived.

A receipt frozen by a retired field set fails closed on every read, which
leaves its target unable to start, stop or restart. Reclaiming restores
operability, so it must never be reachable while the runtime it describes is
still alive, and it must leave the removed evidence behind.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quwoquan_ops.cli import stackctl

STALE_RECEIPT = {
    "schema": "stackctl.mutable_test_live_startup_attempt",
    "attemptId": "alpha-test-live-retired",
    "status": "stopped",
    "contentBindingState": "unbound",
}
VOLUMES = ["quwoquan_alpha_test_live_local-gamma-mongo"]


def _args(*, confirm: bool) -> argparse.Namespace:
    return argparse.Namespace(
        target="alpha-local",
        fix="reclaim-stale-test-live-receipt",
        confirm_stale_test_live_receipt_reclaim=confirm,
    )


def _clean_runtime(monkeypatch, *, volumes: list[str] | None = None) -> None:
    monkeypatch.setattr(stackctl, "active_consumer_leases", lambda _target: [])
    monkeypatch.setattr(
        stackctl,
        "_mutable_test_live_container_ids",
        lambda _project: [],
    )
    monkeypatch.setattr(
        stackctl,
        "_mutable_test_live_resource_names",
        lambda kind, *, compose_project: (
            list(VOLUMES if volumes is None else volumes) if kind == "volume" else []
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_canonical_port_occupancy_report",
        lambda _target: {"ports": [{"name": "api-edge", "port": 17000, "open": False}]},
    )
    monkeypatch.setattr(
        stackctl,
        "test_live_startup_attempt_path",
        lambda target: Path(f"/process/{target}/test_live_startup_attempt.json"),
    )


def _run(report_dir: Path, *, confirm: bool) -> dict:
    return stackctl._repair_stale_test_live_receipt(
        _args(confirm=confirm),
        environment="alpha",
        report_dir=report_dir,
    )


def test_audit_reports_the_reclaim_without_removing_anything(
    monkeypatch, tmp_path: Path
) -> None:
    removals: list[str] = []
    _clean_runtime(monkeypatch)
    monkeypatch.setattr(
        stackctl,
        "read_stale_test_live_startup_attempt",
        lambda _target: dict(STALE_RECEIPT),
    )
    monkeypatch.setattr(
        stackctl,
        "reclaim_stale_test_live_startup_attempt",
        lambda target: removals.append(target),
    )

    result = _run(tmp_path, confirm=False)

    assert result["exitCode"] == 0
    assert removals == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["auditOnly"] is True
    assert report["reclaimed"] is False
    assert report["preservedVolumes"] == VOLUMES
    assert not (tmp_path / "stale_test_live_receipt.json").exists()


def test_confirmed_reclaim_archives_the_receipt_before_removing_it(
    monkeypatch, tmp_path: Path
) -> None:
    removals: list[str] = []
    _clean_runtime(monkeypatch)
    monkeypatch.setattr(
        stackctl,
        "read_stale_test_live_startup_attempt",
        lambda _target: dict(STALE_RECEIPT),
    )

    def _reclaim(target: str) -> dict:
        removals.append(target)
        return dict(STALE_RECEIPT)

    monkeypatch.setattr(
        stackctl, "reclaim_stale_test_live_startup_attempt", _reclaim
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 0
    assert removals == ["alpha-local"]
    archive = json.loads(
        (tmp_path / "stale_test_live_receipt.json").read_text(encoding="utf-8")
    )
    assert archive == STALE_RECEIPT
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["reclaimed"] is True
    assert report["preservedVolumes"] == VOLUMES


def test_admissible_receipt_is_refused_so_normal_down_stays_the_only_path(
    monkeypatch, tmp_path: Path
) -> None:
    removals: list[str] = []
    _clean_runtime(monkeypatch)
    monkeypatch.setattr(
        stackctl, "read_stale_test_live_startup_attempt", lambda _target: None
    )
    monkeypatch.setattr(
        stackctl,
        "reclaim_stale_test_live_startup_attempt",
        lambda target: removals.append(target),
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert removals == []
    assert any("normal down path" in item for item in result["details"])


def test_live_runtime_residue_blocks_the_reclaim(monkeypatch, tmp_path: Path) -> None:
    removals: list[str] = []
    _clean_runtime(monkeypatch)
    monkeypatch.setattr(
        stackctl,
        "read_stale_test_live_startup_attempt",
        lambda _target: dict(STALE_RECEIPT),
    )
    monkeypatch.setattr(
        stackctl,
        "_mutable_test_live_container_ids",
        lambda _project: ["c0ffee"],
    )
    monkeypatch.setattr(
        stackctl,
        "reclaim_stale_test_live_startup_attempt",
        lambda target: removals.append(target),
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert removals == []
    assert any("still owns containers" in item for item in result["details"])


def test_active_consumer_lease_blocks_the_reclaim(monkeypatch, tmp_path: Path) -> None:
    removals: list[str] = []
    _clean_runtime(monkeypatch)
    monkeypatch.setattr(
        stackctl,
        "read_stale_test_live_startup_attempt",
        lambda _target: dict(STALE_RECEIPT),
    )
    monkeypatch.setattr(
        stackctl,
        "active_consumer_leases",
        lambda _target: [{"device": "iphone-1", "consumer": "app-content-uat"}],
    )
    monkeypatch.setattr(
        stackctl,
        "reclaim_stale_test_live_startup_attempt",
        lambda target: removals.append(target),
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert removals == []
    assert any("active consumer leases" in item for item in result["details"])


def test_occupied_canonical_port_blocks_the_reclaim(
    monkeypatch, tmp_path: Path
) -> None:
    _clean_runtime(monkeypatch)
    monkeypatch.setattr(
        stackctl,
        "read_stale_test_live_startup_attempt",
        lambda _target: dict(STALE_RECEIPT),
    )
    monkeypatch.setattr(
        stackctl,
        "_canonical_port_occupancy_report",
        lambda _target: {
            "ports": [{"name": "api-edge", "port": 17000, "open": True}]
        },
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert any("ports remain occupied" in item for item in result["details"])


def test_losing_a_named_volume_is_reported_as_a_failure(
    monkeypatch, tmp_path: Path
) -> None:
    _clean_runtime(monkeypatch)
    monkeypatch.setattr(
        stackctl,
        "read_stale_test_live_startup_attempt",
        lambda _target: dict(STALE_RECEIPT),
    )
    monkeypatch.setattr(
        stackctl,
        "reclaim_stale_test_live_startup_attempt",
        lambda _target: dict(STALE_RECEIPT),
    )
    observed: list[str] = []

    def _names(kind: str, *, compose_project: str) -> list[str]:
        if kind != "volume":
            return []
        observed.append(kind)
        return list(VOLUMES) if len(observed) == 1 else []

    monkeypatch.setattr(stackctl, "_mutable_test_live_resource_names", _names)

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert any("named volumes were removed" in item for item in result["details"])


def test_production_targets_are_never_reclaimable(monkeypatch, tmp_path: Path) -> None:
    args = _args(confirm=True)
    args.target = "prod-hosted"

    result = stackctl._repair_stale_test_live_receipt(
        args,
        environment="prod",
        report_dir=tmp_path,
    )

    assert result["exitCode"] == 2
    assert any("only available for" in item for item in result["details"])
