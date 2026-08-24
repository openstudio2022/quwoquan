"""Canonical App 安装后 activation 与 CAS 回执状态机。"""

from __future__ import annotations

import json
import re
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    build_runtime_config_activation_request,
    runtime_config_activation_request_digest,
    validate_runtime_config_activation_receipt,
)

# typed 失败定义在叶子模块，launcher 参数预检无需引入本模块的契约依赖链。
from .arguments import CanonicalExecutorError


REQUEST_FILE_NAME = "runtime-config-activation-request.json"
RECEIPT_FILE_NAME = "runtime-config-activation-receipt.json"
ACTIVE_RECEIPT_FILE_NAME = "runtime-config-active-receipt.json"
MAXIMUM_RUNTIME_DOCUMENT_BYTES = 1024 * 1024
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "status",
        "requestDigest",
        "environment",
        "buildProfile",
        "target",
        "packageDigest",
        "trustEnvelopeDigest",
        "effectiveLaunchManifestDigest",
        "previousActiveDigest",
        "activePackageDigest",
        "errorCode",
        "validationIssues",
    }
)

FORBIDDEN_COMPILE_ENVIRONMENT_KEYS = frozenset(
    {
        "DART_DEFINES",
        "QWQ_ENVIRONMENT",
        "QWQ_APP_RUNTIME_ENV",
        "QWQ_APP_RUN_MODE",
        "QWQ_APP_LAUNCH_MODE",
        "QWQ_APP_LAUNCH_POLICY",
        "QWQ_LAUNCH_TARGET",
        "QWQ_LAUNCH_HANDOFF_JSON",
        "QWQ_RUNTIME_CONFIG_PACKAGE_JSON",
        "QWQ_RUNTIME_CONFIG_PACKAGE_DIGEST",
        "QWQ_RUNTIME_CONFIG_TRUST_ENVELOPE_DIGEST",
        "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
        "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
        "QWQ_APP_RUNTIME_CONFIG_PACKAGE_PATH",
        "QWQ_IOS_RUNTIME_CONFIG_PACKAGE_PATH",
        "QWQ_APP_RUNTIME_CONFIG_TRUST_PATH",
        "QWQ_APP_RUNTIME_CONFIG_SIGNING_KEY_ID",
        "QWQ_APP_RUNTIME_CONFIG_SIGNING_PRIVATE_KEY_FILE",
        "QWQ_APP_RUNTIME_CONFIG_TRUSTED_PUBLIC_KEYS_FILE",
        "QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON",
        "QWQ_ANDROID_RELEASE_*",
        "QWQ_CONTENT_*",
        "QWQ_CONSUMER_*",
        "QWQ_ANDROID_LOCAL_*",
        "ANDROID_LOCAL_*",
    }
)


class PlatformDriver(Protocol):
    def build(self, environment: dict[str, str]) -> None: ...

    def install(self) -> None: ...

    def read_runtime_file(self, file_name: str) -> bytes | None: ...

    def write_activation_request(self, payload: bytes) -> None: ...

    def launch_activation(self, request_digest: str) -> None: ...

    def launch_application(self) -> None: ...

    def attach(
        self,
        attach_arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        on_attached: Callable[[], None],
    ) -> int: ...


class CanonicalLaunchExecutor:
    def __init__(
        self,
        *,
        handoff: dict[str, object],
        platform_driver: PlatformDriver,
        inherited_environment: Mapping[str, str],
        attach_arguments: tuple[str, ...],
        activation_timeout_seconds: float,
        attach_timeout_seconds: float,
        emit: Callable[[str], None],
    ) -> None:
        self.handoff = handoff
        self.platform_driver = platform_driver
        self.inherited_environment = inherited_environment
        self.attach_arguments = attach_arguments
        self.activation_timeout_seconds = activation_timeout_seconds
        self.attach_timeout_seconds = attach_timeout_seconds
        self.emit = emit

    def execute(self) -> int:
        self.platform_driver.build(compile_environment(self.inherited_environment))
        self._emit_phase("compiled")
        self._emit_phase("installing")
        self.platform_driver.install()
        self._emit_phase("installed")
        self._emit_phase("configuring")

        expected_active_digest = self._read_expected_active_digest()
        request = build_runtime_config_activation_request(
            self.handoff,
            expected_active_digest=expected_active_digest,
        )
        request_digest = runtime_config_activation_request_digest(request)
        self.platform_driver.write_activation_request(canonical_json_bytes(request))
        self.platform_driver.launch_activation(request_digest)
        activated_receipt = self._wait_for_current_activation_receipt(
            request,
            request_digest,
        )
        active_receipt_payload = self.platform_driver.read_runtime_file(
            ACTIVE_RECEIPT_FILE_NAME
        )
        if active_receipt_payload is None:
            raise CanonicalExecutorError(
                "native activation committed no active activation receipt"
            )
        active_receipt = decode_activation_receipt(
            active_receipt_payload,
            label="active activation receipt",
        )
        active_issues = validate_runtime_config_activation_receipt(
            active_receipt,
            request,
        )
        if active_issues or active_receipt != activated_receipt:
            details = "; ".join(active_issues) or "active receipt differs from launch receipt"
            raise CanonicalExecutorError(
                f"native active activation receipt is inconsistent: {details}"
            )
        self._emit_phase("configured")

        self._emit_phase("launching")
        self.platform_driver.launch_application()
        attached = False

        def mark_attached() -> None:
            nonlocal attached
            if not attached:
                attached = True
                self._emit_phase("launched")

        return self.platform_driver.attach(
            self.attach_arguments,
            timeout_seconds=self.attach_timeout_seconds,
            on_attached=mark_attached,
        )

    def _read_expected_active_digest(self) -> str:
        payload = self.platform_driver.read_runtime_file(ACTIVE_RECEIPT_FILE_NAME)
        if payload is None:
            return ""
        receipt = decode_activation_receipt(
            payload,
            label="active activation receipt",
        )
        if receipt["status"] != "activated":
            raise CanonicalExecutorError(
                "active activation receipt does not record activated status"
            )
        return str(receipt["activePackageDigest"])

    def _wait_for_current_activation_receipt(
        self,
        request: dict[str, object],
        request_digest: str,
    ) -> dict[str, object]:
        deadline = time.monotonic() + self.activation_timeout_seconds
        while time.monotonic() < deadline:
            payload = self.platform_driver.read_runtime_file(RECEIPT_FILE_NAME)
            if payload is None:
                time.sleep(0.1)
                continue
            receipt = decode_activation_receipt(
                payload,
                label="activation receipt",
            )
            if receipt["requestDigest"] != request_digest:
                time.sleep(0.1)
                continue
            issues = validate_runtime_config_activation_receipt(receipt, request)
            if issues:
                raise CanonicalExecutorError(
                    "native activation receipt failed validation: " + "; ".join(issues)
                )
            if receipt["status"] != "activated":
                error_code = str(receipt.get("errorCode") or "unknown")
                raise CanonicalExecutorError(
                    f"native runtime configuration activation failed: {error_code}"
                )
            return receipt
        raise CanonicalExecutorError(
            "native activation receipt was not bound to the current request "
            f"within {self.activation_timeout_seconds:g}s"
        )

    def _emit_phase(self, phase: str) -> None:
        self.emit(f"QWQ_APP_LAUNCH_PHASE status={phase}")


def canonical_json_bytes(document: object) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def decode_activation_receipt(
    payload: bytes,
    *,
    label: str,
) -> dict[str, object]:
    payload = bounded_payload(payload, label)
    try:
        text = payload.decode("utf-8")
        decoded = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CanonicalExecutorError(f"{label} is malformed: {error}") from error
    if not isinstance(decoded, dict) or set(decoded) != RECEIPT_FIELDS:
        raise CanonicalExecutorError(f"{label} fields are invalid")
    if canonical_json_bytes(decoded) != payload:
        raise CanonicalExecutorError(f"{label} is not canonical JSON")
    if (
        decoded.get("schema") != "app-runtime-config-activation-receipt"
        or decoded.get("status") not in {"activated", "failed"}
    ):
        raise CanonicalExecutorError(f"{label} identity is invalid")
    digest_fields = (
        "requestDigest",
        "packageDigest",
        "trustEnvelopeDigest",
        "effectiveLaunchManifestDigest",
        "activePackageDigest",
    )
    for field in digest_fields:
        value = decoded.get(field)
        if decoded["status"] == "failed" and value == "":
            continue
        if not _is_digest(value):
            raise CanonicalExecutorError(f"{label} {field} is invalid")
    previous = decoded.get("previousActiveDigest")
    if previous != "" and not _is_digest(previous):
        raise CanonicalExecutorError(f"{label} previousActiveDigest is invalid")
    if not isinstance(decoded.get("validationIssues"), list) or not all(
        isinstance(item, str) and item for item in decoded["validationIssues"]
    ):
        raise CanonicalExecutorError(f"{label} validationIssues is invalid")
    for field in ("environment", "buildProfile", "target", "errorCode"):
        if not isinstance(decoded.get(field), str):
            raise CanonicalExecutorError(f"{label} {field} is invalid")
    if decoded["status"] == "activated":
        if (
            not decoded["environment"]
            or not decoded["buildProfile"]
            or not decoded["target"]
            or decoded["activePackageDigest"] != decoded["packageDigest"]
            or decoded["errorCode"] != ""
            or decoded["validationIssues"] != []
        ):
            raise CanonicalExecutorError(f"{label} activated state is invalid")
    return decoded


def compile_environment(inherited: Mapping[str, str]) -> dict[str, str]:
    environment = {str(key): str(value) for key, value in inherited.items()}
    for forbidden in FORBIDDEN_COMPILE_ENVIRONMENT_KEYS:
        if forbidden.endswith("*"):
            prefix = forbidden[:-1]
            for key in tuple(environment):
                if key.startswith(prefix):
                    environment.pop(key, None)
        else:
            environment.pop(forbidden, None)
    return environment


def bounded_payload(payload: bytes, label: str) -> bytes:
    if not payload or len(payload) > MAXIMUM_RUNTIME_DOCUMENT_BYTES:
        raise CanonicalExecutorError(
            f"{label} must contain 1..{MAXIMUM_RUNTIME_DOCUMENT_BYTES} bytes"
        )
    return payload


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and DIGEST_PATTERN.fullmatch(value) is not None
