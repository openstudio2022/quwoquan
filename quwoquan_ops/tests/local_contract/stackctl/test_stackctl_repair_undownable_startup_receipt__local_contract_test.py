"""Retiring an undownable formal receipt is probe-gated, archived and terminal.

Normal ``down`` replays the receipt's own candidate topology under the receipt's
own workload. When that projection carries a service with neither an image nor a
build context nor a gating profile, ``docker compose`` rejects the whole project,
so ``down`` can never converge while ``up`` keeps refusing to run before ``down``
succeeds. Retiring restores operability, so it must stay unreachable while the
runtime it describes is alive, must leave the removed evidence behind, and must
refuse any receipt whose normal ``down`` is still usable.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quwoquan_ops.cli import stackctl

UNDOWNABLE_RECEIPT = {
    "schema": "stackctl.startup_attempt",
    "target": "alpha-local",
    "env": "alpha",
    "attemptId": "20260817T122017745469Z-up-alpha-local",
    "status": "partial",
    "workload": "content-release",
    "composeProject": "quwoquan_alpha_local",
    "candidateDigest": "sha256:" + "a" * 64,
}
STRUCTURAL_REASON = (
    "candidate sha256:" + "a" * 64 + " projects workload=content-release into an "
    "invalid Compose project; services without image, build or gating profile: "
    "rtc-service"
)
VOLUMES = ["quwoquan_alpha_local-mongo"]


def _args(*, confirm: bool) -> argparse.Namespace:
    return argparse.Namespace(
        target="alpha-local",
        fix="reclaim-undownable-startup-receipt",
        confirm_undownable_startup_receipt_reclaim=confirm,
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
        "startup_attempt_path",
        lambda target: Path(f"/process/{target}/startup_attempt.json"),
    )


def _undownable(monkeypatch, *, receipt: dict | None = None) -> None:
    monkeypatch.setattr(
        stackctl,
        "load_startup_attempt",
        lambda _target: None if receipt is None else dict(receipt),
    )
    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: STRUCTURAL_REASON,
    )


def _run(report_dir: Path, *, confirm: bool) -> dict:
    return stackctl._repair_undownable_startup_receipt(
        _args(confirm=confirm),
        environment="alpha",
        report_dir=report_dir,
    )


def test_audit_names_the_structural_defect_without_retiring_anything(
    monkeypatch, tmp_path: Path
) -> None:
    closures: list[str] = []
    _clean_runtime(monkeypatch)
    _undownable(monkeypatch, receipt=UNDOWNABLE_RECEIPT)
    monkeypatch.setattr(
        stackctl,
        "_close_orphan_reclaimed_startup_receipt",
        lambda target, _startup: closures.append(target) or "",
    )

    result = _run(tmp_path, confirm=False)

    assert result["exitCode"] == 0
    assert closures == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["auditOnly"] is True
    assert report["reclaimed"] is False
    assert report["structuralReason"] == STRUCTURAL_REASON
    assert report["preservedVolumes"] == VOLUMES
    assert not (tmp_path / "undownable_startup_receipt.json").exists()


def test_confirmed_retirement_archives_the_receipt_and_stops_it(
    monkeypatch, tmp_path: Path
) -> None:
    closed: list[tuple[str, str]] = []
    _clean_runtime(monkeypatch)
    _undownable(monkeypatch, receipt=UNDOWNABLE_RECEIPT)

    def _close(target: str, startup: dict) -> str:
        closed.append((target, str(startup.get("attemptId"))))
        return f"retired startup receipt status=partial attempt={startup['attemptId']}"

    monkeypatch.setattr(
        stackctl, "_close_orphan_reclaimed_startup_receipt", _close
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 0
    assert closed == [("alpha-local", UNDOWNABLE_RECEIPT["attemptId"])]
    archive = json.loads(
        (tmp_path / "undownable_startup_receipt.json").read_text(encoding="utf-8")
    )
    assert archive == UNDOWNABLE_RECEIPT
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["reclaimed"] is True
    assert report["preservedVolumes"] == VOLUMES
    assert any("can now start, stop and restart" in item for item in result["details"])


def test_downable_receipt_is_refused_so_normal_down_stays_the_only_path(
    monkeypatch, tmp_path: Path
) -> None:
    closures: list[str] = []
    _clean_runtime(monkeypatch)
    monkeypatch.setattr(
        stackctl, "load_startup_attempt", lambda _target: dict(UNDOWNABLE_RECEIPT)
    )
    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "",
    )
    monkeypatch.setattr(
        stackctl,
        "_close_orphan_reclaimed_startup_receipt",
        lambda target, _startup: closures.append(target) or "",
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert closures == []
    assert any("stackctl down --target alpha-local" in item for item in result["details"])


def test_stopped_receipt_is_refused_because_up_is_already_admitted(
    monkeypatch, tmp_path: Path
) -> None:
    _clean_runtime(monkeypatch)
    _undownable(monkeypatch, receipt={**UNDOWNABLE_RECEIPT, "status": "stopped"})

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert any("no non-stopped startup receipt" in item for item in result["details"])


def test_absent_receipt_is_refused(monkeypatch, tmp_path: Path) -> None:
    _clean_runtime(monkeypatch)
    _undownable(monkeypatch, receipt=None)

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert any("no non-stopped startup receipt" in item for item in result["details"])


def test_live_container_blocks_the_retirement(monkeypatch, tmp_path: Path) -> None:
    closures: list[str] = []
    _clean_runtime(monkeypatch)
    _undownable(monkeypatch, receipt=UNDOWNABLE_RECEIPT)
    monkeypatch.setattr(
        stackctl,
        "_mutable_test_live_container_ids",
        lambda _project: ["c0ffee"],
    )
    monkeypatch.setattr(
        stackctl,
        "_close_orphan_reclaimed_startup_receipt",
        lambda target, _startup: closures.append(target) or "",
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert closures == []
    assert any("still owns containers" in item for item in result["details"])


def test_active_consumer_lease_blocks_the_retirement(
    monkeypatch, tmp_path: Path
) -> None:
    _clean_runtime(monkeypatch)
    _undownable(monkeypatch, receipt=UNDOWNABLE_RECEIPT)
    monkeypatch.setattr(
        stackctl,
        "active_consumer_leases",
        lambda _target: [{"device": "iphone-1", "consumer": "app-content-uat"}],
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert any("active consumer leases" in item for item in result["details"])


def test_occupied_canonical_port_blocks_the_retirement(
    monkeypatch, tmp_path: Path
) -> None:
    _clean_runtime(monkeypatch)
    _undownable(monkeypatch, receipt=UNDOWNABLE_RECEIPT)
    monkeypatch.setattr(
        stackctl,
        "_canonical_port_occupancy_report",
        lambda _target: {"ports": [{"name": "api-edge", "port": 17000, "open": True}]},
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert any("ports remain occupied" in item for item in result["details"])


def test_receipt_without_a_compose_project_is_refused(
    monkeypatch, tmp_path: Path
) -> None:
    _clean_runtime(monkeypatch)
    _undownable(
        monkeypatch,
        receipt={**UNDOWNABLE_RECEIPT, "composeProject": ""},
    )

    result = _run(tmp_path, confirm=True)

    assert result["exitCode"] == 2
    assert any("names no Compose project" in item for item in result["details"])


def test_losing_a_named_volume_is_reported_as_a_failure(
    monkeypatch, tmp_path: Path
) -> None:
    _clean_runtime(monkeypatch)
    _undownable(monkeypatch, receipt=UNDOWNABLE_RECEIPT)
    monkeypatch.setattr(
        stackctl,
        "_close_orphan_reclaimed_startup_receipt",
        lambda _target, _startup: "retired",
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

    result = stackctl._repair_undownable_startup_receipt(
        args,
        environment="prod",
        report_dir=tmp_path,
    )

    assert result["exitCode"] == 2
    assert any("only available for" in item for item in result["details"])
