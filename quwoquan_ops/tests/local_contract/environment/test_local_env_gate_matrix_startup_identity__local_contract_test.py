"""local_contract：矩阵启动 receipt 必须绑定当前 target package 身份。"""

from __future__ import annotations

import pytest

from quwoquan_ops.cli.lib.local_env_gate_matrix.identity import (
    _startup_attempt_matches_package_identity,
)

TARGET = "alpha-local"
ENVIRONMENT = "alpha"
PACKAGE_BASELINE = f"sha256:{'a' * 64}"


def _running_attempt() -> dict[str, object]:
    return {
        "status": "running",
        "target": TARGET,
        "env": ENVIRONMENT,
        "workload": "full",
        "candidateDigest": PACKAGE_BASELINE,
        "composeProject": "quwoquan-alpha-local",
        "configurationDigest": f"sha256:{'b' * 64}",
        "imageTransportTag": f"sha256:{'c' * 64}",
    }


def test_running_startup_attempt_matches_current_package_identity() -> None:
    assert _startup_attempt_matches_package_identity(
        _running_attempt(),
        target=TARGET,
        environment=ENVIRONMENT,
        package_baseline=PACKAGE_BASELINE,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", "stopped"),
        ("target", "beta-local"),
        ("env", "beta"),
        ("workload", "service"),
        ("candidateDigest", f"sha256:{'d' * 64}"),
        ("composeProject", ""),
        ("configurationDigest", "unknown"),
        ("imageTransportTag", "unknown"),
    ),
)
def test_startup_attempt_identity_drift_is_rejected(
    field: str,
    value: object,
) -> None:
    attempt = _running_attempt()
    attempt[field] = value

    assert not _startup_attempt_matches_package_identity(
        attempt,
        target=TARGET,
        environment=ENVIRONMENT,
        package_baseline=PACKAGE_BASELINE,
    )
