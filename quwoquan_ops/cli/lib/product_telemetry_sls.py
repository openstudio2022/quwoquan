from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_LOCAL_TARGETS = {"beta": "beta-local", "gamma": "gamma-local"}
_REQUIRED_KEYS = (
    "PRODUCT_OPS_SLS_REGION",
    "PRODUCT_OPS_SLS_ENDPOINT",
    "PRODUCT_OPS_SLS_PROJECT",
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
)
_OPTIONAL_KEYS = ("ALIBABA_CLOUD_SECURITY_TOKEN",)
_FILE_OVERRIDE_ENV = "QWQ_PRODUCT_TELEMETRY_SLS_ENV_FILE"


@dataclass(frozen=True)
class ProductTelemetrySLS:
    environment: dict[str, str]
    secret_path: Path | None


def load_product_telemetry_sls(
    environment: str,
    target_name: str,
    *,
    process_environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> ProductTelemetrySLS:
    """Load the real SLS deployment bundle without copying it into runtime output."""
    expected_target = _LOCAL_TARGETS.get(environment)
    if expected_target != target_name:
        raise ValueError(
            f"unsupported product telemetry target: {environment}/{target_name}"
        )

    source = os.environ if process_environment is None else process_environment
    present = {
        key: source.get(key, "").strip()
        for key in (*_REQUIRED_KEYS, *_OPTIONAL_KEYS)
    }
    if all(present[key] for key in _REQUIRED_KEYS):
        return ProductTelemetrySLS(
            environment={key: value for key, value in present.items() if value},
            secret_path=None,
        )

    configured_path = source.get(_FILE_OVERRIDE_ENV, "").strip()
    base_home = Path.home() if home is None else home
    secret_path = (
        Path(configured_path).expanduser()
        if configured_path
        else base_home
        / ".config"
        / "quwoquan"
        / "product_telemetry_sls"
        / f"{environment}.env"
    )
    if not secret_path.is_file():
        raise RuntimeError(
            "product telemetry SLS deployment secret is missing: " + str(secret_path)
        )
    _require_mode(secret_path, 0o600)
    file_values = _read_secret_file(secret_path)
    merged = {**file_values, **{key: value for key, value in present.items() if value}}
    missing = [key for key in _REQUIRED_KEYS if not merged.get(key, "").strip()]
    if missing:
        raise RuntimeError(
            "product telemetry SLS deployment secret is incomplete: "
            + ", ".join(missing)
        )
    return ProductTelemetrySLS(
        environment={
            key: merged[key].strip()
            for key in (*_REQUIRED_KEYS, *_OPTIONAL_KEYS)
            if merged.get(key, "").strip()
        },
        secret_path=secret_path,
    )


def _read_secret_file(path: Path) -> dict[str, str]:
    allowed = frozenset((*_REQUIRED_KEYS, *_OPTIONAL_KEYS))
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not separator or key not in allowed or not value:
            raise RuntimeError(
                f"invalid product telemetry SLS deployment secret at {path}:{line_number}"
            )
        if key in values:
            raise RuntimeError(
                f"duplicate product telemetry SLS key at {path}:{line_number}"
            )
        values[key] = value
    return values


def _require_mode(path: Path, expected: int) -> None:
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected:
        raise RuntimeError(
            f"product telemetry SLS deployment secret must use mode {expected:04o}: {path}"
        )
