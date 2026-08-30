"""Cursor terminal surface 投影身份、回执读取与探针。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PROFILE_SURFACE_UNKNOWN = "unknown"
PROFILE_SURFACES = frozenset({"folder-new-terminal", "agents-window"})
PROFILE_SURFACE_VALUES = PROFILE_SURFACES | {PROFILE_SURFACE_UNKNOWN}
PROFILE_LAUNCHER_PATH = Path(__file__).resolve().with_name("cursor_terminal_profile.zsh")
RECEIPT_TOOL_PATH = Path(__file__).resolve().with_name("terminal_surface_receipt.py")
RECEIPT_ROOT = REPO_ROOT / ".qwq_output/env/repo/local/flutter-facade-terminal-receipts"


def canonical_digest(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def sdk_binding_seal(binding: dict[str, str]) -> str:
    return canonical_digest(binding)


def cocoapods_binding_seal(binding: dict[str, str]) -> str:
    return binding["QWQ_COCOAPODS_BINDING_SEAL"]


def python_binding_seal(binding: dict[str, str]) -> str:
    return canonical_digest(binding)


def projection_seal(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
) -> str:
    return canonical_digest(
        {
            "sdkBindingSeal": sdk_binding_seal(sdk_binding),
            "cocoaPodsBindingSeal": cocoapods_binding_seal(cocoapods_binding),
            "pythonBindingSeal": python_binding_seal(python_binding),
        }
    )


def _projection_artifact_digests() -> tuple[str, str]:
    launcher_digest = "sha256:" + hashlib.sha256(
        PROFILE_LAUNCHER_PATH.read_bytes()
    ).hexdigest()
    receipt_tool_digest = "sha256:" + hashlib.sha256(
        RECEIPT_TOOL_PATH.read_bytes()
    ).hexdigest()
    return launcher_digest, receipt_tool_digest


def legacy_projection_generation(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
) -> str:
    launcher_digest, receipt_tool_digest = _projection_artifact_digests()
    return canonical_digest(
        {
            "profileLauncherDigest": launcher_digest,
            "receiptToolDigest": receipt_tool_digest,
            "sdkBindingSeal": sdk_binding_seal(sdk_binding),
            "cocoaPodsBindingSeal": cocoapods_binding_seal(cocoapods_binding),
            "workspacePhysicalRoot": str(REPO_ROOT.resolve(strict=True)),
        }
    )


def projection_generation(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
) -> str:
    launcher_digest, receipt_tool_digest = _projection_artifact_digests()
    return canonical_digest(
        {
            "profileLauncherDigest": launcher_digest,
            "receiptToolDigest": receipt_tool_digest,
            "projectionSeal": projection_seal(
                sdk_binding, cocoapods_binding, python_binding
            ),
            "workspacePhysicalRoot": str(REPO_ROOT.resolve(strict=True)),
        }
    )


def load_receipt_module():
    spec = importlib.util.spec_from_file_location(
        "qwq_terminal_surface_receipt", RECEIPT_TOOL_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load terminal receipt module: {RECEIPT_TOOL_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def surface_receipt_state(
    *,
    surface: str | None,
    sdk_binding: dict[str, str] | None,
    cocoapods_binding: dict[str, str] | None,
    python_binding: dict[str, str] | None,
    receipt_root: Path,
    max_age_seconds: int,
    now_epoch_ms: int | None,
) -> str:
    if surface is None:
        return "not_requested"
    if surface not in PROFILE_SURFACES:
        return "unsupported_surface"
    if (
        sdk_binding is None
        or cocoapods_binding is None
        or python_binding is None
    ):
        return "projection_invalid"
    receipt_module = load_receipt_module()
    try:
        root = receipt_root.resolve(strict=True)
    except OSError:
        return "missing"
    expected_root = REPO_ROOT.resolve(strict=True)
    expected_facade = (
        REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/bin/flutter"
    ).resolve(strict=True)
    expected_identity = {
        "facadeBinRealpath": str(expected_facade.parent),
        "realFlutterRealpath": sdk_binding["executable"],
        "realFlutterVersion": sdk_binding["flutterVersion"],
        "commandResolutionDigest": sdk_binding["commandResolutionDigest"],
    }
    expected_seal = projection_seal(
        sdk_binding, cocoapods_binding, python_binding
    )
    expected_generation = projection_generation(
        sdk_binding, cocoapods_binding, python_binding
    )
    current_ms = time.time_ns() // 1_000_000 if now_epoch_ms is None else now_epoch_ms
    saw_surface_receipt = False
    saw_invalid = False
    for candidate in sorted(root.glob(f"{surface}--*.json"), reverse=True):
        saw_surface_receipt = True
        try:
            payload = receipt_module.load_receipt(candidate)
            if payload["surface"] != surface:
                raise ValueError("surface mismatch")
            if payload["workspacePhysicalRoot"] != str(expected_root):
                raise ValueError("physical root mismatch")
            if Path(str(payload["workspaceLogicalRoot"])).resolve(strict=True) != expected_root:
                raise ValueError("logical root mismatch")
            if payload["workspaceUri"] not in {
                payload["workspaceLogicalRoot"],
                Path(str(payload["workspaceLogicalRoot"])).as_uri(),
            }:
                raise ValueError("workspace URI mismatch")
            if payload["finalStateValidated"] is not True:
                raise ValueError("final terminal state was not validated")
            if payload["facadeRealpath"] != str(expected_facade):
                raise ValueError("facade mismatch")
            if payload["qwqIdentity"] != expected_identity:
                raise ValueError("QWQ identity mismatch")
            if payload["projectionSeal"] != expected_seal:
                raise ValueError("projection seal mismatch")
            if payload["projectionGeneration"] != expected_generation:
                raise ValueError("projection generation mismatch")
            written_at = int(payload["writtenAtEpochMs"])
            if written_at > current_ms + 5_000:
                raise ValueError("receipt time is in the future")
            if current_ms - written_at > max_age_seconds * 1000:
                raise ValueError("receipt is stale")
            pid = int(payload["shellPid"])
            if receipt_module.process_start(pid) != payload["shellStart"]:
                raise ValueError("shell PID/start identity is stale")
        except (json.JSONDecodeError, OSError, RuntimeError, TypeError, ValueError):
            saw_invalid = True
            continue
        return "active"
    if saw_invalid:
        return "invalid_or_stale"
    return "missing" if not saw_surface_receipt else "invalid_or_stale"


def probe_surface(
    *,
    surface: str,
    environ: dict[str, str] | None = None,
    receipt_root: Path = RECEIPT_ROOT,
) -> Path:
    if surface not in PROFILE_SURFACES:
        raise SystemExit("GATE_BLOCK: unsupported terminal surface")
    env = dict(os.environ if environ is None else environ)
    try:
        shell_pid = int(env.get("QWQ_TERMINAL_SHELL_PID", "0"))
        if shell_pid != os.getppid() and shell_pid != os.getpid():
            raise ValueError("probe is not running in the projected terminal shell")
        workspace_uri = env.get("QWQ_TERMINAL_WORKSPACE_URI", "")
        logical_root = env.get("QWQ_TERMINAL_WORKSPACE_LOGICAL_ROOT", "")
        if not logical_root:
            logical_root = workspace_uri.removeprefix("file://")
        physical_root = str(Path(logical_root).resolve(strict=True))
        receipt_module = load_receipt_module()
        expected_facade = (
            REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/bin/flutter"
        ).resolve(strict=True)
        expected_pod = Path(env.get("QWQ_COCOAPODS_EXECUTABLE", "")).resolve(
            strict=True
        )
        resolved_flutter = Path(
            __import__("shutil").which("flutter", path=env.get("PATH", "")) or ""
        ).resolve(strict=True)
        resolved_pod = Path(
            __import__("shutil").which("pod", path=env.get("PATH", "")) or ""
        ).resolve(strict=True)
        if resolved_flutter != expected_facade or resolved_pod != expected_pod:
            raise ValueError("optional probe final command resolution differs")
        env["QWQ_TERMINAL_FINAL_FLUTTER_COMMAND_REALPATH"] = str(resolved_flutter)
        env["QWQ_TERMINAL_FINAL_POD_COMMAND_REALPATH"] = str(resolved_pod)
        return receipt_module.write_receipt(
            surface=surface,
            shell_pid=shell_pid,
            workspace_uri=workspace_uri,
            logical_root=logical_root,
            physical_root=physical_root,
            environ=env,
            receipt_root=receipt_root,
        )
    except (json.JSONDecodeError, OSError, RuntimeError, TypeError, ValueError) as error:
        raise SystemExit(
            "GATE_BLOCK: APP.LAUNCH.workspace_entrypoint_inactive; "
            f"terminal surface probe failed: {error}"
        ) from error
