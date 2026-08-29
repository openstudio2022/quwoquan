"""Bind and launch the native test driver without relabelling the Patrol host."""

from __future__ import annotations

import copy
import hashlib
import os
import plistlib
import re
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .artifact_binding import (
    TESTED_APP_ARTIFACT_BINDING_SCHEMA,
    TestedAppArtifactBindingError,
    collect_tested_app_artifact_binding,
    host_source_identity,
    validate_tested_app_artifact_binding,
)
from .external_aut_driver_contract import (
    _ANDROID_DRIVER_APK_RELATIVE,
    _DRIVER_ARTIFACT_FIELDS,
    _PLATFORM_CONTRACT,
    EXTERNAL_AUT_DRIVER_ARTIFACT_SCHEMA,
    IOS_EXTERNAL_AUT_ONLY_TESTING,
    PATROL_ANDROID_DRIVER_APPLICATION_ID,
    PATROL_ANDROID_HOST_APPLICATION_ID,
    PATROL_IOS_HOST_APPLICATION_ID,
    PATROL_IOS_XCTEST_BUNDLE_ID,
    PATROL_IOS_XCTRUNNER_BUNDLE_ID,
    ExternalAutDriverEvidenceError,
    _application_id,
    _canonical_document_digest,
    _digest,
)


def _sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ExternalAutDriverEvidenceError(f"artifact file is missing or unsafe: {path}")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ExternalAutDriverEvidenceError(
            f"artifact file changed during digest readback: {path}"
        )
    return "sha256:" + digest.hexdigest()


def _stable_tree_digest(root: Path, *, suffix: str) -> str:
    canonical = root.resolve()
    if root.is_symlink() or root.suffix != suffix or not canonical.is_dir():
        raise ExternalAutDriverEvidenceError(
            f"artifact tree is missing or unsafe: {root}"
        )

    def inventory() -> tuple[tuple[Path, tuple[int, int, int, int]], ...]:
        values: list[tuple[Path, tuple[int, int, int, int]]] = []
        for path in sorted(canonical.rglob("*")):
            if path.is_symlink():
                raise ExternalAutDriverEvidenceError(
                    f"artifact tree contains a symlink: {path}"
                )
            if not path.is_file():
                continue
            stat = path.stat()
            values.append(
                (
                    path.relative_to(canonical),
                    (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns),
                )
            )
        return tuple(values)

    before = inventory()
    if not before:
        raise ExternalAutDriverEvidenceError(f"artifact tree is empty: {root}")
    digest = hashlib.sha256(b"external-aut-driver-tree-v1\0")
    for relative, identity in before:
        encoded = relative.as_posix().encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(identity[2].to_bytes(8, "big"))
        with (canonical / relative).open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    if before != inventory():
        raise ExternalAutDriverEvidenceError(
            f"artifact tree changed during digest readback: {root}"
        )
    return "sha256:" + digest.hexdigest()


def _ios_runner_configuration(payload: object) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        direct = payload.get("RunnerUITests")
        if isinstance(direct, dict):
            candidates.append(direct)
        configurations = payload.get("TestConfigurations")
        if isinstance(configurations, list):
            for configuration in configurations:
                targets = (
                    configuration.get("TestTargets")
                    if isinstance(configuration, dict)
                    else None
                )
                if not isinstance(targets, list):
                    continue
                for target in targets:
                    if not isinstance(target, dict):
                        continue
                    test_bundle = str(target.get("TestBundlePath") or "")
                    if (
                        target.get("BlueprintName") == "RunnerUITests"
                        or target.get("TargetName") == "RunnerUITests"
                        or "RunnerUITests.xctest" in test_bundle
                    ):
                        candidates.append(target)
    unique = list({id(candidate): candidate for candidate in candidates}.values())
    if len(unique) != 1:
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun must contain exactly one RunnerUITests target"
        )
    return unique[0]


def _ios_driver_artifact_paths(
    *, source: Path, runner: Mapping[str, Any]
) -> tuple[Path, Path]:
    test_root = source.parent.resolve()
    raw_host = str(runner.get("TestHostPath") or "").strip()
    raw_bundle = str(runner.get("TestBundlePath") or "").strip()
    if not raw_bundle:
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun TestBundlePath is missing"
        )

    def expand(raw: str, *, test_host: Path | None = None) -> Path:
        value = raw.replace("__TESTROOT__", str(test_root))
        if "__TESTHOST__" in value:
            if test_host is None:
                raise ExternalAutDriverEvidenceError(
                    "iOS Patrol xctestrun uses TestHost before it is resolved"
                )
            value = value.replace("__TESTHOST__", str(test_host))
        if "__" in value:
            raise ExternalAutDriverEvidenceError(
                "iOS Patrol xctestrun contains an unsupported path placeholder"
            )
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = test_root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(test_root)
        except ValueError as exc:
            raise ExternalAutDriverEvidenceError(
                "iOS Patrol driver artifact escapes build products"
            ) from exc
        return resolved

    host_path = expand(raw_host) if raw_host else None
    bundle_path = expand(raw_bundle, test_host=host_path)
    if host_path is None:
        host_path = next(
            (parent for parent in bundle_path.parents if parent.suffix == ".app"),
            None,
        )
    if host_path is None or host_path.suffix != ".app":
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun xctrunner TestHostPath is missing"
        )
    if bundle_path.suffix != ".xctest":
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun TestBundlePath is not an xctest bundle"
        )
    try:
        bundle_path.relative_to(host_path)
    except ValueError as exc:
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol TestBundlePath is not inside the xctrunner"
        ) from exc
    return host_path, bundle_path


def _driver_artifact_envelope(
    *,
    platform: str,
    device_id: str,
    driver_application_id: str,
    test_host_application_id: str,
    artifact_kind: str,
    artifact_digest: str,
    evidence: Mapping[str, Any],
) -> dict[str, object]:
    payload = copy.deepcopy(dict(evidence))
    return {
        "schema": EXTERNAL_AUT_DRIVER_ARTIFACT_SCHEMA,
        "status": "passed",
        "provenance": "external_aut_native_driver_artifact_readback",
        "platform": platform,
        "deviceId": device_id,
        "driverApplicationId": driver_application_id,
        "testHostApplicationId": test_host_application_id,
        "artifactKind": artifact_kind,
        "artifactDigest": artifact_digest,
        "evidenceDigest": _canonical_document_digest(payload),
        "evidence": payload,
    }


def collect_android_external_aut_driver_artifact_binding(
    *,
    patrol_host_dir: Path,
    device: dict[str, Any],
    command_env: dict[str, str],
    adb: str,
    collector: Callable[..., dict[str, object]] = collect_tested_app_artifact_binding,
) -> dict[str, object]:
    """Bind the final androidTest APK and its exact installed driver bytes."""

    artifact_path = (patrol_host_dir / _ANDROID_DRIVER_APK_RELATIVE).resolve()
    try:
        raw = collector(
            device=device,
            patrol_command=[
                "external-aut-native-driver",
                "--package-name",
                PATROL_ANDROID_DRIVER_APPLICATION_ID,
            ],
            command_env=command_env,
            artifact_path=artifact_path,
            host_source=host_source_identity(host_root=patrol_host_dir),
            android_adb=adb,
        )
        comparison = validate_tested_app_artifact_binding(raw)
    except TestedAppArtifactBindingError as exc:
        raise ExternalAutDriverEvidenceError(
            f"Android native driver artifact readback failed: {exc.detail}"
        ) from exc
    if (
        raw.get("platform") != "android"
        or raw.get("deviceId") != str(device.get("id") or "").strip()
        or comparison.get("applicationId")
        != PATROL_ANDROID_DRIVER_APPLICATION_ID
        or Path(str((raw.get("buildArtifact") or {}).get("path") or "")).resolve()
        != artifact_path
    ):
        raise ExternalAutDriverEvidenceError(
            "Android native driver artifact identity drifted"
        )
    binding = _driver_artifact_envelope(
        platform="android",
        device_id=str(device.get("id") or "").strip(),
        driver_application_id=PATROL_ANDROID_DRIVER_APPLICATION_ID,
        test_host_application_id=PATROL_ANDROID_HOST_APPLICATION_ID,
        artifact_kind="android_test_apk_installed_readback",
        artifact_digest=comparison["artifactDigest"],
        evidence={"testedDriverArtifactBinding": raw},
    )
    validate_external_aut_driver_artifact_binding(
        binding,
        expected_platform="android",
        expected_device_id=str(device.get("id") or "").strip(),
        patrol_host_dir=patrol_host_dir,
    )
    return binding


def build_ios_external_aut_driver_artifact_binding(
    *, source: Path, patrol_host_dir: Path, device_id: str
) -> dict[str, object]:
    """Bind the exact xctestrun TestBundlePath and xctrunner tree bytes."""

    try:
        payload = plistlib.loads(source.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun is unreadable"
        ) from exc
    runner = _ios_runner_configuration(payload)
    if runner.get("TestHostBundleIdentifier") != PATROL_IOS_XCTRUNNER_BUNDLE_ID:
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun driver identity mismatch"
        )
    host_path, bundle_path = _ios_driver_artifact_paths(
        source=source, runner=runner
    )
    info_path = host_path / "Info.plist"
    try:
        host_info = plistlib.loads(info_path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        raise ExternalAutDriverEvidenceError(
            "iOS xctrunner Info.plist is unreadable"
        ) from exc
    if host_info.get("CFBundleIdentifier") != PATROL_IOS_XCTRUNNER_BUNDLE_ID:
        raise ExternalAutDriverEvidenceError(
            "iOS xctrunner bundle identity drifted"
        )
    test_bundle_info_path = bundle_path / "Info.plist"
    try:
        test_bundle_info = plistlib.loads(test_bundle_info_path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        raise ExternalAutDriverEvidenceError(
            "iOS XCTest bundle Info.plist is unreadable"
        ) from exc
    if test_bundle_info.get("CFBundleIdentifier") != PATROL_IOS_XCTEST_BUNDLE_ID:
        raise ExternalAutDriverEvidenceError(
            "iOS XCTest bundle identity drifted"
        )
    host_digest = _stable_tree_digest(host_path, suffix=".app")
    bundle_digest = _stable_tree_digest(bundle_path, suffix=".xctest")
    evidence = {
        "xctestrunPath": str(source.resolve()),
        "xctestrunDigest": _sha256_file(source),
        "testBundlePath": str(bundle_path),
        "testBundleDigest": bundle_digest,
        "testHostPath": str(host_path),
        "testHostDigest": host_digest,
        "testHostBundleIdentifier": PATROL_IOS_XCTRUNNER_BUNDLE_ID,
        "testBundleIdentifier": PATROL_IOS_XCTEST_BUNDLE_ID,
    }
    binding = _driver_artifact_envelope(
        platform="ios",
        device_id=str(device_id or "").strip(),
        driver_application_id=PATROL_IOS_XCTRUNNER_BUNDLE_ID,
        test_host_application_id=PATROL_IOS_HOST_APPLICATION_ID,
        artifact_kind="ios_xctrunner_test_bundle_tree",
        artifact_digest=host_digest,
        evidence=evidence,
    )
    validate_external_aut_driver_artifact_binding(
        binding,
        expected_platform="ios",
        expected_device_id=device_id,
        patrol_host_dir=patrol_host_dir,
    )
    return binding


def validate_external_aut_driver_artifact_binding(
    binding: Mapping[str, Any],
    *,
    expected_platform: str,
    expected_device_id: str,
    patrol_host_dir: Path | None = None,
) -> dict[str, object]:
    if set(binding) != _DRIVER_ARTIFACT_FIELDS:
        raise ExternalAutDriverEvidenceError(
            "external AUT native driver artifact fields differ"
        )
    platform = str(expected_platform or "").strip().lower()
    contract = _PLATFORM_CONTRACT.get(platform)
    evidence = binding.get("evidence")
    if (
        contract is None
        or binding.get("schema") != EXTERNAL_AUT_DRIVER_ARTIFACT_SCHEMA
        or binding.get("status") != "passed"
        or binding.get("provenance")
        != "external_aut_native_driver_artifact_readback"
        or binding.get("platform") != platform
        or binding.get("deviceId") != str(expected_device_id or "").strip()
        or binding.get("driverApplicationId")
        != contract["driverApplicationId"]
        or binding.get("testHostApplicationId")
        != contract["testHostApplicationId"]
        or not isinstance(evidence, Mapping)
        or binding.get("evidenceDigest") != _canonical_document_digest(evidence)
    ):
        raise ExternalAutDriverEvidenceError(
            "external AUT native driver artifact identity or digest drifted"
        )
    artifact_digest = _digest(
        binding.get("artifactDigest"), "native driver artifactDigest"
    )
    if platform == "android":
        if binding.get("artifactKind") != "android_test_apk_installed_readback":
            raise ExternalAutDriverEvidenceError(
                "Android native driver artifact kind drifted"
            )
        raw = evidence.get("testedDriverArtifactBinding")
        if not isinstance(raw, dict) or raw.get("schema") != (
            TESTED_APP_ARTIFACT_BINDING_SCHEMA
        ):
            raise ExternalAutDriverEvidenceError(
                "Android native driver artifact readback is missing"
            )
        try:
            comparison = validate_tested_app_artifact_binding(raw)
        except TestedAppArtifactBindingError as exc:
            raise ExternalAutDriverEvidenceError(exc.detail) from exc
        expected_path = (
            (patrol_host_dir / _ANDROID_DRIVER_APK_RELATIVE).resolve()
            if patrol_host_dir is not None
            else None
        )
        raw_path = Path(str((raw.get("buildArtifact") or {}).get("path") or ""))
        if (
            comparison.get("applicationId")
            != PATROL_ANDROID_DRIVER_APPLICATION_ID
            or comparison.get("artifactDigest") != artifact_digest
            or raw.get("platform") != "android"
            or raw.get("deviceId") != expected_device_id
            or (expected_path is not None and raw_path.resolve() != expected_path)
        ):
            raise ExternalAutDriverEvidenceError(
                "Android native driver build/install readback drifted"
            )
    else:
        if binding.get("artifactKind") != "ios_xctrunner_test_bundle_tree" or set(
            evidence
        ) != {
            "xctestrunPath",
            "xctestrunDigest",
            "testBundlePath",
            "testBundleDigest",
            "testHostPath",
            "testHostDigest",
            "testHostBundleIdentifier",
            "testBundleIdentifier",
        }:
            raise ExternalAutDriverEvidenceError(
                "iOS native driver xctestrun binding is malformed"
            )
        if (
            evidence.get("testHostBundleIdentifier")
            != PATROL_IOS_XCTRUNNER_BUNDLE_ID
            or evidence.get("testBundleIdentifier")
            != PATROL_IOS_XCTEST_BUNDLE_ID
            or evidence.get("testHostDigest") != artifact_digest
        ):
            raise ExternalAutDriverEvidenceError(
                "iOS native driver xctrunner identity drifted"
            )
        for field in ("xctestrunDigest", "testBundleDigest", "testHostDigest"):
            _digest(evidence.get(field), f"iOS native driver {field}")
        if patrol_host_dir is not None:
            root = (
                patrol_host_dir / "build" / "ios_integ" / "Build" / "Products"
            ).resolve()
            xctestrun = Path(str(evidence["xctestrunPath"])).resolve()
            bundle = Path(str(evidence["testBundlePath"])).resolve()
            host = Path(str(evidence["testHostPath"])).resolve()
            try:
                for path in (xctestrun, bundle, host):
                    path.relative_to(root)
            except ValueError as exc:
                raise ExternalAutDriverEvidenceError(
                    "iOS native driver artifact escaped build products"
                ) from exc
            if (
                _sha256_file(xctestrun) != evidence["xctestrunDigest"]
                or _stable_tree_digest(bundle, suffix=".xctest")
                != evidence["testBundleDigest"]
                or _stable_tree_digest(host, suffix=".app")
                != evidence["testHostDigest"]
            ):
                raise ExternalAutDriverEvidenceError(
                    "iOS native driver artifact bytes changed after binding"
                )
    return copy.deepcopy(dict(binding))


def resolve_ios_external_aut_xctestrun(
    *,
    patrol_host_dir: Path,
    patrol_output: str,
) -> Path:
    """Resolve the exact current Patrol xctestrun and reject stale ambiguity."""

    products_root = (
        patrol_host_dir / "build" / "ios_integ" / "Build" / "Products"
    ).resolve()
    marker_candidates: list[Path] = []
    marker_pattern = re.compile(r"(?P<path>\S+\.xctestrun) \(xctestrun file\)")
    for match in marker_pattern.finditer(patrol_output):
        candidate = Path(match.group("path"))
        if not candidate.is_absolute():
            candidate = patrol_host_dir / candidate
        marker_candidates.append(candidate.resolve())
    candidates = tuple(dict.fromkeys(marker_candidates))
    if not candidates:
        candidates = tuple(
            sorted(products_root.glob("Runner_*iphonesimulator*.xctestrun"))
        )
    if len(candidates) != 1:
        raise ExternalAutDriverEvidenceError(
            "expected exactly one current iOS Patrol xctestrun, observed "
            + str(len(candidates))
        )
    source = candidates[0]
    try:
        source.relative_to(products_root)
    except ValueError as exc:
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun escapes its build products root"
        ) from exc
    if source.is_symlink() or not source.is_file():
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun is missing or unsafe"
        )
    return source


def materialize_ios_external_aut_xctestrun(
    *,
    source: Path,
    production_application_id: str,
    expected_source_digest: str | None = None,
) -> tuple[Path, str]:
    """Create a sibling xctestrun that injects env only into the driver."""

    production_id = _application_id(
        production_application_id, "production_application_id"
    )
    if source.is_symlink() or not source.is_file():
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun is missing or unsafe"
        )
    try:
        source_bytes = source.read_bytes()
        payload = plistlib.loads(source_bytes)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun is unreadable"
        ) from exc
    source_digest = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    if expected_source_digest is not None and source_digest != expected_source_digest:
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun changed after native driver artifact binding"
        )
    runner = _ios_runner_configuration(payload)
    if runner.get("TestHostBundleIdentifier") != PATROL_IOS_XCTRUNNER_BUNDLE_ID:
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun driver identity mismatch"
        )
    environment = runner.get("EnvironmentVariables")
    if not isinstance(environment, dict):
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun driver environment is malformed"
        )
    if any(
        key in environment
        for key in ("QWQ_IOS_TARGET_BUNDLE_ID", "QWQ_IOS_EXPECTED_BUNDLE_ID")
    ):
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun contains stale external AUT identity"
        )
    runner["EnvironmentVariables"] = {
        **environment,
        "QWQ_IOS_TARGET_BUNDLE_ID": production_id,
        "QWQ_IOS_EXPECTED_BUNDLE_ID": production_id,
    }
    if _sha256_file(source) != source_digest:
        raise ExternalAutDriverEvidenceError(
            "iOS Patrol xctestrun changed during identity injection"
        )
    handle, temporary = tempfile.mkstemp(
        prefix=source.stem + ".external-aut.",
        suffix=".xctestrun",
        dir=source.parent,
    )
    destination = Path(temporary)
    try:
        os.close(handle)
        serialized = plistlib.dumps(payload, fmt=plistlib.FMT_BINARY, sort_keys=True)
        destination.write_bytes(serialized)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination, "sha256:" + hashlib.sha256(serialized).hexdigest()


def ios_external_aut_xcodebuild_command(
    *,
    xctestrun: Path,
    device_id: str,
) -> list[str]:
    normalized_device_id = str(device_id or "").strip()
    if xctestrun.is_symlink() or not xctestrun.is_file() or not normalized_device_id:
        raise ExternalAutDriverEvidenceError(
            "iOS external AUT driver requires xctestrun and an exact deviceId"
        )
    return [
        "xcodebuild",
        "test-without-building",
        "-xctestrun",
        str(xctestrun),
        "-only-testing",
        IOS_EXTERNAL_AUT_ONLY_TESTING,
        "-destination",
        "platform=iOS Simulator,id=" + normalized_device_id,
        "-destination-timeout",
        "30",
    ]
