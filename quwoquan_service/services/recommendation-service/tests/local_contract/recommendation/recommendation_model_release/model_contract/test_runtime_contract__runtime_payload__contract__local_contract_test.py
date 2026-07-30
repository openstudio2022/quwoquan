from __future__ import annotations

from pathlib import Path

import pytest


from runtime_contract import bootstrap_runtime_contract_or_die


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_bootstrap_loads_one_autonomous_config_and_env_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = "recommendation-service"
    version = "sha256:" + "a" * 64

    _write_yaml(
        tmp_path / f"{service}.yaml",
        f"""
config:
  version: "{version}"
runtime:
  model_profile: "release"
""".strip(),
    )

    monkeypatch.setenv("APP_ENV", "gamma")
    monkeypatch.setenv("SERVICE_NAME", service)
    monkeypatch.setenv("CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("CONFIG_VERSION", version)
    monkeypatch.setenv("IMAGE_VERSION", "sha256:" + "b" * 64)
    monkeypatch.setenv("REC_SERVICE_HTTP_ADDR", ":19090")
    monkeypatch.setenv("REC_MODEL_CONTENT_FEED_PATH", "/tmp/model.bin")

    cfg = bootstrap_runtime_contract_or_die()

    assert cfg["service"]["http"]["addr"] == ":19090"
    assert cfg["config"]["version"] == version
    assert cfg["runtime"]["model_profile"] == "release"
    assert cfg["runtime"]["content_feed_model_path"] == "/tmp/model.bin"


def test_bootstrap_fail_fast_when_version_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = "recommendation-service"

    monkeypatch.setenv("APP_ENV", "gamma")
    monkeypatch.setenv("SERVICE_NAME", service)
    monkeypatch.setenv("CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("CONFIG_VERSION", "sha256:" + "b" * 64)
    monkeypatch.setenv("IMAGE_VERSION", "sha256:" + "c" * 64)

    with pytest.raises(RuntimeError, match="missing config file"):
        bootstrap_runtime_contract_or_die()


@pytest.mark.parametrize(
    ("app_env", "expected_profile"),
    [
        ("alpha", "alpha-local"),
        ("beta", "beta-local"),
        ("gamma", "gamma"),
        ("prod", "prod"),
    ],
)
def test_bootstrap_config_loading_matrix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    app_env: str,
    expected_profile: str,
) -> None:
    service = "recommendation-service"
    version = "sha256:" + "a" * 64

    _write_yaml(
        tmp_path / f"{service}.yaml",
        f"""
config:
  version: "{version}"
runtime:
  model_profile: "{expected_profile}"
""".strip(),
    )

    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("SERVICE_NAME", service)
    monkeypatch.setenv("CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("CONFIG_VERSION", version)
    monkeypatch.setenv("IMAGE_VERSION", "sha256:" + "b" * 64)

    cfg = bootstrap_runtime_contract_or_die()
    assert cfg["runtime"]["model_profile"] == expected_profile


def test_bootstrap_every_environment_requires_runtime_contract_envs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = "recommendation-service"

    monkeypatch.setenv("APP_ENV", "alpha")
    monkeypatch.setenv("SERVICE_NAME", service)
    monkeypatch.delenv("CONFIG_VERSION", raising=False)
    monkeypatch.delenv("IMAGE_VERSION", raising=False)
    monkeypatch.setenv("CONFIG_ROOT", str(tmp_path))

    with pytest.raises(RuntimeError, match="missing required runtime env"):
        bootstrap_runtime_contract_or_die()
