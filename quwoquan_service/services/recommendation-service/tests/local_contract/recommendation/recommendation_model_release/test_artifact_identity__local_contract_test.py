from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

API = Path(__file__).resolve().parents[5] / "cmd" / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from artifact_identity import verify_embedded_artifact_identity


def write_identity(tmp_path: Path, environment: str = "gamma") -> Path:
    path = tmp_path / "artifact-identity.json"
    path.write_text(
        json.dumps(
            {
                "schema": "qwq.environment-artifact-identity",
                "environment": environment,
                "configDigest": "sha256:" + "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_embedded_artifact_identity_requires_matching_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_identity(tmp_path)
    monkeypatch.setenv("QWQ_ARTIFACT_IDENTITY_FILE", str(path))
    monkeypatch.setenv("APP_ENV", "gamma")
    verify_embedded_artifact_identity()

    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(RuntimeError, match="does not match"):
        verify_embedded_artifact_identity()


def test_embedded_artifact_identity_rejects_extra_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_identity(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["selector"] = "prod"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("QWQ_ARTIFACT_IDENTITY_FILE", str(path))
    monkeypatch.setenv("APP_ENV", "gamma")
    with pytest.raises(RuntimeError, match="fields mismatch"):
        verify_embedded_artifact_identity()
