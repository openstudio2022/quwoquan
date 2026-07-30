from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

VALID_APP_ENVS = {"alpha", "beta", "gamma", "prod"}
EXPECTED_SERVICE_NAME = "recommendation-service"


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"missing config file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"invalid config format (expect map): {path}")
    return data


def _runtime_paths(
    app_env: str, service_name: str, config_root: str, config_version: str
) -> list[Path]:
    del app_env
    if not config_root and not config_version:
        return []
    if not config_root or not config_version:
        raise RuntimeError(
            "CONFIG_ROOT and CONFIG_VERSION must be provided together"
        )
    return [
        Path(config_root) / f"{service_name}.yaml"
    ]



def load_layered_runtime_config_or_die(
    app_env: str, service_name: str, config_root: str, config_version: str
) -> dict[str, Any]:
    paths = _runtime_paths(app_env, service_name, config_root, config_version)
    merged: dict[str, Any] = {}
    if paths:
        path = paths[0]
        if not path.exists():
            raise RuntimeError(f"missing config file: {path}")
        merged = _load_yaml_dict(path)

    # env vars are final override layer
    if _env("REC_SERVICE_HTTP_ADDR"):
        merged.setdefault("service", {}).setdefault("http", {})["addr"] = _env(
            "REC_SERVICE_HTTP_ADDR"
        )
    if _env("REC_MODEL_CONTENT_FEED_PATH"):
        merged.setdefault("runtime", {})["content_feed_model_path"] = _env(
            "REC_MODEL_CONTENT_FEED_PATH"
        )
    if _env("REC_MODEL_CIRCLE_DISCOVERY_PATH"):
        merged.setdefault("runtime", {})["circle_discovery_model_path"] = _env(
            "REC_MODEL_CIRCLE_DISCOVERY_PATH"
        )
    if _env("REC_MODEL_FRIEND_SUGGESTION_PATH"):
        merged.setdefault("runtime", {})["friend_suggestion_model_path"] = _env(
            "REC_MODEL_FRIEND_SUGGESTION_PATH"
        )
    return merged


def _validate_runtime_configuration_identity_or_die(
    merged_cfg: dict[str, Any], config_version: str
) -> None:
    cfg = merged_cfg.get("config", {})
    if not isinstance(cfg, dict):
        raise RuntimeError("invalid config section in merged runtime config")

    file_version = str(cfg.get("version", "")).strip()
    if config_version and file_version and file_version != config_version:
        raise RuntimeError(
            f"CONFIG_VERSION mismatch: env={config_version!r} file={file_version!r}"
        )

def bootstrap_runtime_contract_or_die() -> dict[str, Any]:
    """
    Fail-fast runtime contract:
    - APP_ENV must be one of alpha/beta/gamma/prod.
    - SERVICE_NAME, when provided, must be recommendation-service.
    - CONFIG_VERSION/IMAGE_VERSION/CONFIG_ROOT are required in every environment.
    """
    app_env = _env("APP_ENV") or "alpha"
    if app_env not in VALID_APP_ENVS:
        raise RuntimeError(
            f"invalid APP_ENV={app_env!r}; expected one of {sorted(VALID_APP_ENVS)}"
        )

    service_name = _env("SERVICE_NAME") or EXPECTED_SERVICE_NAME
    if service_name != EXPECTED_SERVICE_NAME:
        raise RuntimeError(
            f"invalid SERVICE_NAME={service_name!r}; expected {EXPECTED_SERVICE_NAME!r}"
        )

    config_root = _env("CONFIG_ROOT")
    config_version = _env("CONFIG_VERSION")

    required = ["CONFIG_VERSION", "IMAGE_VERSION", "CONFIG_ROOT"]
    missing = [key for key in required if not _env(key)]
    if missing:
        raise RuntimeError(
            f"missing required runtime env for APP_ENV={app_env}: {', '.join(missing)}"
        )

    merged_cfg = load_layered_runtime_config_or_die(
        app_env=app_env,
        service_name=service_name,
        config_root=config_root,
        config_version=config_version,
    )
    _validate_runtime_configuration_identity_or_die(
        merged_cfg=merged_cfg,
        config_version=config_version,
    )
    return merged_cfg
