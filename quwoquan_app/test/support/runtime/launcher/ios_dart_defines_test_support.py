# iOS runtime trust/package build 契约套件的共享常量与构造 helper。

import base64
import json
import shlex
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[4]
for _support_path in (
    str(APP_DIR / "scripts/runtime/platform"),
    str(APP_DIR / "scripts/device"),
    str(APP_DIR / "test/support/runtime/launcher"),
):
    if _support_path not in sys.path:
        sys.path.insert(0, _support_path)

import build_launcher_handoff as launcher
from launcher_package_fixture import build_test_handoff_fixture


SCRIPT = APP_DIR / "scripts/ios/build_prepare_dart_defines.sh"
BUILD_WRAPPER = APP_DIR / "scripts/ios/build_xcode_backend.sh"
CANONICAL_LAUNCHER = APP_DIR / "run.sh"
STACKCTL_PYTHON_RESOLVER = APP_DIR / "scripts/ios/build_resolve_stackctl_python.sh"
RUNTIME_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}


def _build_handoff(
    environment: str,
    *,
    launch_provenance: str = "canonical_launcher",
) -> tuple[dict[str, object], dict[str, object]]:
    return build_test_handoff_fixture(
        launcher,
        environment,
        RUNTIME_TARGETS[environment],
        launch_provenance=launch_provenance,
    )


def _write_trust_envelope(
    root: Path,
    trust_envelope: dict[str, object],
) -> Path:
    path = root / "runtime-config-trust.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            trust_envelope,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _apply_handoff_identity(
    env: dict[str, str],
    environment: str,
    *,
    artifact_root: Path,
    launch_provenance: str = "canonical_launcher",
    runtime_python: Path,
) -> dict[str, object]:
    handoff, trust_envelope = _build_handoff(
        environment,
        launch_provenance=launch_provenance,
    )
    env["QWQ_IOS_STACKCTL_PYTHON"] = str(runtime_python)
    env["QWQ_APP_LAUNCH_PROVENANCE"] = launch_provenance
    env["QWQ_RUNTIME_CONFIG_SUPPLY_MODE"] = str(
        handoff["runtimeConfigSupplyMode"]
    )
    env["QWQ_APP_BUILD_PROFILE"] = str(handoff["buildProfile"])
    env["QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH"] = str(
        _write_trust_envelope(artifact_root, trust_envelope)
    )
    env["TARGET_BUILD_DIR"] = str(artifact_root / "build")
    env["UNLOCALIZED_RESOURCES_FOLDER_PATH"] = "Runner.app"
    return handoff


def _decode_export(stdout: str) -> dict[str, str]:
    line = next(
        item for item in stdout.splitlines() if item.startswith("export DART_DEFINES=")
    )
    assignment = shlex.split(line.removeprefix("export "))[0]
    encoded = assignment.split("=", 1)[1]
    values: dict[str, str] = {}
    if encoded == "__QWQ_COMPILE_ONLY__":
        return values
    for item in encoded.split(","):
        decoded = base64.b64decode(item).decode("utf-8")
        key, value = decoded.split("=", 1)
        values[key] = value
    return values


def _encode_defines(defines: dict[str, object]) -> str:
    return ",".join(
        base64.b64encode(f"{key}={value}".encode()).decode()
        for key, value in sorted(defines.items())
    )


def _bound_test_live_handoff() -> dict[str, object]:
    handoff, _ = build_test_handoff_fixture(
        launcher,
        "alpha",
        "alpha-local",
        launch_provenance="canonical_launcher",
    )
    return handoff


def _write_passthrough_python(directory: Path) -> Path:
    executable = directory / "runtime-python"
    executable.write_text(
        f"#!/usr/bin/env bash\nexec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _install_direct_handoff(
    environment: dict[str, str],
    runtime_environment: str,
    artifact_root: Path,
) -> dict[str, object]:
    handoff, trust_envelope = _build_handoff(
        runtime_environment,
        launch_provenance="workspace_flutter_run",
    )
    environment["QWQ_TEST_LAUNCHER_HANDOFF_JSON"] = json.dumps(
        handoff,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    environment["QWQ_APP_BUILD_PROFILE"] = str(handoff["buildProfile"])
    environment["QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH"] = str(
        _write_trust_envelope(artifact_root, trust_envelope)
    )
    environment["TARGET_BUILD_DIR"] = str(artifact_root / "build")
    environment["UNLOCALIZED_RESOURCES_FOLDER_PATH"] = "Runner.app"
    return handoff
