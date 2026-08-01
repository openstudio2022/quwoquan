from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from quwoquan_ops.cli.lib import startup_attempt_receipt as subject


def _composition() -> dict[str, object]:
    return {
        "imageVersion": "sha256:" + "a" * 64,
        "images": {"api-edge": {"ref": "qwq/api-edge@sha256:" + "b" * 64}},
    }


def test_startup_attempt_has_atomic_transactional_lifecycle(tmp_path: Path) -> None:
    receipt_path = tmp_path / "process/startup_attempt.json"
    run_root = tmp_path / "runs/up-alpha"
    common = {
        "env": "alpha",
        "target": "alpha-local",
        "attempt_id": "up-alpha",
        "workload": "content-release",
        "compose_project": "quwoquan_alpha_release",
        "configuration_digest": "sha256:" + "c" * 64,
        "image_transport_tag": "sha256:" + "a" * 64,
        "image_composition": _composition(),
        "run_root": str(run_root),
    }

    with mock.patch.object(
        subject,
        "startup_attempt_path",
        return_value=receipt_path,
    ):
        prepared = subject.transition_startup_attempt(status="prepared", **common)
        partial = subject.transition_startup_attempt(status="partial", **common)
        running = subject.transition_startup_attempt(status="running", **common)
        stopped = subject.transition_startup_attempt(status="stopped", **common)

    assert [prepared["status"], partial["status"], running["status"], stopped["status"]] == [
        "prepared",
        "partial",
        "running",
        "stopped",
    ]
    assert stopped["composeProject"] == "quwoquan_alpha_release"
    assert stopped["imageComposition"] == _composition()
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == stopped
    assert json.loads(
        (run_root / "startup_attempt.json").read_text(encoding="utf-8")
    ) == stopped
    assert not list(receipt_path.parent.glob("*.tmp"))


def test_partial_cleanup_failure_remains_partial_and_keeps_original_error(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "startup_attempt.json"
    with mock.patch.object(
        subject,
        "startup_attempt_path",
        return_value=receipt_path,
    ):
        subject.transition_startup_attempt(
            env="gamma",
            target="gamma-local",
            attempt_id="attempt-1",
            status="prepared",
        )
        subject.transition_startup_attempt(
            env="gamma",
            target="gamma-local",
            attempt_id="attempt-1",
            status="partial",
            compose_project="quwoquan_gamma_release",
            configuration_digest="sha256:" + "c" * 64,
            image_transport_tag="sha256:" + "a" * 64,
            image_composition=_composition(),
        )
        receipt = subject.transition_startup_attempt(
            env="gamma",
            target="gamma-local",
            attempt_id="attempt-1",
            status="partial",
            failure="startup exited with status 1",
            cleanup_failure="compose down failed",
        )

    assert receipt["status"] == "partial"
    assert receipt["failure"] == "startup exited with status 1"
    assert receipt["cleanupFailure"] == "compose down failed"


def test_startup_attempt_rejects_cross_attempt_and_invalid_transition(
    tmp_path: Path,
) -> None:
    with mock.patch.object(
        subject,
        "startup_attempt_path",
        return_value=tmp_path / "startup_attempt.json",
    ):
        subject.transition_startup_attempt(
            env="beta",
            target="beta-local",
            attempt_id="attempt-1",
            status="prepared",
        )
        with pytest.raises(ValueError, match="identity mismatch"):
            subject.transition_startup_attempt(
                env="beta",
                target="beta-local",
                attempt_id="attempt-2",
                status="partial",
                compose_project="quwoquan_beta_release",
                configuration_digest="sha256:" + "c" * 64,
                image_transport_tag="sha256:" + "a" * 64,
                image_composition=_composition(),
            )
        with pytest.raises(ValueError, match="transition is invalid"):
            subject.transition_startup_attempt(
                env="beta",
                target="beta-local",
                attempt_id="attempt-1",
                status="running",
            )
