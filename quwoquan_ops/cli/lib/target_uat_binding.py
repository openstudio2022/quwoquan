"""Ops-owned create-once ``TargetUatBinding`` authoring primitives.

The library is intentionally detached from ``app-preflight-uat`` orchestration.
Callers supply already-verified runtime, launch, active-CAS/readback, device and
runner facts; this module never discovers a latest target, release, or device.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "environments"
    / "evidence"
    / "target_uat_binding.schema.json"
)
TARGET_UAT_BINDING_SCHEMA = "quwoquan_ops.target_uat_binding.v1"
TARGET_UAT_BINDING_DIRECTORY = "target-uat-bindings"
TARGET_UAT_BINDING_KEYS = frozenset(
    {
        "schema",
        "bindingId",
        "releaseId",
        "releaseDigest",
        "releaseUatSamplePlanRef",
        "releaseUatSamplePlanDigest",
        "environment",
        "target",
        "candidateDigest",
        "packageDigest",
        "configurationDigest",
        "runtimeConfigDigest",
        "environmentRuntimeDigest",
        "activeCas",
        "readback",
        "artifact",
        "platform",
        "provider",
        "device",
        "runner",
        "profile",
        "nonPromotable",
        "createdAt",
    }
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,255}$")
_REF_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
_PLATFORMS = frozenset({"android", "ios"})
_DEVICE_CLASSES = frozenset({"physical", "emulator", "simulator"})
_PROFILES = frozenset({"rehearsal", "promotable", "production"})
_ARTIFACT_CLASSES = frozenset({"production_behavior", "production"})
_BUILD_MODES = frozenset({"debug", "profile", "release"})
_BUILD_PROFILES = frozenset({"nonprod", "prod"})
_SOURCE_KEYS = frozenset({"ref", "digest"})
_ARTIFACT_KEYS = frozenset(
    {"class", "digest", "applicationId", "buildMode", "buildProfile"}
)
_PROVIDER_CLASSES = frozenset({"first_party", "external", "test_fixture"})
_PROVIDER_KEYS = frozenset(
    {"identity", "class", "type", "registered", "conformanceEvidence"}
)
_DEVICE_KEYS = frozenset({"identity", "class", "registered"})
_RUNNER_KEYS = frozenset({"identity", "sourcePath", "digest", "registered"})

_INVALID = "OPS.TARGET_UAT_BINDING.invalid"
_STALE = "OPS.TARGET_UAT_BINDING.stale"
_CONFLICT = "OPS.TARGET_UAT_BINDING.create_once_conflict"
_PATH_INVALID = "OPS.TARGET_UAT_BINDING.path_invalid"


class TargetUatBindingError(ValueError):
    """Typed fail-closed TargetUatBinding error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class TargetUatBindingWriteResult:
    """Identity returned by one create-once write or exact-byte replay."""

    path: Path
    ref: str
    digest: str
    binding: dict[str, Any]
    created: bool


def _error(detail: str, *, code: str = _INVALID) -> TargetUatBindingError:
    return TargetUatBindingError(code, detail)


def _strict_object(
    value: object, *, field: str, keys: frozenset[str]
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _error(f"{field} must be an object with string keys")
    observed = set(value)
    missing = keys - observed
    unknown = observed - keys
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing={sorted(missing)}")
        if unknown:
            details.append(f"unknown={sorted(unknown)}")
        raise _error(f"{field} fields drifted: " + ", ".join(details))
    return dict(value)


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _error(f"{field} must be a non-empty canonical string")
    if _URL_RE.match(value):
        raise _error(f"{field} must not contain a URL")
    return value


def _identity(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if _IDENTITY_RE.fullmatch(text) is None:
        raise _error(f"{field} has invalid identity format")
    return text


def _digest(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if _DIGEST_RE.fullmatch(text) is None:
        raise _error(f"{field} must be sha256:<64 lowercase hex>")
    return text


def _relative_ref(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if "\\" in text or text.startswith("/"):
        raise _error(f"{field} must be a contained relative reference")
    reference = PurePosixPath(text)
    if (
        len(text) > 512
        or reference.as_posix() != text
        or text in {".", ".."}
        or any(
            part in {"", ".", ".."} or _REF_SEGMENT_RE.fullmatch(part) is None
            for part in reference.parts
        )
    ):
        raise _error(f"{field} must be a contained relative reference")
    return text


def _boolean(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise _error(f"{field} must be boolean")
    return value


def _created_at(value: object) -> str:
    text = _text(value, field="createdAt")
    if _RFC3339_RE.fullmatch(text) is None:
        raise _error("createdAt must be an RFC3339 date-time with an explicit offset")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise _error("createdAt must be a valid RFC3339 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error("createdAt must include an explicit offset")
    return text


def _canonical_json_bytes(value: Mapping[str, Any], *, newline: bool) -> bytes:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return encoded + (b"\n" if newline else b"")


def target_uat_binding_slot_identity(
    *,
    target: str,
    release_id: str,
    release_digest: str,
    platform: str,
    provider: Mapping[str, Any],
    device_identity: str,
    profile: str,
    runner: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the exact closed slot identity used to derive ``bindingId``."""

    normalized_provider = _validate_provider(provider)
    runner_value = _strict_object(runner, field="runner", keys=_RUNNER_KEYS)
    normalized_runner = {
        "identity": _identity(runner_value["identity"], field="runner.identity"),
        "sourcePath": _relative_ref(
            runner_value["sourcePath"], field="runner.sourcePath"
        ),
        "digest": _digest(runner_value["digest"], field="runner.digest"),
        "registered": _boolean(
            runner_value["registered"], field="runner.registered"
        ),
    }
    normalized_profile = _text(profile, field="profile")
    if normalized_profile not in _PROFILES:
        raise _error("profile must be rehearsal, promotable, or production")
    normalized_platform = _text(platform, field="platform")
    if normalized_platform not in _PLATFORMS:
        raise _error("platform must be android or ios")
    return {
        "target": _identity(target, field="target"),
        "release": {
            "id": _identity(release_id, field="releaseId"),
            "digest": _digest(release_digest, field="releaseDigest"),
        },
        "platform": normalized_platform,
        "provider": normalized_provider,
        "deviceIdentity": _identity(device_identity, field="device.identity"),
        "profile": normalized_profile,
        "runner": normalized_runner,
    }


def target_uat_binding_id(
    *,
    target: str,
    release_id: str,
    release_digest: str,
    platform: str,
    provider: Mapping[str, Any],
    device_identity: str,
    profile: str,
    runner: Mapping[str, Any],
) -> str:
    """Derive the binding identity from the exact target UAT slot."""

    slot = target_uat_binding_slot_identity(
        target=target,
        release_id=release_id,
        release_digest=release_digest,
        platform=platform,
        provider=provider,
        device_identity=device_identity,
        profile=profile,
        runner=runner,
    )
    return (
        "sha256:"
        + hashlib.sha256(_canonical_json_bytes(slot, newline=False)).hexdigest()
    )


def _validate_source(value: object, *, field: str) -> dict[str, str]:
    source = _strict_object(value, field=field, keys=_SOURCE_KEYS)
    return {
        "ref": _relative_ref(source["ref"], field=f"{field}.ref"),
        "digest": _digest(source["digest"], field=f"{field}.digest"),
    }


def _validate_artifact(value: object) -> dict[str, str]:
    artifact = _strict_object(value, field="artifact", keys=_ARTIFACT_KEYS)
    artifact_class = _text(artifact["class"], field="artifact.class")
    build_mode = _text(artifact["buildMode"], field="artifact.buildMode")
    build_profile = _text(artifact["buildProfile"], field="artifact.buildProfile")
    if artifact_class not in _ARTIFACT_CLASSES:
        raise _error("artifact.class must be production_behavior or production")
    if build_mode not in _BUILD_MODES:
        raise _error("artifact.buildMode must be debug, profile, or release")
    if build_profile not in _BUILD_PROFILES:
        raise _error("artifact.buildProfile must be nonprod or prod")
    return {
        "class": artifact_class,
        "digest": _digest(artifact["digest"], field="artifact.digest"),
        "applicationId": _identity(
            artifact["applicationId"], field="artifact.applicationId"
        ),
        "buildMode": build_mode,
        "buildProfile": build_profile,
    }


def _validate_provider(value: object) -> dict[str, Any]:
    provider = _strict_object(value, field="provider", keys=_PROVIDER_KEYS)
    provider_class = _text(provider["class"], field="provider.class")
    if provider_class not in _PROVIDER_CLASSES:
        raise _error("provider.class must be first_party, external, or test_fixture")
    return {
        "identity": _identity(provider["identity"], field="provider.identity"),
        "class": provider_class,
        "type": _identity(provider["type"], field="provider.type"),
        "registered": _boolean(
            provider["registered"], field="provider.registered"
        ),
        "conformanceEvidence": _validate_source(
            provider["conformanceEvidence"], field="provider.conformanceEvidence"
        ),
    }


def _validate_device(value: object) -> dict[str, Any]:
    device = _strict_object(value, field="device", keys=_DEVICE_KEYS)
    device_class = _text(device["class"], field="device.class")
    if device_class not in _DEVICE_CLASSES:
        raise _error("device.class must be physical, emulator, or simulator")
    return {
        "identity": _identity(device["identity"], field="device.identity"),
        "class": device_class,
        "registered": _boolean(device["registered"], field="device.registered"),
    }


def _validate_runner(value: object) -> dict[str, str]:
    runner = _strict_object(value, field="runner", keys=_RUNNER_KEYS)
    return {
        "identity": _identity(runner["identity"], field="runner.identity"),
        "sourcePath": _relative_ref(runner["sourcePath"], field="runner.sourcePath"),
        "digest": _digest(runner["digest"], field="runner.digest"),
        "registered": _boolean(runner["registered"], field="runner.registered"),
    }


def _validate_profile_constraints(value: Mapping[str, Any]) -> None:
    profile = value["profile"]
    environment = value["environment"]
    provider = value["provider"]
    device = value["device"]
    runner = value["runner"]
    artifact = value["artifact"]
    non_promotable = value["nonPromotable"]

    if environment == "prod" and profile != "production":
        raise _error("prod target only accepts the production profile")
    if profile == "rehearsal":
        if (
            device["class"] not in {"emulator", "simulator"}
            or non_promotable is not True
            or artifact["class"] != "production_behavior"
        ):
            raise _error(
                "rehearsal requires emulator/simulator, production_behavior, "
                "and nonPromotable=true"
            )
        return
    if (
        provider["registered"] is not True
        or device["class"] != "physical"
        or device["registered"] is not True
        or runner["registered"] is not True
        or non_promotable is not False
    ):
        raise _error(
            f"{profile} requires registered provider/device/runner ownership, "
            "a physical device, and nonPromotable=false"
        )
    if profile == "promotable":
        if artifact["class"] != "production_behavior":
            raise _error("promotable requires artifact.class=production_behavior")
        return
    if (
        environment != "prod"
        or artifact["class"] != "production"
        or artifact["buildMode"] != "release"
        or artifact["buildProfile"] != "prod"
    ):
        raise _error(
            "production requires prod, artifact.class=production, buildMode=release, "
            "and buildProfile=prod"
        )


def _assert_expected(
    actual: Mapping[str, Any], expected: Mapping[str, object], *, field: str = "binding"
) -> None:
    if not all(isinstance(key, str) for key in expected):
        raise _error("expected_bindings must use string keys")
    for key, expected_value in expected.items():
        if key not in actual:
            raise _error(f"expected_bindings contains unknown field {field}.{key}")
        actual_value = actual[key]
        if isinstance(expected_value, Mapping):
            if not isinstance(actual_value, Mapping):
                raise _error(f"expected binding shape drifted at {field}.{key}")
            _assert_expected(actual_value, expected_value, field=f"{field}.{key}")
        elif actual_value != expected_value:
            raise _error(
                f"{field}.{key} is stale: {actual_value!r} != {expected_value!r}",
                code=_STALE,
            )


def validate_target_uat_binding(
    binding: Mapping[str, Any],
    *,
    expected_bindings: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Validate closed shape, digests, slot identity, profile and stale inputs."""

    value = _strict_object(binding, field="binding", keys=TARGET_UAT_BINDING_KEYS)
    if value["schema"] != TARGET_UAT_BINDING_SCHEMA:
        raise _error("schema is not quwoquan_ops.target_uat_binding.v1")

    environment = _text(value["environment"], field="environment")
    if environment not in _ENVIRONMENTS:
        raise _error("environment must be alpha, beta, gamma, or prod")
    platform = _text(value["platform"], field="platform")
    if platform not in _PLATFORMS:
        raise _error("platform must be android or ios")
    profile = _text(value["profile"], field="profile")
    if profile not in _PROFILES:
        raise _error("profile must be rehearsal, promotable, or production")

    normalized: dict[str, Any] = {
        "schema": TARGET_UAT_BINDING_SCHEMA,
        "bindingId": _digest(value["bindingId"], field="bindingId"),
        "releaseId": _identity(value["releaseId"], field="releaseId"),
        "releaseDigest": _digest(value["releaseDigest"], field="releaseDigest"),
        "releaseUatSamplePlanRef": _relative_ref(
            value["releaseUatSamplePlanRef"], field="releaseUatSamplePlanRef"
        ),
        "releaseUatSamplePlanDigest": _digest(
            value["releaseUatSamplePlanDigest"],
            field="releaseUatSamplePlanDigest",
        ),
        "environment": environment,
        "target": _identity(value["target"], field="target"),
        "candidateDigest": _digest(value["candidateDigest"], field="candidateDigest"),
        "packageDigest": _digest(value["packageDigest"], field="packageDigest"),
        "configurationDigest": _digest(
            value["configurationDigest"], field="configurationDigest"
        ),
        "runtimeConfigDigest": _digest(
            value["runtimeConfigDigest"], field="runtimeConfigDigest"
        ),
        "environmentRuntimeDigest": _digest(
            value["environmentRuntimeDigest"], field="environmentRuntimeDigest"
        ),
        "activeCas": _validate_source(value["activeCas"], field="activeCas"),
        "readback": _validate_source(value["readback"], field="readback"),
        "artifact": _validate_artifact(value["artifact"]),
        "platform": platform,
        "provider": _validate_provider(value["provider"]),
        "device": _validate_device(value["device"]),
        "runner": _validate_runner(value["runner"]),
        "profile": profile,
        "nonPromotable": _boolean(value["nonPromotable"], field="nonPromotable"),
        "createdAt": _created_at(value["createdAt"]),
    }
    expected_binding_id = target_uat_binding_id(
        target=normalized["target"],
        release_id=normalized["releaseId"],
        release_digest=normalized["releaseDigest"],
        platform=normalized["platform"],
        provider=normalized["provider"],
        device_identity=normalized["device"]["identity"],
        profile=normalized["profile"],
        runner=normalized["runner"],
    )
    if normalized["bindingId"] != expected_binding_id:
        raise _error("bindingId does not match the exact slot identity")
    _validate_profile_constraints(normalized)
    if expected_bindings is not None:
        if not isinstance(expected_bindings, Mapping):
            raise _error("expected_bindings must be an object")
        _assert_expected(normalized, expected_bindings)
    return normalized


def canonical_target_uat_binding_bytes(binding: Mapping[str, Any]) -> bytes:
    """Return sorted compact canonical JSON bytes with one trailing newline."""

    return _canonical_json_bytes(validate_target_uat_binding(binding), newline=True)


def target_uat_binding_digest(binding: Mapping[str, Any] | bytes) -> str:
    """Return the SHA-256 digest of the exact canonical bytes."""

    if isinstance(binding, bytes):
        value = _decode_binding_bytes(binding)
        if binding != _canonical_json_bytes(value, newline=True):
            raise _error("binding bytes are not canonical exact bytes")
        encoded = binding
    else:
        encoded = canonical_target_uat_binding_bytes(binding)
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _source_mapping(
    value: Mapping[str, Any], key: str, *, label: str
) -> Mapping[str, Any]:
    observed = value.get(key)
    if not isinstance(observed, Mapping):
        raise _error(f"{label} is missing")
    return observed


def build_target_uat_binding(
    runtime_binding: Mapping[str, Any],
    launch_binding: Mapping[str, Any],
    sample_plan_binding: Mapping[str, Any],
    *,
    active_cas: Mapping[str, Any],
    readback: Mapping[str, Any],
    artifact_class: str,
    build_mode: str,
    build_profile: str,
    provider: Mapping[str, Any],
    device: Mapping[str, Any],
    runner: Mapping[str, Any],
    profile: str,
    non_promotable: bool,
    created_at: str,
) -> dict[str, Any]:
    """Purely adapt verified current runtime/launch facts into one binding.

    Device class/registration, profile, timestamps and artifact release semantics
    stay explicit.  In particular this adapter never infers a physical device.
    """

    if not all(
        isinstance(value, Mapping)
        for value in (runtime_binding, launch_binding, sample_plan_binding)
    ):
        raise _error("runtime, launch, and sample-plan bindings must be objects")
    startup_identity = _source_mapping(
        runtime_binding, "startupIdentity", label="runtime_binding.startupIdentity"
    )
    normalized_provider = _validate_provider(provider)
    normalized_device = _validate_device(device)
    normalized_runner = _validate_runner(runner)
    document: dict[str, Any] = {
        "schema": TARGET_UAT_BINDING_SCHEMA,
        "bindingId": target_uat_binding_id(
            target=_identity(runtime_binding.get("target"), field="target"),
            release_id=_identity(runtime_binding.get("releaseId"), field="releaseId"),
            release_digest=_digest(
                runtime_binding.get("manifestDigest"), field="releaseDigest"
            ),
            platform=_text(launch_binding.get("platform"), field="platform"),
            provider=normalized_provider,
            device_identity=normalized_device["identity"],
            profile=profile,
            runner=normalized_runner,
        ),
        "releaseId": runtime_binding.get("releaseId"),
        "releaseDigest": runtime_binding.get("manifestDigest"),
        "releaseUatSamplePlanRef": sample_plan_binding.get("releaseUatSamplePlanRef"),
        "releaseUatSamplePlanDigest": sample_plan_binding.get(
            "releaseUatSamplePlanDigest"
        ),
        "environment": runtime_binding.get("environment"),
        "target": runtime_binding.get("target"),
        "candidateDigest": runtime_binding.get("candidateDigest"),
        "packageDigest": runtime_binding.get("packageDigest"),
        "configurationDigest": startup_identity.get("configurationDigest"),
        "runtimeConfigDigest": runtime_binding.get("runtimeConfigDigest"),
        "environmentRuntimeDigest": runtime_binding.get("environmentRuntimeDigest"),
        "activeCas": dict(active_cas),
        "readback": dict(readback),
        "artifact": {
            "class": artifact_class,
            "digest": launch_binding.get("artifactDigest"),
            "applicationId": launch_binding.get("applicationId"),
            "buildMode": build_mode,
            "buildProfile": build_profile,
        },
        "platform": launch_binding.get("platform"),
        "provider": normalized_provider,
        "device": normalized_device,
        "runner": normalized_runner,
        "profile": profile,
        "nonPromotable": non_promotable,
        "createdAt": created_at,
    }
    if launch_binding.get("deviceId") != normalized_device["identity"]:
        raise _error("launch_binding.deviceId drifted from explicit device.identity")
    if launch_binding.get("target") != runtime_binding.get("target"):
        raise _error("launch_binding.target drifted from runtime_binding.target")
    if launch_binding.get("environment") != runtime_binding.get("environment"):
        raise _error(
            "launch_binding.environment drifted from runtime_binding.environment"
        )
    if sample_plan_binding.get("releaseId") not in {
        None,
        runtime_binding.get("releaseId"),
    }:
        raise _error("sample-plan releaseId drifted from runtime binding")
    return validate_target_uat_binding(document)


def _decode_binding_bytes(encoded: bytes) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _error(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        text = encoded.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                _error(f"invalid JSON constant: {value}")
            ),
        )
        document, end = decoder.raw_decode(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("binding bytes are not valid UTF-8 JSON") from exc
    if text[end:] != "\n":
        raise _error("binding bytes must end with exactly one canonical newline")
    if not isinstance(document, dict):
        raise _error("binding bytes must contain one object")
    return validate_target_uat_binding(document)


def _real_directory(path: Path, *, label: str) -> Path:
    candidate = Path(path).expanduser().absolute()
    try:
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise _error(
            f"{label} must be an existing real directory", code=_PATH_INVALID
        ) from exc
    if (
        candidate.is_symlink()
        or resolved != candidate
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise _error(f"{label} must be an existing real directory", code=_PATH_INVALID)
    return candidate


def _read_regular_nofollow(path: Path) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise _error("binding file is unavailable", code=_CONFLICT) from exc
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise _error("binding file must be a regular non-symlink file", code=_CONFLICT)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise _error("binding file cannot be opened safely", code=_CONFLICT) from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise _error("binding file changed while opening", code=_CONFLICT)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    encoded = b"".join(chunks)
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    ) or len(encoded) != opened.st_size:
        raise _error("binding file changed during read", code=_CONFLICT)
    return encoded


def read_target_uat_binding(path: Path) -> dict[str, Any]:
    """Read exact canonical bytes while rejecting symlinks and duplicate keys."""

    candidate = Path(path).expanduser().absolute()
    _real_directory(candidate.parent, label="binding parent")
    encoded = _read_regular_nofollow(candidate)
    value = _decode_binding_bytes(encoded)
    if encoded != _canonical_json_bytes(value, newline=True):
        raise _error("binding file bytes are not canonical", code=_CONFLICT)
    return value


def target_uat_binding_ref(binding: Mapping[str, Any]) -> str:
    """Return the only permitted output-root-relative binding path."""

    value = validate_target_uat_binding(binding)
    return f"{TARGET_UAT_BINDING_DIRECTORY}/{value['bindingId']}.json"


def _prepare_store(output_root: Path) -> Path:
    root = _real_directory(output_root, label="output root")
    store = root / TARGET_UAT_BINDING_DIRECTORY
    try:
        store.mkdir(mode=0o755)
    except FileExistsError:
        pass
    except OSError as exc:
        raise _error(
            "target UAT binding directory cannot be created", code=_PATH_INVALID
        ) from exc
    return _real_directory(store, label="target UAT binding directory")


def _reject_slot_aliases(
    store: Path, binding: Mapping[str, Any], destination: Path
) -> None:
    slot = target_uat_binding_slot_identity(
        target=binding["target"],
        release_id=binding["releaseId"],
        release_digest=binding["releaseDigest"],
        platform=binding["platform"],
        provider=binding["provider"],
        device_identity=binding["device"]["identity"],
        profile=binding["profile"],
        runner=binding["runner"],
    )
    try:
        entries = list(os.scandir(store))
    except OSError as exc:
        raise _error(
            "target UAT binding directory cannot be scanned", code=_CONFLICT
        ) from exc
    for entry in entries:
        if entry.name == destination.name or not entry.name.endswith(".json"):
            continue
        candidate = store / entry.name
        try:
            existing_raw = _read_regular_nofollow(candidate)
            existing = _decode_binding_bytes(existing_raw)
        except TargetUatBindingError as exc:
            raise _error(
                f"existing target UAT binding store entry is unsafe: {entry.name}",
                code=_CONFLICT,
            ) from exc
        if entry.name != f"{existing['bindingId']}.json":
            raise _error(
                f"existing target UAT binding has a noncanonical path: {entry.name}",
                code=_CONFLICT,
            )
        existing_slot = target_uat_binding_slot_identity(
            target=existing["target"],
            release_id=existing["releaseId"],
            release_digest=existing["releaseDigest"],
            platform=existing["platform"],
            provider=existing["provider"],
            device_identity=existing["device"]["identity"],
            profile=existing["profile"],
            runner=existing["runner"],
        )
        if existing_slot == slot:
            raise _error(
                "the same slot already exists under a different binding path",
                code=_CONFLICT,
            )


def write_create_once_target_uat_binding(
    *, output_root: Path, binding: Mapping[str, Any]
) -> TargetUatBindingWriteResult:
    """Create the canonical slot path with O_EXCL; exact bytes replay idempotently."""

    value = validate_target_uat_binding(binding)
    encoded = _canonical_json_bytes(value, newline=True)
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    reference = target_uat_binding_ref(value)
    store = _prepare_store(output_root)
    destination = store / Path(reference).name
    _reject_slot_aliases(store, value, destination)

    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(destination, flags, 0o644)
    except FileExistsError:
        existing = _read_regular_nofollow(destination)
        if existing != encoded:
            raise _error(
                "canonical binding path already contains different bytes",
                code=_CONFLICT,
            )
        _decode_binding_bytes(existing)
        return TargetUatBindingWriteResult(
            path=destination,
            ref=reference,
            digest=digest,
            binding=value,
            created=False,
        )
    except OSError as exc:
        raise _error("canonical binding cannot be created", code=_CONFLICT) from exc

    try:
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_fd = os.open(store, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return TargetUatBindingWriteResult(
        path=destination,
        ref=reference,
        digest=digest,
        binding=value,
        created=True,
    )


__all__ = [
    "SCHEMA_PATH",
    "TARGET_UAT_BINDING_DIRECTORY",
    "TARGET_UAT_BINDING_KEYS",
    "TARGET_UAT_BINDING_SCHEMA",
    "TargetUatBindingError",
    "TargetUatBindingWriteResult",
    "build_target_uat_binding",
    "canonical_target_uat_binding_bytes",
    "read_target_uat_binding",
    "target_uat_binding_digest",
    "target_uat_binding_id",
    "target_uat_binding_ref",
    "target_uat_binding_slot_identity",
    "validate_target_uat_binding",
    "write_create_once_target_uat_binding",
]
