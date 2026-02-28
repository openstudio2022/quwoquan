from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

VALID_APP_ENVS = {"dev", "integration", "prod"}
EXPECTED_SERVICE_NAME = "recommendation-service"


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"missing config file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"invalid config format (expect map): {path}")
    return data


def _compare_semver(a: str, b: str) -> int:
    def parse(value: str) -> tuple[int, int, int]:
        parts = value.strip().lstrip("v").split(".")
        ints = [int(p) if p.isdigit() else 0 for p in parts[:3]]
        while len(ints) < 3:
            ints.append(0)
        return ints[0], ints[1], ints[2]

    av = parse(a)
    bv = parse(b)
    if av > bv:
        return 1
    if av < bv:
        return -1
    return 0


def _runtime_paths(
    app_env: str, service_name: str, config_root: str, config_version: str
) -> list[Path]:
    env_name = "local" if app_env == "dev" else app_env
    paths: list[Path] = []

    if config_root:
        root = Path(config_root)
        paths.append(root / "configs" / service_name / "default" / "config.yaml")
        paths.append(root / "configs" / service_name / env_name / "config.yaml")
        if config_version:
            paths.append(
                root
                / "releases"
                / "config"
                / service_name
                / f"{config_version}.yaml"
            )
        return paths

    service_dir = Path(__file__).resolve().parent
    paths.append(service_dir / "configs" / "default" / "config.yaml")
    paths.append(service_dir / "configs" / env_name / "config.yaml")
    if config_version:
        repo_root = service_dir.parents[3]
        paths.append(
            repo_root / "releases" / "config" / service_name / f"{config_version}.yaml"
        )
    return paths


def load_layered_runtime_config_or_die(
    app_env: str, service_name: str, config_root: str, config_version: str
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for path in _runtime_paths(app_env, service_name, config_root, config_version):
        merged = _deep_merge(merged, _load_yaml_dict(path))

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
    if _env("CONFIG_VERSION"):
        merged.setdefault("config", {})["version"] = _env("CONFIG_VERSION")

    return merged


def _validate_runtime_compatibility_or_die(
    merged_cfg: dict[str, Any], config_version: str, image_version: str
) -> None:
    cfg = merged_cfg.get("config", {})
    if not isinstance(cfg, dict):
        raise RuntimeError("invalid config section in merged runtime config")

    file_version = str(cfg.get("version", "")).strip()
    if config_version and file_version and file_version != config_version:
        raise RuntimeError(
            f"CONFIG_VERSION mismatch: env={config_version!r} file={file_version!r}"
        )

    if image_version:
        min_image = str(cfg.get("min_image_version", "")).strip()
        max_image = str(cfg.get("max_image_version", "")).strip()
        if min_image and _compare_semver(image_version, min_image) < 0:
            raise RuntimeError(
                f"IMAGE_VERSION={image_version!r} below min_image_version={min_image!r}"
            )
        if max_image and _compare_semver(image_version, max_image) > 0:
            raise RuntimeError(
                f"IMAGE_VERSION={image_version!r} above max_image_version={max_image!r}"
            )


def bootstrap_runtime_contract_or_die() -> dict[str, Any]:
    """
    Fail-fast runtime contract:
    - APP_ENV must be one of dev/integration/prod.
    - SERVICE_NAME, when provided, must be recommendation-service.
    - For integration/prod, CONFIG_VERSION/IMAGE_VERSION/CONFIG_ROOT are required.
    """
    app_env = _env("APP_ENV") or "dev"
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
    image_version = _env("IMAGE_VERSION")

    if app_env in {"integration", "prod"}:
        required = ["CONFIG_VERSION", "IMAGE_VERSION", "CONFIG_ROOT"]
        missing = [k for k in required if not _env(k)]
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
    _validate_runtime_compatibility_or_die(
        merged_cfg=merged_cfg,
        config_version=config_version,
        image_version=image_version,
    )
    return merged_cfg
