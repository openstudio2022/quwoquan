"""Auto-generate Alpha/Beta substitute credentials under QWQ_DEPLOY_WORK_ROOT."""

from __future__ import annotations

import fcntl
import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Mapping

from .external_provider_governance import (
    SUBSTITUTE_ENVIRONMENTS,
    is_local_substitute_adapter,
    load_bindings,
)
from .output_paths import deployment_target_path, deployment_work_root


_DEFAULT_VALUES: dict[str, str] = {
    "ASSISTANT_MODEL_FIXTURE_ENDPOINT": "https://fixture.local/assistant/model/completion",
    "ASSISTANT_MODEL_API_KEY": "",
    "ASSISTANT_PUBLIC_SEARCH_FIXTURE_URL": "https://fixture.local/assistant/search",
    "ASSISTANT_WEATHER_FIXTURE_GEOCODING_URL": "https://fixture.local/assistant/weather/geocoding",
    "ASSISTANT_WEATHER_FIXTURE_FORECAST_URL": "https://fixture.local/assistant/weather/forecast",
    "ASSISTANT_FINANCE_FIXTURE_CHART_URL": "https://fixture.local/assistant/finance/chart",
    "CONTENT_EMBEDDING_FIXTURE_ENDPOINT": "https://fixture.local/content/embedding",
    "CONTENT_EMBEDDING_FIXTURE_API_KEY": "",
    "RTC_MEDIA_FIXTURE_CONNECTION_URL": "wss://fixture.local/rtc",
    "RTC_MEDIA_FIXTURE_API_KEY": "",
    "RTC_MEDIA_FIXTURE_API_SECRET": "",
    "INTEGRATION_SMS_FIXTURE_ENDPOINT": "https://fixture.local/integration/sms",
    "INTEGRATION_SMS_FIXTURE_TOKEN": "",
    "INTEGRATION_PUSH_FIXTURE_USER_SERVICE_BASE_URL": "https://fixture.local/user",
    "INTEGRATION_PUSH_FIXTURE_HMAC_KEY": "",
    "INTEGRATION_LOCATION_FIXTURE_BASE_URL": "https://fixture.local/integration/location",
    "INTEGRATION_LOCATION_FIXTURE_AK": "",
    "IDENTITY_ONE_TAP_FIXTURE_ENDPOINT": "https://fixture.local/identity/one-tap",
    "IDENTITY_ONE_TAP_FIXTURE_ACCESS_KEY_ID": "",
    "IDENTITY_ONE_TAP_FIXTURE_ACCESS_KEY_SECRET": "",
    "IDENTITY_SOCIAL_FIXTURE_WECHAT_TOKEN_URL": "https://fixture.local/identity/wechat/token",
    "IDENTITY_SOCIAL_FIXTURE_WECHAT_USER_INFO_URL": "https://fixture.local/identity/wechat/user",
    "IDENTITY_SOCIAL_FIXTURE_ALIPAY_TOKEN_URL": "https://fixture.local/identity/alipay/token",
    "IDENTITY_SOCIAL_FIXTURE_ALIPAY_USER_INFO_URL": "https://fixture.local/identity/alipay/user",
    "IDENTITY_SOCIAL_FIXTURE_QQ_USER_INFO_URL": "https://fixture.local/identity/qq/user",
    "IDENTITY_SOCIAL_FIXTURE_WECHAT_APP_ID": "",
    "IDENTITY_SOCIAL_FIXTURE_WECHAT_APP_SECRET": "",
    "IDENTITY_SOCIAL_FIXTURE_ALIPAY_APP_ID": "",
    "IDENTITY_SOCIAL_FIXTURE_ALIPAY_APP_PRIVATE_KEY_PEM": "FIXTURE_PRIVATE_KEY",
    "IDENTITY_SOCIAL_FIXTURE_ALIPAY_PLATFORM_PUBLIC_KEY_PEM": "FIXTURE_PUBLIC_KEY",
    "IDENTITY_SOCIAL_FIXTURE_ALIPAY_MERCHANT_PID": "",
    "IDENTITY_SOCIAL_FIXTURE_QQ_APP_ID": "",
}

# Object-storage credentials are owned by local_environment_object_storage and must
# stay aligned with MinIO; never invent a second CONTENT_OSS_* material set here.
_PLATFORM_OWNED_KEYS = frozenset(
    {
        "CONTENT_OSS_ENDPOINT",
        "CONTENT_OSS_ACCESS_KEY_ID",
        "CONTENT_OSS_ACCESS_KEY_SECRET",
        "CONTENT_OSS_BUCKET",
        "CONTENT_OSS_REGION",
        "CONTENT_CDN_DOMAIN",
        "CONTENT_CDN_SIGN_KEY",
    }
)


def prepare_local_provider_credentials(
    *,
    environment: str,
    target_name: str,
) -> dict[str, str]:
    """Materialize Alpha/Beta substitute secrets under the deploy work root."""
    if environment not in SUBSTITUTE_ENVIRONMENTS:
        raise ValueError(
            "auto-generated local Provider credentials are only for Alpha/Beta "
            f"substitute environments, got {environment}"
        )
    if not target_name.endswith("-local"):
        raise ValueError(f"local provider target must end with -local: {target_name}")

    work_root = deployment_work_root(target_name)
    if work_root.resolve() == Path.cwd().resolve() or ".qwq_output" in work_root.parts:
        raise RuntimeError(
            "provider credentials must not be written into the repository or .qwq_output"
        )

    secret_path = deployment_target_path(
        target_name,
        "secrets",
        "external-providers.env",
    )
    required_keys = _required_keys_for_environment(environment)
    values = _load_or_create_secrets(secret_path, required_keys)
    return values


def _required_keys_for_environment(environment: str) -> list[str]:
    bindings = load_bindings()
    scope = bindings["environments"][environment]
    keys: set[str] = set()
    for service_bindings in scope.values():
        if not isinstance(service_bindings, Mapping):
            continue
        for binding in service_bindings.values():
            if not isinstance(binding, Mapping):
                continue
            if binding.get("state") != "enabled":
                continue
            adapter_id = str(binding.get("adapter") or "")
            if not adapter_id or not is_local_substitute_adapter(adapter_id):
                continue
            for env_key in (binding.get("secretRefs") or []):
                key = str(env_key)
                if key not in _PLATFORM_OWNED_KEYS:
                    keys.add(key)
            endpoint_envs = binding.get("endpointEnvs") or {}
            if isinstance(endpoint_envs, Mapping):
                for env_key in endpoint_envs.values():
                    key = str(env_key)
                    if key not in _PLATFORM_OWNED_KEYS:
                        keys.add(key)
    # Include fixture defaults referenced by Alpha/Beta templates.
    keys.update(_DEFAULT_VALUES)
    return sorted(keys)


def _load_or_create_secrets(path: Path, required_keys: list[str]) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    with _exclusive_lock(path.parent / ".external-provider-secrets.lock"):
        existing: dict[str, str] = {}
        if path.is_file():
            _require_mode(path, 0o600, "external provider secret file")
            existing = _read_secret_file(path)
        elif path.exists():
            raise RuntimeError(f"external provider secret path is not a file: {path}")

        values = dict(existing)
        changed = False
        for key in required_keys:
            if values.get(key):
                continue
            values[key] = _default_or_generate(key)
            changed = True
        if changed or not path.is_file():
            _write_secret_file(path, values)
        return {key: values[key] for key in required_keys if values.get(key)}


def _default_or_generate(key: str) -> str:
    default = _DEFAULT_VALUES.get(key)
    if default:
        return default
    if key.endswith("_PEM"):
        return "FIXTURE_PEM_MATERIAL"
    if "ENDPOINT" in key or "URL" in key:
        return f"https://fixture.local/{key.lower()}"
    if key.endswith("_ID"):
        return "fixture-" + secrets.token_hex(4)
    return secrets.token_urlsafe(24)


def _write_secret_file(path: Path, values: Mapping[str, str]) -> None:
    fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for key in sorted(values):
                handle.write(f"{key}={values[key]}\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    os.chmod(path, 0o600)


def _read_secret_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator != "=" or not key:
            raise RuntimeError(
                f"external provider secret file is malformed at line {line_number}"
            )
        values[key.strip()] = value
    return values


def _require_mode(path: Path, mode: int, label: str) -> None:
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != mode:
        raise RuntimeError(f"{label} must have mode {oct(mode)}, got {oct(actual)}")
    if path.is_symlink():
        raise RuntimeError(f"{label} must not be a symlink")


@contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)
