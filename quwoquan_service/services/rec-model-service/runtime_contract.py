from __future__ import annotations

import os

VALID_APP_ENVS = {"dev", "integration", "prod"}
EXPECTED_SERVICE_NAME = "recommendation-service"


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def bootstrap_runtime_contract_or_die() -> None:
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

    service_name = _env("SERVICE_NAME")
    if service_name and service_name != EXPECTED_SERVICE_NAME:
        raise RuntimeError(
            f"invalid SERVICE_NAME={service_name!r}; expected {EXPECTED_SERVICE_NAME!r}"
        )

    if app_env in {"integration", "prod"}:
        required = ["CONFIG_VERSION", "IMAGE_VERSION", "CONFIG_ROOT"]
        missing = [k for k in required if not _env(k)]
        if missing:
            raise RuntimeError(
                f"missing required runtime env for APP_ENV={app_env}: {', '.join(missing)}"
            )
