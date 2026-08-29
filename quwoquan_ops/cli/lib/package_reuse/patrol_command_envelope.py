"""Sealed Flutter command identity for one immutable Patrol projection.

The expectation that owns this envelope is mode ``0600``.  Consumers may
publish only :func:`patrol_command_envelope_digest`; the executable and PATH
remain private build/UAT inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_app.scripts.tools.flutter_facade.flutter_facade import (
    FacadeError,
    resolved_flutter_identity,
)

from .android_gradle_capsule import canonical_bytes, digest_bytes

PATROL_COMMAND_ENVELOPE_SCHEMA = "stackctl-patrol-command-envelope.v1"
PATROL_COMMAND_ENVELOPE_DIGEST_ENV = "QWQ_PATROL_COMMAND_ENVELOPE_DIGEST"
PATROL_REAL_FLUTTER_ENV = "QWQ_PATROL_REAL_FLUTTER"
REAL_FLUTTER_ENV = "QWQ_REAL_FLUTTER"
FLUTTER_VERSION_ENV = "QWQ_FLUTTER_VERSION"
COMMAND_RESOLUTION_DIGEST_ENV = "QWQ_COMMAND_RESOLUTION_DIGEST"
PROXY_ENVIRONMENT_KEYS = (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
)
DEPENDENCY_ENVIRONMENT_KEYS = (
    "PUB_CACHE",
    "GRADLE_USER_HOME",
    "CP_HOME_DIR",
    "CP_CACHE_DIR",
    "COCOAPODS_HOME",
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "FLUTTER_SWIFT_PACKAGE_MANAGER",
    "COCOAPODS_DISABLE_STATS",
    "COCOAPODS_SKIP_UPDATE_MESSAGE",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_TERMINAL_PROMPT",
)
HOST_ENVIRONMENT_KEYS = (
    "ANDROID_HOME",
    "ANDROID_SDK_ROOT",
    "JAVA_HOME",
    "DEVELOPER_DIR",
    "SDKROOT",
    "TOOLCHAINS",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TMP",
    "TEMP",
    "PYTHONPYCACHEPREFIX",
)
_DIGEST_PREFIX = "sha256:"
_ENVELOPE_FIELDS = {
    "schema",
    "flutterExecutable",
    "flutterVersion",
    "commandResolutionDigest",
    "path",
    "requiredAbsentProxyKeys",
    "dependencyEnvironment",
    "hostEnvironment",
}
_RESERVED_ENVIRONMENT_KEYS = frozenset(
    {
        "PATH",
        "FLUTTER_ROOT",
        REAL_FLUTTER_ENV,
        PATROL_REAL_FLUTTER_ENV,
        FLUTTER_VERSION_ENV,
        COMMAND_RESOLUTION_DIGEST_ENV,
        PATROL_COMMAND_ENVELOPE_DIGEST_ENV,
    }
)
_RUNTIME_COMMAND_ENVIRONMENT_KEYS = frozenset(
    {
        "TEST_AUTH_TOKEN",
        "TEST_REFRESH_TOKEN",
        "APP_CURRENT_OWNER_ID",
        "APP_CURRENT_PERSONA_ID",
        "QWQ_EXTERNAL_AUT_CANONICAL_BINDING_B64",
        "QWQ_APP_CONTENT_VIDEO_PAGE_COUNT",
        "QWQ_APP_CONTENT_PROFILE_P0_ONLY",
        "QWQ_PROVIDER_UAT_DART_DEFINE_KEYS",
        "QWQ_DEPLOY_TARGET",
        "QWQ_APP_RUNTIME_ENV",
        "QWQ_TEST_DATA_ACCESS_TOKEN",
        "QWQ_TEST_DATA_REFRESH_TOKEN",
        "QWQ_TEST_DATA_OWNER_ID",
        "QWQ_TEST_DATA_PERSONA_ID",
        "QWQ_TEST_DATA_CONVERSATION_ID",
        "QWQ_TEST_DATA_MESSAGE_IDS_JSON",
        "QWQ_TEST_DATA_PRIMARY_ACCESS_TOKEN",
        "QWQ_TEST_DATA_PRIMARY_REFRESH_TOKEN",
        "QWQ_TEST_DATA_PRIMARY_OWNER_ID",
        "QWQ_TEST_DATA_PRIMARY_PERSONA_ID",
    }
)


def _is_digest(value: object) -> bool:
    raw = str(value or "")
    return (
        len(raw) == 71
        and raw.startswith(_DIGEST_PREFIX)
        and all(character in "0123456789abcdef" for character in raw[7:])
    )


def _literal_absolute_path(value: object, *, label: str) -> str:
    raw = str(value or "")
    path = Path(raw)
    if (
        not raw
        or not path.is_absolute()
        or str(path) != raw
        or any(part in {"", ".", ".."} for part in path.parts[1:])
    ):
        raise ValueError(f"{label} is not a literal absolute path")
    return raw


def patrol_command_envelope(
    *,
    flutter_identity: Mapping[str, str],
    path: str,
    dependency_environment: Mapping[str, str] | None = None,
    host_environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build canonical envelope bytes from an already resolved facade identity."""

    executable = _literal_absolute_path(
        flutter_identity.get("executable"),
        label="Patrol Flutter executable",
    )
    flutter_version = str(flutter_identity.get("flutterVersion") or "").strip()
    resolution_digest = str(
        flutter_identity.get("commandResolutionDigest") or ""
    ).strip()
    if not flutter_version or not _is_digest(resolution_digest):
        raise ValueError("Patrol Flutter identity is incomplete")
    if not isinstance(path, str) or not path:
        raise ValueError("Patrol sealed PATH is empty")
    envelope = {
        "schema": PATROL_COMMAND_ENVELOPE_SCHEMA,
        "flutterExecutable": executable,
        "flutterVersion": flutter_version,
        "commandResolutionDigest": resolution_digest,
        "path": path,
        "requiredAbsentProxyKeys": list(PROXY_ENVIRONMENT_KEYS),
        "dependencyEnvironment": dict(dependency_environment or {}),
        "hostEnvironment": dict(host_environment or {}),
    }
    validate_patrol_command_envelope(envelope)
    return envelope


def build_patrol_command_envelope(
    environment: Mapping[str, str],
) -> dict[str, Any]:
    """Resolve and seal the one Flutter command selected by a private projection."""

    present_proxy = next(
        (key for key in PROXY_ENVIRONMENT_KEYS if key in environment),
        "",
    )
    if present_proxy:
        raise ValueError("Patrol dependency environment contains a proxy key")
    try:
        identity = resolved_flutter_identity(dict(environment))
    except (FacadeError, OSError, TypeError, ValueError) as error:
        raise ValueError("Patrol Flutter command identity is invalid") from error
    return patrol_command_envelope(
        flutter_identity=identity,
        path=str(environment.get("PATH") or ""),
        dependency_environment={
            key: str(environment[key])
            for key in DEPENDENCY_ENVIRONMENT_KEYS
            if key in environment
        },
        host_environment={
            key: str(environment[key])
            for key in HOST_ENVIRONMENT_KEYS
            if key in environment
        },
    )


def validate_patrol_command_envelope(value: object) -> Mapping[str, Any]:
    """Validate historical/private envelope structure without probing the host SDK."""

    if not isinstance(value, Mapping) or set(value) != _ENVELOPE_FIELDS:
        raise ValueError("Patrol command envelope fields drifted")
    if (
        value.get("schema") != PATROL_COMMAND_ENVELOPE_SCHEMA
        or not str(value.get("flutterVersion") or "").strip()
        or not _is_digest(value.get("commandResolutionDigest"))
        or not isinstance(value.get("path"), str)
        or not value.get("path")
        or value.get("requiredAbsentProxyKeys") != list(PROXY_ENVIRONMENT_KEYS)
        or not isinstance(value.get("dependencyEnvironment"), Mapping)
        or not isinstance(value.get("hostEnvironment"), Mapping)
    ):
        raise ValueError("Patrol command envelope identity drifted")
    dependency_environment = value["dependencyEnvironment"]
    host_environment = value["hostEnvironment"]
    if (
        any(key not in DEPENDENCY_ENVIRONMENT_KEYS for key in dependency_environment)
        or any(not isinstance(item, str) for item in dependency_environment.values())
        or any(key not in HOST_ENVIRONMENT_KEYS for key in host_environment)
        or any(not isinstance(item, str) for item in host_environment.values())
    ):
        raise ValueError("Patrol command envelope environment drifted")
    _literal_absolute_path(
        value.get("flutterExecutable"),
        label="Patrol Flutter executable",
    )
    return value


def patrol_command_envelope_digest(value: object) -> str:
    envelope = validate_patrol_command_envelope(value)
    return digest_bytes(canonical_bytes(envelope))


def _sealed_environment_values(envelope: Mapping[str, Any]) -> dict[str, str]:
    executable = str(envelope["flutterExecutable"])
    return {
        "PATH": str(envelope["path"]),
        "FLUTTER_ROOT": str(Path(executable).parent.parent),
        REAL_FLUTTER_ENV: executable,
        PATROL_REAL_FLUTTER_ENV: executable,
        FLUTTER_VERSION_ENV: str(envelope["flutterVersion"]),
        COMMAND_RESOLUTION_DIGEST_ENV: str(envelope["commandResolutionDigest"]),
        PATROL_COMMAND_ENVELOPE_DIGEST_ENV: patrol_command_envelope_digest(envelope),
    }


def _runtime_command_key_allowed(key: str) -> bool:
    return key in _RUNTIME_COMMAND_ENVIRONMENT_KEYS


def rebuild_patrol_command_environment(
    *,
    envelope: object,
    ambient_environment: Mapping[str, str],
    dependency_environment: Mapping[str, str],
    command_environment: Mapping[str, str],
) -> dict[str, str]:
    """Rebuild an effective command env without ambient PATH/proxy selection."""

    validated = validate_patrol_command_envelope(envelope)
    if not isinstance(ambient_environment, Mapping):
        raise TypeError("Patrol ambient environment is invalid")
    if any(key in command_environment for key in PROXY_ENVIRONMENT_KEYS):
        raise ValueError("Patrol command overlay contains a proxy key")
    sealed = _sealed_environment_values(validated)
    expected_dependency = {
        str(key): str(value)
        for key, value in validated["dependencyEnvironment"].items()
    }
    expected_host = {
        str(key): str(value) for key, value in validated["hostEnvironment"].items()
    }
    if dict(dependency_environment) != expected_dependency:
        raise ValueError("Patrol dependency command environment drifted")
    expected_reserved = {**expected_dependency, **expected_host, **sealed}
    for key in {*_RESERVED_ENVIRONMENT_KEYS, *expected_dependency, *expected_host}:
        supplied = command_environment.get(key)
        if supplied is not None and supplied != expected_reserved[key]:
            raise ValueError(
                "Patrol command overlay conflicts with its sealed toolchain"
            )
    unexpected = next(
        (
            key
            for key in command_environment
            if key not in expected_reserved and not _runtime_command_key_allowed(key)
        ),
        "",
    )
    if unexpected:
        raise ValueError("Patrol command overlay contains an ungoverned key")
    result = {
        **expected_host,
        **expected_dependency,
        **{key: "" for key in _RUNTIME_COMMAND_ENVIRONMENT_KEYS},
    }
    result.update(
        {
            key: str(value)
            for key, value in command_environment.items()
            if _runtime_command_key_allowed(key)
        }
    )
    result.update(sealed)
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    validate_patrol_command_environment(result)
    return result


def validate_patrol_command_environment(
    environment: Mapping[str, str],
) -> dict[str, str]:
    """Probe the actual SDK and match it to every field of the sealed envelope."""

    if any(key in environment for key in PROXY_ENVIRONMENT_KEYS):
        raise ValueError("Patrol effective command environment contains a proxy key")
    reconstructed = patrol_command_envelope(
        flutter_identity={
            "executable": str(environment.get(REAL_FLUTTER_ENV) or ""),
            "flutterVersion": str(environment.get(FLUTTER_VERSION_ENV) or ""),
            "commandResolutionDigest": str(
                environment.get(COMMAND_RESOLUTION_DIGEST_ENV) or ""
            ),
        },
        path=str(environment.get("PATH") or ""),
        dependency_environment={
            key: str(environment[key])
            for key in DEPENDENCY_ENVIRONMENT_KEYS
            if key in environment
        },
        host_environment={
            key: str(environment[key])
            for key in HOST_ENVIRONMENT_KEYS
            if key in environment
        },
    )
    if environment.get(PATROL_REAL_FLUTTER_ENV) != reconstructed["flutterExecutable"]:
        raise ValueError("Patrol proxy Flutter executable drifted")
    if environment.get(PATROL_COMMAND_ENVELOPE_DIGEST_ENV) != (
        patrol_command_envelope_digest(reconstructed)
    ):
        raise ValueError("Patrol command envelope digest drifted")
    try:
        actual = resolved_flutter_identity(dict(environment))
    except (FacadeError, OSError, TypeError, ValueError) as error:
        raise ValueError("Patrol actual Flutter command identity is invalid") from error
    expected = {
        "executable": str(reconstructed["flutterExecutable"]),
        "flutterVersion": str(reconstructed["flutterVersion"]),
        "commandResolutionDigest": str(reconstructed["commandResolutionDigest"]),
    }
    if actual != expected:
        raise ValueError("Patrol actual Flutter command identity drifted")
    return expected


def strip_proxy_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Remove both cases of every admitted proxy variable before validation/use."""

    return {
        key: str(value)
        for key, value in environment.items()
        if key not in PROXY_ENVIRONMENT_KEYS
    }


def closed_patrol_child_environment(
    environment: Mapping[str, str],
) -> dict[str, str]:
    """Select only sealed build inputs and explicit Patrol runtime handoff keys."""

    sanitized = strip_proxy_environment(environment)
    validate_patrol_command_environment(sanitized)
    selected_keys = {
        *_RESERVED_ENVIRONMENT_KEYS,
        *DEPENDENCY_ENVIRONMENT_KEYS,
        *HOST_ENVIRONMENT_KEYS,
    }
    result = {
        key: str(value)
        for key, value in sanitized.items()
        if key in selected_keys or _runtime_command_key_allowed(key)
    }
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    validate_patrol_command_environment(result)
    return result
