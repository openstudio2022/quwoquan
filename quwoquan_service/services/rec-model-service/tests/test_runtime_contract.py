from __future__ import annotations

from pathlib import Path

import pytest

from runtime_contract import bootstrap_runtime_contract_or_die


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_bootstrap_loads_default_env_version_and_env_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = "recommendation-service"
    version = "v2026.02.28.0"

    _write_yaml(
        tmp_path / "configs" / service / "default" / "config.yaml",
        """
service:
  http:
    addr: ":18080"
config:
  version: "v0.0.1"
  min_image_version: "1.0.0"
  max_image_version: "2.0.0"
runtime:
  model_profile: "default"
""".strip(),
    )
    _write_yaml(
        tmp_path / "configs" / service / "integration" / "config.yaml",
        """
runtime:
  model_profile: "integration"
""".strip(),
    )
    _write_yaml(
        tmp_path / "releases" / "config" / service / f"{version}.yaml",
        """
config:
  version: "v2026.02.28.0"
runtime:
  model_profile: "release"
""".strip(),
    )

    monkeypatch.setenv("APP_ENV", "integration")
    monkeypatch.setenv("SERVICE_NAME", service)
    monkeypatch.setenv("CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("CONFIG_VERSION", version)
    monkeypatch.setenv("IMAGE_VERSION", "1.2.3")
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

    _write_yaml(
        tmp_path / "configs" / service / "default" / "config.yaml",
        "config:\n  version: v0.0.1\n",
    )
    _write_yaml(
        tmp_path / "configs" / service / "integration" / "config.yaml",
        "service:\n  http:\n    addr: ':18080'\n",
    )

    monkeypatch.setenv("APP_ENV", "integration")
    monkeypatch.setenv("SERVICE_NAME", service)
    monkeypatch.setenv("CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("CONFIG_VERSION", "v-missing")
    monkeypatch.setenv("IMAGE_VERSION", "1.0.0")

    with pytest.raises(RuntimeError, match="missing config file"):
        bootstrap_runtime_contract_or_die()
