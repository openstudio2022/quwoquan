#!/usr/bin/env python3
"""工作区 flutter facade 的受版本控制激活入口。

把 facade 的 PATH、本机真实 `FLUTTER_ROOT`、受控 ZDOTDIR bridge 与 Dart-Code
PATH 策略合并进本机 `.vscode/settings.json`（gitignore 的本地投影）。Cursor 从
Dock 启动时进程 PATH 通常不含 Flutter；激活时把真实 SDK 钉进终端 env，使新开
集成终端 / automation 终端不依赖用户是否已 source `~/.zshrc`。同一个 zsh 仍先
代理用户 startup files，再把 facade 放回 PATH 首位，字面 `flutter run` 归一化进
canonical launcher；仓库外终端与系统 Flutter 不受影响。

- 激活：python3 quwoquan_app/scripts/tools/flutter_facade/activate_cursor_workspace.py
- 回退：同命令加 `--deactivate`，随后重载编辑器窗口即回到真实 SDK 直连。
- 本地投影可随时删除；凭本脚本可完全重建，符合「激活面可凭受版本控制
  真相源重建」的规格要求（environment-topology-and-packaging REQ-003）。

合并策略是标记块文本级增删：保留用户注释与既有配置；发现非本工具管理的
`dart.addSdkToTerminalPath` 或 `terminal.integrated.env.osx` 时拒绝静默覆盖。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_app.scripts.tools.flutter_facade import (
    cursor_terminal_surface_state as _terminal_surface_state,
)
from quwoquan_app.scripts.tools.flutter_facade import (
    cursor_workspace_projection_io as _workspace_projection_io,
)
DEFAULT_SETTINGS_PATH = REPO_ROOT / ".vscode/settings.json"
DEFAULT_TASKS_PATH = REPO_ROOT / ".vscode/tasks.json"
DEFAULT_LAUNCH_PATH = REPO_ROOT / ".vscode/launch.json"
GENERATED_APP_LAUNCH_CONTRACT_PATH = (
    REPO_ROOT
    / "quwoquan_app/tool/app_launch_contract_codegen/app_launch_contract.generated.json"
)
BEGIN_MARKER = "// qwq-flutter-facade-begin"
END_MARKER = "// qwq-flutter-facade-end"
MANAGED_DART_KEY = "dart.addSdkToTerminalPath"
MANAGED_ENV_KEY = "terminal.integrated.env.osx"
MANAGED_PROFILES_KEY = "terminal.integrated.profiles.osx"
MANAGED_DEFAULT_PROFILE_KEY = "terminal.integrated.defaultProfile.osx"
MANAGED_KEYS = (
    MANAGED_DART_KEY,
    MANAGED_ENV_KEY,
    MANAGED_PROFILES_KEY,
    MANAGED_DEFAULT_PROFILE_KEY,
)
GENERATED_MARKER = _workspace_projection_io.GENERATED_MARKER
FACADE_BIN_VALUE = "${workspaceFolder}/quwoquan_app/scripts/tools/flutter_facade/bin"
ZDOTDIR_VALUE = (
    "${workspaceFolder}/quwoquan_app/scripts/tools/flutter_facade/zsh_projection"
)
PROFILE_NAME = "QuWoQuan Workspace Flutter Facade"
PROFILE_LAUNCHER_VALUE = (
    "${workspaceFolder}/quwoquan_app/scripts/tools/flutter_facade/"
    "cursor_terminal_profile.zsh"
)
PROFILE_SURFACE_UNKNOWN = _terminal_surface_state.PROFILE_SURFACE_UNKNOWN
PROFILE_SURFACES = _terminal_surface_state.PROFILE_SURFACES
PROFILE_SURFACE_VALUES = _terminal_surface_state.PROFILE_SURFACE_VALUES
PROFILE_LAUNCHER_PATH = _terminal_surface_state.PROFILE_LAUNCHER_PATH
RECEIPT_TOOL_PATH = _terminal_surface_state.RECEIPT_TOOL_PATH
RECEIPT_ROOT = _terminal_surface_state.RECEIPT_ROOT
SDK_EXECUTABLE_KEY = "QWQ_REAL_FLUTTER"
SDK_VERSION_KEY = "QWQ_REAL_FLUTTER_VERSION"
SDK_IDENTITY_KEY = "QWQ_REAL_FLUTTER_COMMAND_RESOLUTION_DIGEST"
SDK_STATUS_KEYS = (
    SDK_EXECUTABLE_KEY,
    SDK_VERSION_KEY,
    SDK_IDENTITY_KEY,
)
PYTHON_EXECUTABLE_KEY = "QWQ_WORKSPACE_PYTHON"
PYTHON_VERSION_KEY = "QWQ_WORKSPACE_PYTHON_VERSION"
PYTHON_STATUS_KEYS = (PYTHON_EXECUTABLE_KEY, PYTHON_VERSION_KEY)
PYTHON_MINIMUM_VERSION = (3, 10)
TRUSTED_PYTHON_PREFIXES = (Path("/opt/homebrew/bin"), Path("/usr/local/bin"))
PYTHON_BINDING_MARKER_PREFIX = "// qwq-workspace-python-binding "
SDK_BINDING_MARKER_PREFIX = "// qwq-flutter-sdk-binding "
PROJECTION_MARKER_PREFIX = "// qwq-flutter-terminal-projection "
_SHA256_IDENTITY_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
LEGACY_MANAGED_ENV_KEYS = frozenset(
    {
        "PATH",
        "QWQ_WORKSPACE_FLUTTER_FACADE_BIN",
        "QWQ_WORKSPACE_ORIGINAL_ZDOTDIR",
        "ZDOTDIR",
        "FLUTTER_ROOT",
        SDK_EXECUTABLE_KEY,
    }
)


def _load_canonical_launch_blockers() -> frozenset[str]:
    """从 codegen 产物读取 launcher blocker 闭集，拒绝本地第二枚举。"""
    try:
        contract = json.loads(
            GENERATED_APP_LAUNCH_CONTRACT_PATH.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeError("generated App launch contract is unavailable") from error
    blockers = contract.get("launchBlockers")
    if contract.get("schema") != "qwq.app-launch-contract.generated" or not isinstance(
        blockers, dict
    ):
        raise RuntimeError("generated App launch blocker closure is invalid")
    if not blockers or any(
        not isinstance(code, str)
        or not code
        or not isinstance(description, str)
        or not description
        for code, description in blockers.items()
    ):
        raise RuntimeError("generated App launch blocker closure is invalid")
    return frozenset(blockers)


CANONICAL_LAUNCH_BLOCKERS = _load_canonical_launch_blockers()


def _canonical_launch_blocker(code: str) -> str:
    if code not in CANONICAL_LAUNCH_BLOCKERS:
        raise RuntimeError(f"unregistered App launch blocker: {code}")
    return code


WORKSPACE_FLUTTER_SDK_UNAVAILABLE_BLOCKER = _canonical_launch_blocker(
    "APP.LAUNCH.workspace_flutter_sdk_unavailable"
)
COCOAPODS_MISSING_BLOCKER = _canonical_launch_blocker(
    "APP.DEPENDENCY.cocoapods_missing"
)
COCOAPODS_MIXED_BLOCKER = _canonical_launch_blocker(
    "APP.DEPENDENCY.cocoapods_mixed"
)


def _load_canonical_facade_module():
    module_path = Path(__file__).resolve().with_name("flutter_facade.py")
    spec = importlib.util.spec_from_file_location(
        "qwq_workspace_flutter_facade_canonical", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load canonical Flutter facade: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CANONICAL_FACADE = _load_canonical_facade_module()


def _load_canonical_cocoapods_module():
    module_path = REPO_ROOT / "quwoquan_ops/cli/lib/app_dependency_toolchain.py"
    spec = importlib.util.spec_from_file_location(
        "qwq_workspace_app_dependency_toolchain", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"unable to load canonical App dependency toolchain: {module_path}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


_CANONICAL_COCOAPODS = _load_canonical_cocoapods_module()
COCOAPODS_STATUS_KEYS = tuple(_CANONICAL_COCOAPODS.COCOAPODS_ENVIRONMENT_KEYS)
COCOAPODS_BINDING_MARKER_PREFIX = "// qwq-cocoapods-binding "


def _resolved_sdk_binding(environ: dict[str, str]) -> dict[str, str]:
    """只消费 canonical facade 的解析/版本/identity API，不维护第二 resolver。"""
    identity = _CANONICAL_FACADE.resolved_flutter_identity(dict(environ))
    executable = str(identity.get("executable") or "").strip()
    version = str(identity.get("flutterVersion") or "").strip()
    digest = str(identity.get("commandResolutionDigest") or "").strip()
    if not executable or not version or not _SHA256_IDENTITY_PATTERN.fullmatch(digest):
        raise _CANONICAL_FACADE.FacadeError(
            "canonical Flutter SDK identity 缺少 executable/version/digest"
        )
    physical_executable = Path(executable).resolve(strict=True)
    return {
        "flutterRoot": str(physical_executable.parent.parent),
        "executable": str(physical_executable),
        "flutterVersion": version,
        "commandResolutionDigest": digest,
    }


def _resolved_cocoapods_binding(environ: dict[str, str]) -> dict[str, str]:
    candidate = str(environ.get("QWQ_COCOAPODS_EXECUTABLE") or "").strip()
    identity = _CANONICAL_COCOAPODS.resolve_cocoapods_identity(
        candidate,
        search_path=str(environ.get("PATH") or ""),
    )
    resolved = identity.as_environment()
    present = {
        key for key in COCOAPODS_STATUS_KEYS if str(environ.get(key) or "").strip()
    }
    if present:
        declared = _CANONICAL_COCOAPODS.cocoapods_identity_from_environment(environ)
        if declared.as_environment() != resolved:
            raise _CANONICAL_COCOAPODS.AppDependencyToolchainError(
                f"{COCOAPODS_MIXED_BLOCKER}: declared CocoaPods identity differs "
                "from resolved identity"
            )
    return resolved


_canonical_digest = _terminal_surface_state.canonical_digest
_sdk_binding_seal = _terminal_surface_state.sdk_binding_seal
_cocoapods_binding_seal = _terminal_surface_state.cocoapods_binding_seal
_python_binding_seal = _terminal_surface_state.python_binding_seal
_projection_seal = _terminal_surface_state.projection_seal
_projection_generation = _terminal_surface_state.projection_generation


def _inspect_python(candidate: Path) -> dict[str, str] | None:
    try:
        path_metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        resolved_metadata = resolved.stat()
    except OSError:
        return None
    if not stat.S_ISREG(resolved_metadata.st_mode) or not os.access(resolved, os.X_OK):
        return None
    if (
        path_metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or resolved_metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        return None
    completed = subprocess.run(
        [
            str(resolved),
            "-I",
            "-c",
            (
                "import json,os,sys; "
                "print(json.dumps({"
                "'executable':os.path.realpath(sys.executable),"
                "'version':[sys.version_info.major,sys.version_info.minor,"
                "sys.version_info.micro]}))"
            ),
        ],
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
        version_parts = tuple(int(value) for value in payload["version"])
        executable = Path(str(payload["executable"])).resolve(strict=True)
    except (json.JSONDecodeError, KeyError, OSError, TypeError, ValueError):
        return None
    if len(version_parts) != 3 or version_parts < PYTHON_MINIMUM_VERSION or executable != resolved:
        return None
    return {
        "executable": str(resolved),
        "version": ".".join(str(value) for value in version_parts),
    }


def _resolved_python_binding(environ: dict[str, str]) -> dict[str, str]:
    declared = str(environ.get(PYTHON_EXECUTABLE_KEY) or "").strip()
    candidates: list[Path] = []
    if declared:
        candidates.append(Path(declared))
    else:
        current_python = Path(sys.executable)
        candidates.append(current_python)
        resolved_from_path = shutil.which("python3", path=environ.get("PATH", ""))
        if resolved_from_path:
            path_candidate = Path(resolved_from_path)
            if any(
                path_candidate.parent.resolve(strict=False)
                == prefix.resolve(strict=False)
                for prefix in TRUSTED_PYTHON_PREFIXES
            ):
                candidates.append(path_candidate)
        for trusted_prefix in TRUSTED_PYTHON_PREFIXES:
            candidate = trusted_prefix / "python3"
            if candidate not in candidates:
                candidates.append(candidate)
    for candidate in candidates:
        binding = _inspect_python(candidate)
        if binding is None:
            continue
        declared_version = str(environ.get(PYTHON_VERSION_KEY) or "").strip()
        if declared and not declared_version:
            raise ValueError("projected workspace Python version is missing")
        if declared and binding["version"] != declared_version:
            raise ValueError(
                "projected workspace Python version differs from physical identity"
            )
        return binding
    raise ValueError("workspace terminal requires a trusted physical Python 3.10+")


def _managed_terminal_env(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
) -> dict[str, str]:
    flutter_root = Path(sdk_binding["flutterRoot"])
    real_bin = flutter_root / "bin"
    pod_bin = Path(cocoapods_binding["QWQ_COCOAPODS_EXECUTABLE"]).parent
    env: dict[str, str] = {
        "PATH": f"{FACADE_BIN_VALUE}:{real_bin}:{pod_bin}:${{env:PATH}}",
        "QWQ_WORKSPACE_FLUTTER_FACADE_BIN": FACADE_BIN_VALUE,
        "QWQ_WORKSPACE_ORIGINAL_ZDOTDIR": "${env:ZDOTDIR}",
        "ZDOTDIR": ZDOTDIR_VALUE,
        "FLUTTER_ROOT": str(flutter_root),
        SDK_EXECUTABLE_KEY: sdk_binding["executable"],
        SDK_VERSION_KEY: sdk_binding["flutterVersion"],
        SDK_IDENTITY_KEY: sdk_binding["commandResolutionDigest"],
        PYTHON_EXECUTABLE_KEY: python_binding["executable"],
        PYTHON_VERSION_KEY: python_binding["version"],
        **cocoapods_binding,
    }
    return env


def _managed_profile(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
) -> dict[str, object]:
    return {
        "path": PROFILE_LAUNCHER_VALUE,
        "args": [],
        "env": {
            "QWQ_TERMINAL_SURFACE": PROFILE_SURFACE_UNKNOWN,
            "QWQ_TERMINAL_PROJECTION_SEAL": _projection_seal(
                sdk_binding, cocoapods_binding, python_binding
            ),
            "QWQ_TERMINAL_PROJECTION_GENERATION": _projection_generation(
                sdk_binding, cocoapods_binding, python_binding
            ),
            "QWQ_TERMINAL_WORKSPACE_URI": "${workspaceFolder}",
            "FLUTTER_ROOT": sdk_binding["flutterRoot"],
            SDK_EXECUTABLE_KEY: sdk_binding["executable"],
            SDK_VERSION_KEY: sdk_binding["flutterVersion"],
            SDK_IDENTITY_KEY: sdk_binding["commandResolutionDigest"],
            PYTHON_EXECUTABLE_KEY: python_binding["executable"],
            PYTHON_VERSION_KEY: python_binding["version"],
            **cocoapods_binding,
        },
    }


def _managed_profiles(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
) -> dict[str, object]:
    return {
        PROFILE_NAME: _managed_profile(
            sdk_binding, cocoapods_binding, python_binding
        )
    }


def _stored_cocoapods_binding(text: str) -> dict[str, str]:
    parsed = _parse_settings(text)
    env = parsed.get(MANAGED_ENV_KEY)
    if not isinstance(env, dict):
        raise TypeError("managed terminal environment is missing")
    return _CANONICAL_COCOAPODS.cocoapods_identity_from_environment(
        env,
        inspect_physical=False,
    ).as_environment()


def _stored_python_binding(text: str) -> dict[str, str]:
    parsed = _parse_settings(text)
    env = parsed.get(MANAGED_ENV_KEY)
    if not isinstance(env, dict):
        raise TypeError("managed terminal environment is missing")
    executable = str(env.get(PYTHON_EXECUTABLE_KEY) or "").strip()
    version = str(env.get(PYTHON_VERSION_KEY) or "").strip()
    if not executable or not version:
        raise ValueError("managed workspace Python identity is incomplete")
    binding = _inspect_python(Path(executable))
    if binding is None or binding["version"] != version:
        raise ValueError("managed workspace Python identity differs from physical runtime")
    return binding


def _stored_sdk_binding(text: str) -> dict[str, str]:
    parsed = _parse_settings(text)
    env = parsed.get(MANAGED_ENV_KEY)
    if not isinstance(env, dict):
        raise TypeError("managed terminal environment is missing")
    flutter_root = str(env.get("FLUTTER_ROOT") or "").strip()
    executable = str(env.get(SDK_EXECUTABLE_KEY) or "").strip()
    version = str(env.get(SDK_VERSION_KEY) or "").strip()
    digest = str(env.get(SDK_IDENTITY_KEY) or "").strip()
    if not flutter_root or not executable or not version or not digest:
        raise ValueError("managed Flutter SDK status fields are incomplete")
    if Path(executable) != Path(flutter_root) / "bin" / "flutter":
        raise ValueError("managed Flutter SDK root/executable fields disagree")
    expected_version = (
        (REPO_ROOT / "quwoquan_app/.flutter-version")
        .read_text(encoding="utf-8")
        .strip()
    )
    if version != expected_version:
        raise ValueError("managed Flutter SDK version differs from workspace pin")
    if not _SHA256_IDENTITY_PATTERN.fullmatch(digest):
        raise ValueError("managed Flutter SDK identity is invalid")
    return {
        "flutterRoot": flutter_root,
        "executable": executable,
        "flutterVersion": version,
        "commandResolutionDigest": digest,
    }


def _settings_lines(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
    *,
    indent: str = "    ",
) -> list[str]:
    terminal_env = _managed_terminal_env(
        sdk_binding, cocoapods_binding, python_binding
    )
    profiles = _managed_profiles(sdk_binding, cocoapods_binding, python_binding)
    settings = [
        (MANAGED_DART_KEY, False),
        (MANAGED_ENV_KEY, terminal_env),
        (MANAGED_PROFILES_KEY, profiles),
        (MANAGED_DEFAULT_PROFILE_KEY, PROFILE_NAME),
    ]
    lines: list[str] = []
    for index, (key, value) in enumerate(settings):
        encoded = json.dumps(value, ensure_ascii=False, indent=4).splitlines()
        suffix = ","
        if len(encoded) == 1:
            lines.append(f"{indent}{json.dumps(key)}: {encoded[0]}{suffix}")
            continue
        lines.append(f"{indent}{json.dumps(key)}: {encoded[0]}")
        for encoded_line in encoded[1:-1]:
            lines.append(f"{indent}{encoded_line}")
        lines.append(f"{indent}{encoded[-1]}{suffix}")
    return lines


def _managed_block(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
    indent: str = "    ",
) -> str:
    lines = [
        f"{indent}{BEGIN_MARKER}",
        (
            f"{indent}// 由 activate_cursor_workspace.py 管理，勿手改；"
            "回退：--deactivate 后重载窗口。"
        ),
        f"{indent}{SDK_BINDING_MARKER_PREFIX}{_sdk_binding_seal(sdk_binding)}",
        (
            f"{indent}{PYTHON_BINDING_MARKER_PREFIX}"
            f"{_python_binding_seal(python_binding)}"
        ),
        (
            f"{indent}{COCOAPODS_BINDING_MARKER_PREFIX}"
            f"{_cocoapods_binding_seal(cocoapods_binding)}"
        ),
        (
            f"{indent}{PROJECTION_MARKER_PREFIX}"
            f"{_projection_generation(sdk_binding, cocoapods_binding, python_binding)}"
        ),
        *_settings_lines(
            sdk_binding, cocoapods_binding, python_binding, indent=indent
        ),
        f"{indent}{END_MARKER}",
    ]
    return "\n".join(lines)


def _managed_segment(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
) -> str:
    return (
        "\n"
        + _managed_block(sdk_binding, cocoapods_binding, python_binding)
        + "\n"
    )


def _pre_python_identity_managed_segment(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
) -> str:
    terminal_env = _managed_terminal_env(
        sdk_binding, cocoapods_binding, python_binding
    )
    profiles = _managed_profiles(
        sdk_binding, cocoapods_binding, python_binding
    )
    profile_env = profiles[PROFILE_NAME]["env"]
    if not isinstance(profile_env, dict):
        raise TypeError("managed terminal profile environment is invalid")
    profile_env["QWQ_TERMINAL_PROJECTION_SEAL"] = _sdk_binding_seal(
        sdk_binding
    )
    profile_env[
        "QWQ_TERMINAL_PROJECTION_GENERATION"
    ] = _terminal_surface_state.legacy_projection_generation(
        sdk_binding, cocoapods_binding
    )
    settings = [
        (MANAGED_DART_KEY, False),
        (MANAGED_ENV_KEY, terminal_env),
        (MANAGED_PROFILES_KEY, profiles),
        (MANAGED_DEFAULT_PROFILE_KEY, PROFILE_NAME),
    ]
    lines = [
        f"    {BEGIN_MARKER}",
        (
            "    // 由 activate_cursor_workspace.py 管理，勿手改；"
            "回退：--deactivate 后重载窗口。"
        ),
        f"    {SDK_BINDING_MARKER_PREFIX}{_sdk_binding_seal(sdk_binding)}",
        (
            f"    {PYTHON_BINDING_MARKER_PREFIX}"
            f"{_python_binding_seal(python_binding)}"
        ),
        (
            f"    {COCOAPODS_BINDING_MARKER_PREFIX}"
            f"{_cocoapods_binding_seal(cocoapods_binding)}"
        ),
        (
            f"    {PROJECTION_MARKER_PREFIX}"
            f"{_terminal_surface_state.legacy_projection_generation(sdk_binding, cocoapods_binding)}"
        ),
    ]
    for key, value in settings:
        encoded = json.dumps(value, ensure_ascii=False, indent=4).splitlines()
        if len(encoded) == 1:
            lines.append(f"    {json.dumps(key)}: {encoded[0]},")
            continue
        lines.append(f"    {json.dumps(key)}: {encoded[0]}")
        lines.extend(f"    {encoded_line}" for encoded_line in encoded[1:-1])
        lines.append(f"    {encoded[-1]},")
    lines.append(f"    {END_MARKER}")
    return "\n" + "\n".join(lines) + "\n"


def _pre_python_managed_segment(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
) -> str:
    sentinel_python = {"executable": "", "version": ""}
    terminal_env = _managed_terminal_env(
        sdk_binding, cocoapods_binding, sentinel_python
    )
    for key in PYTHON_STATUS_KEYS:
        terminal_env.pop(key)
    profiles = _managed_profiles(
        sdk_binding, cocoapods_binding, sentinel_python
    )
    profile_env = profiles[PROFILE_NAME]["env"]
    if not isinstance(profile_env, dict):
        raise TypeError("managed terminal profile environment is invalid")
    for key in PYTHON_STATUS_KEYS:
        profile_env.pop(key)
    profile_env["QWQ_TERMINAL_PROJECTION_SEAL"] = _sdk_binding_seal(
        sdk_binding
    )
    profile_env[
        "QWQ_TERMINAL_PROJECTION_GENERATION"
    ] = _terminal_surface_state.legacy_projection_generation(
        sdk_binding, cocoapods_binding
    )
    settings = [
        (MANAGED_DART_KEY, False),
        (MANAGED_ENV_KEY, terminal_env),
        (MANAGED_PROFILES_KEY, profiles),
        (MANAGED_DEFAULT_PROFILE_KEY, PROFILE_NAME),
    ]
    lines = [
        f"    {BEGIN_MARKER}",
        (
            "    // 由 activate_cursor_workspace.py 管理，勿手改；"
            "回退：--deactivate 后重载窗口。"
        ),
        f"    {SDK_BINDING_MARKER_PREFIX}{_sdk_binding_seal(sdk_binding)}",
        (
            f"    {COCOAPODS_BINDING_MARKER_PREFIX}"
            f"{_cocoapods_binding_seal(cocoapods_binding)}"
        ),
        (
            f"    {PROJECTION_MARKER_PREFIX}"
            f"{_terminal_surface_state.legacy_projection_generation(sdk_binding, cocoapods_binding)}"
        ),
    ]
    for key, value in settings:
        encoded = json.dumps(value, ensure_ascii=False, indent=4).splitlines()
        if len(encoded) == 1:
            lines.append(f"    {json.dumps(key)}: {encoded[0]},")
            continue
        lines.append(f"    {json.dumps(key)}: {encoded[0]}")
        lines.extend(f"    {encoded_line}" for encoded_line in encoded[1:-1])
        lines.append(f"    {encoded[-1]},")
    lines.append(f"    {END_MARKER}")
    return "\n" + "\n".join(lines) + "\n"


def _strip_line_comments(text: str) -> str:
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def _parse_settings(text: str) -> dict:
    stripped = _strip_line_comments(text)
    stripped = re.sub(r",(\s*[}\]])", r"\1", stripped).strip()
    if not stripped:
        return {}
    return json.loads(stripped)


def _marked_managed_segment(text: str) -> str:
    begin_count = text.count(BEGIN_MARKER)
    end_count = text.count(END_MARKER)
    if begin_count != 1 or end_count != 1:
        raise ValueError("managed settings markers are malformed")
    begin = text.index(BEGIN_MARKER)
    end = text.index(END_MARKER, begin) + len(END_MARKER)
    if "\n" not in text[:begin] or not text[end:].startswith("\n"):
        raise ValueError("managed settings segment boundaries are drifted")
    segment_start = text.rfind("\n", 0, begin)
    segment_end = end + 1
    return text[segment_start:segment_end]


def _exact_pre_python_identity_managed_segment(text: str) -> str:
    segment = _marked_managed_segment(text)
    sdk_binding = _stored_sdk_binding(text)
    cocoapods_binding = _stored_cocoapods_binding(text)
    python_binding = _stored_python_binding(text)
    expected = _pre_python_identity_managed_segment(
        sdk_binding, cocoapods_binding, python_binding
    )
    if (
        text.count(SDK_BINDING_MARKER_PREFIX) != 1
        or text.count(PYTHON_BINDING_MARKER_PREFIX) != 1
        or text.count(COCOAPODS_BINDING_MARKER_PREFIX) != 1
        or text.count(PROJECTION_MARKER_PREFIX) != 1
        or segment != expected
    ):
        raise ValueError(
            "pre-Python-identity managed settings projection is drifted"
        )
    return segment


def _exact_pre_python_managed_segment(text: str) -> str:
    segment = _marked_managed_segment(text)
    if PYTHON_BINDING_MARKER_PREFIX in text:
        raise ValueError("pre-Python projection contains a Python marker")
    parsed = _parse_settings(text)
    env = parsed.get(MANAGED_ENV_KEY)
    profiles = parsed.get(MANAGED_PROFILES_KEY)
    if not isinstance(env, dict) or any(key in env for key in PYTHON_STATUS_KEYS):
        raise ValueError("pre-Python terminal environment is invalid")
    if not isinstance(profiles, dict):
        raise ValueError("pre-Python terminal profiles are invalid")
    profile = profiles.get(PROFILE_NAME)
    profile_env = profile.get("env") if isinstance(profile, dict) else None
    if not isinstance(profile_env, dict) or any(
        key in profile_env for key in PYTHON_STATUS_KEYS
    ):
        raise ValueError("pre-Python terminal profile environment is invalid")
    sdk_binding = _stored_sdk_binding(text)
    cocoapods_binding = _stored_cocoapods_binding(text)
    expected = _pre_python_managed_segment(sdk_binding, cocoapods_binding)
    if (
        text.count(SDK_BINDING_MARKER_PREFIX) != 1
        or text.count(COCOAPODS_BINDING_MARKER_PREFIX) != 1
        or text.count(PROJECTION_MARKER_PREFIX) != 1
        or segment != expected
    ):
        raise ValueError("pre-Python managed settings projection is drifted")
    return segment


def _exact_legacy_managed_segment(text: str) -> str:
    segment = _marked_managed_segment(text)
    if PROJECTION_MARKER_PREFIX in text:
        raise ValueError("legacy managed settings contain a current projection marker")
    parsed = _parse_settings(text)
    if PYTHON_BINDING_MARKER_PREFIX in text:
        raise ValueError(
            "legacy managed settings contain a current Python marker"
        )
    if COCOAPODS_BINDING_MARKER_PREFIX in text:
        raise ValueError(
            "legacy managed settings contain a current CocoaPods marker"
        )
    if any(
        key in parsed
        for key in (MANAGED_PROFILES_KEY, MANAGED_DEFAULT_PROFILE_KEY)
    ):
        raise ValueError("legacy managed settings contain terminal profile keys")
    if parsed.get(MANAGED_DART_KEY) is not False:
        raise ValueError("legacy Dart terminal PATH policy is invalid")
    env = parsed.get(MANAGED_ENV_KEY)
    if not isinstance(env, dict):
        raise ValueError("legacy managed terminal environment is invalid")
    if set(env) == LEGACY_MANAGED_ENV_KEYS:
        flutter_root = str(env.get("FLUTTER_ROOT") or "").strip()
        executable = str(env.get(SDK_EXECUTABLE_KEY) or "").strip()
        if not flutter_root or Path(executable) != Path(flutter_root) / "bin" / "flutter":
            raise ValueError("legacy Flutter SDK root/executable fields disagree")
        expected_env = {
            "PATH": f"{FACADE_BIN_VALUE}:{Path(flutter_root) / 'bin'}:${{env:PATH}}",
            "QWQ_WORKSPACE_FLUTTER_FACADE_BIN": FACADE_BIN_VALUE,
            "QWQ_WORKSPACE_ORIGINAL_ZDOTDIR": "${env:ZDOTDIR}",
            "ZDOTDIR": ZDOTDIR_VALUE,
            "FLUTTER_ROOT": flutter_root,
            SDK_EXECUTABLE_KEY: executable,
        }
        expected_segment = "\n" + _managed_block_from_env(expected_env) + "\n"
    else:
        sdk_binding = _stored_sdk_binding(text)
        flutter_root = Path(sdk_binding["flutterRoot"])
        expected_env = {
            "PATH": (
                f"{FACADE_BIN_VALUE}:{flutter_root / 'bin'}:${{env:PATH}}"
            ),
            "QWQ_WORKSPACE_FLUTTER_FACADE_BIN": FACADE_BIN_VALUE,
            "QWQ_WORKSPACE_ORIGINAL_ZDOTDIR": "${env:ZDOTDIR}",
            "ZDOTDIR": ZDOTDIR_VALUE,
            "FLUTTER_ROOT": str(flutter_root),
            SDK_EXECUTABLE_KEY: sdk_binding["executable"],
            SDK_VERSION_KEY: sdk_binding["flutterVersion"],
            SDK_IDENTITY_KEY: sdk_binding["commandResolutionDigest"],
        }
        expected_segment = "\n" + _managed_sdk_env_block(sdk_binding) + "\n"
    if env != expected_env or segment != expected_segment:
        raise ValueError("legacy managed settings projection is drifted")
    return segment


def _managed_block_from_env(
    terminal_env: dict[str, str],
    indent: str = "    ",
) -> str:
    env_lines = []
    items = list(terminal_env.items())
    for index, (key, value) in enumerate(items):
        suffix = "," if index < len(items) - 1 else ""
        env_lines.append(f"{indent}    {json.dumps(key)}: {json.dumps(value)}{suffix}")
    return "\n".join(
        [
            f"{indent}{BEGIN_MARKER}",
            (
                f"{indent}// 由 activate_cursor_workspace.py 管理，勿手改；"
                "回退：--deactivate 后重载窗口。"
            ),
            f'{indent}"{MANAGED_DART_KEY}": false,',
            f'{indent}"{MANAGED_ENV_KEY}": {{',
            *env_lines,
            f"{indent}}},",
            f"{indent}{END_MARKER}",
        ]
    )


def _managed_sdk_env_block(
    sdk_binding: dict[str, str],
    indent: str = "    ",
) -> str:
    flutter_root = Path(sdk_binding["flutterRoot"])
    terminal_env = {
        "PATH": f"{FACADE_BIN_VALUE}:{flutter_root / 'bin'}:${{env:PATH}}",
        "QWQ_WORKSPACE_FLUTTER_FACADE_BIN": FACADE_BIN_VALUE,
        "QWQ_WORKSPACE_ORIGINAL_ZDOTDIR": "${env:ZDOTDIR}",
        "ZDOTDIR": ZDOTDIR_VALUE,
        "FLUTTER_ROOT": str(flutter_root),
        SDK_EXECUTABLE_KEY: sdk_binding["executable"],
        SDK_VERSION_KEY: sdk_binding["flutterVersion"],
        SDK_IDENTITY_KEY: sdk_binding["commandResolutionDigest"],
    }
    env_lines = []
    items = list(terminal_env.items())
    for index, (key, value) in enumerate(items):
        suffix = "," if index < len(items) - 1 else ""
        env_lines.append(f"{indent}    {json.dumps(key)}: {json.dumps(value)}{suffix}")
    return "\n".join(
        [
            f"{indent}{BEGIN_MARKER}",
            (
                f"{indent}// 由 activate_cursor_workspace.py 管理，勿手改；"
                "回退：--deactivate 后重载窗口。"
            ),
            f"{indent}{SDK_BINDING_MARKER_PREFIX}{_sdk_binding_seal(sdk_binding)}",
            f'{indent}"{MANAGED_DART_KEY}": false,',
            f'{indent}"{MANAGED_ENV_KEY}": {{',
            *env_lines,
            f"{indent}}},",
            f"{indent}{END_MARKER}",
        ]
    )


def _remove_managed_block(text: str, *, allow_legacy: bool = False) -> str:
    if not _has_any_managed_marker(text):
        return text
    try:
        sdk_binding = _stored_sdk_binding(text)
        cocoapods_binding = _stored_cocoapods_binding(text)
        python_binding = _stored_python_binding(text)
        segment = _managed_segment(
            sdk_binding, cocoapods_binding, python_binding
        )
        if text.count(SDK_BINDING_MARKER_PREFIX) != 1:
            raise ValueError("managed SDK binding marker is malformed")
        if text.count(PYTHON_BINDING_MARKER_PREFIX) != 1:
            raise ValueError("managed Python binding marker is malformed")
        if text.count(COCOAPODS_BINDING_MARKER_PREFIX) != 1:
            raise ValueError("managed CocoaPods binding marker is malformed")
        if text.count(PROJECTION_MARKER_PREFIX) != 1:
            raise ValueError("managed projection marker is malformed")
        if text.count(segment) != 1:
            raise ValueError("managed settings projection is drifted")
    except (json.JSONDecodeError, OSError, RuntimeError, TypeError, ValueError):
        if not allow_legacy:
            raise
        try:
            segment = _exact_pre_python_identity_managed_segment(text)
        except (
            json.JSONDecodeError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            try:
                segment = _exact_pre_python_managed_segment(text)
            except (
                json.JSONDecodeError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                segment = _exact_legacy_managed_segment(text)
    return text.replace(segment, "", 1)


def _has_managed_block(text: str) -> bool:
    return BEGIN_MARKER in text and END_MARKER in text


def _has_any_managed_marker(text: str) -> bool:
    return (
        BEGIN_MARKER in text
        or END_MARKER in text
        or SDK_BINDING_MARKER_PREFIX in text
        or PYTHON_BINDING_MARKER_PREFIX in text
        or COCOAPODS_BINDING_MARKER_PREFIX in text
        or PROJECTION_MARKER_PREFIX in text
    )


def _has_exact_managed_block(text: str) -> bool:
    try:
        sdk_binding = _stored_sdk_binding(text)
        cocoapods_binding = _stored_cocoapods_binding(text)
        python_binding = _stored_python_binding(text)
        return (
            text.count(BEGIN_MARKER) == 1
            and text.count(END_MARKER) == 1
            and text.count(SDK_BINDING_MARKER_PREFIX) == 1
            and text.count(PYTHON_BINDING_MARKER_PREFIX) == 1
            and text.count(COCOAPODS_BINDING_MARKER_PREFIX) == 1
            and text.count(PROJECTION_MARKER_PREFIX) == 1
            and text.count(
                _managed_segment(sdk_binding, cocoapods_binding, python_binding)
            ) == 1
        )
    except (json.JSONDecodeError, OSError, RuntimeError, TypeError, ValueError):
        return False


_tasks_projection = _workspace_projection_io.tasks_projection
_launch_projection = _workspace_projection_io.launch_projection
_assert_projection_owned = _workspace_projection_io.assert_projection_owned
_atomic_write = _workspace_projection_io.atomic_write


def _settings_baseline_for_activation(settings_path: Path, original: str) -> str:
    begin_count = original.count(BEGIN_MARKER)
    end_count = original.count(END_MARKER)
    if begin_count != end_count or begin_count > 1:
        raise SystemExit(
            f"GATE_BLOCK: {settings_path} contains a malformed managed settings block"
        )
    try:
        baseline = _remove_managed_block(original, allow_legacy=True)
    except (json.JSONDecodeError, OSError, RuntimeError, TypeError, ValueError) as error:
        raise SystemExit(
            f"GATE_BLOCK: {settings_path} contains a drifted managed settings block"
        ) from error
    parsed = _parse_settings(baseline)
    foreign = [key for key in MANAGED_KEYS if key in parsed]
    if foreign:
        raise SystemExit(
            f"GATE_BLOCK: {settings_path} already contains foreign managed keys: "
            + ",".join(sorted(foreign))
        )
    return baseline


def activate(
    settings_path: Path,
    tasks_path: Path | None = None,
    launch_path: Path | None = None,
    environ: dict[str, str] | None = None,
) -> str:
    activation_environment = dict(os.environ if environ is None else environ)
    try:
        sdk_binding = _resolved_sdk_binding(activation_environment)
    except (_CANONICAL_FACADE.FacadeError, OSError, ValueError) as error:
        raise SystemExit(
            f"GATE_BLOCK: {WORKSPACE_FLUTTER_SDK_UNAVAILABLE_BLOCKER}; {error}"
        ) from error
    try:
        cocoapods_binding = _resolved_cocoapods_binding(activation_environment)
    except _CANONICAL_COCOAPODS.AppDependencyToolchainError as error:
        raise SystemExit(f"GATE_BLOCK: {error}") from error
    try:
        python_binding = _resolved_python_binding(activation_environment)
    except (OSError, ValueError) as error:
        raise SystemExit(
            "GATE_BLOCK: APP.LAUNCH.workspace_entrypoint_inactive; "
            f"{error}"
        ) from error
    tasks_path = tasks_path or settings_path.with_name("tasks.json")
    launch_path = launch_path or settings_path.with_name("launch.json")
    if settings_path.exists():
        original = settings_path.read_text(encoding="utf-8")
    else:
        original = "{\n}\n"

    # 三份本地投影构成一个入口。先验证全部 ownership，再写任一字节，避免
    # settings 已激活而 tasks/launch 因外来配置拒绝后的半激活状态。
    tasks_content = _tasks_projection()
    launch_content = _launch_projection()
    _assert_projection_owned(tasks_path, tasks_content, allow_managed_drift=True)
    _assert_projection_owned(launch_path, launch_content, allow_managed_drift=True)
    baseline = _settings_baseline_for_activation(settings_path, original)

    opening = baseline.index("{")
    updated = (
        baseline[: opening + 1]
        + _managed_segment(sdk_binding, cocoapods_binding, python_binding)
        + baseline[opening + 1 :]
    )
    _parse_settings(updated)
    settings_outcome = "unchanged"
    if updated != original:
        _atomic_write(settings_path, updated)
        settings_outcome = "refreshed" if _has_managed_block(original) else "activated"
    task_outcome = "unchanged"
    if (
        not tasks_path.exists()
        or tasks_path.read_text(encoding="utf-8") != tasks_content
    ):
        _atomic_write(tasks_path, tasks_content)
        task_outcome = "projected"
    launch_outcome = "unchanged"
    if (
        not launch_path.exists()
        or launch_path.read_text(encoding="utf-8") != launch_content
    ):
        _atomic_write(launch_path, launch_content)
        launch_outcome = "projected"
    if settings_outcome == task_outcome == launch_outcome == "unchanged":
        return "unchanged"
    return "activated" if settings_outcome == "activated" else "refreshed"


def deactivate(
    settings_path: Path,
    tasks_path: Path | None = None,
    launch_path: Path | None = None,
) -> str:
    tasks_path = tasks_path or settings_path.with_name("tasks.json")
    launch_path = launch_path or settings_path.with_name("launch.json")
    _assert_projection_owned(tasks_path, _tasks_projection(), deleting=True)
    _assert_projection_owned(launch_path, _launch_projection(), deleting=True)
    settings_original = ""
    settings_updated = ""
    settings_changed = False
    if settings_path.exists():
        settings_original = settings_path.read_text(encoding="utf-8")
        if _has_any_managed_marker(settings_original):
            if not _has_exact_managed_block(settings_original):
                raise SystemExit(
                    "GATE_BLOCK: refusing to delete drifted managed settings projection"
                )
            sdk_binding = _stored_sdk_binding(settings_original)
            cocoapods_binding = _stored_cocoapods_binding(settings_original)
            python_binding = _stored_python_binding(settings_original)
            settings_updated = settings_original.replace(
                _managed_segment(
                    sdk_binding, cocoapods_binding, python_binding
                ),
                "",
                1,
            )
            _parse_settings(settings_updated)
            parsed = _parse_settings(settings_updated)
            if any(key in parsed for key in MANAGED_KEYS):
                raise SystemExit(
                    "GATE_BLOCK: refusing to delete settings with foreign managed keys"
                )
            settings_changed = True
    changed = False
    for projection in (tasks_path, launch_path):
        if not projection.exists():
            continue
        projection.unlink()
        changed = True
    if not settings_path.exists():
        return "deactivated" if changed else "unchanged"
    if not settings_changed:
        return "deactivated" if changed else "unchanged"
    _atomic_write(settings_path, settings_updated)
    return "deactivated"


_load_receipt_module = _terminal_surface_state.load_receipt_module
_surface_receipt_state = _terminal_surface_state.surface_receipt_state


def status(
    settings_path: Path,
    tasks_path: Path | None = None,
    launch_path: Path | None = None,
    environ: dict[str, str] | None = None,
    *,
    surface: str | None = None,
    receipt_root: Path = RECEIPT_ROOT,
    max_age_seconds: int = 900,
    now_epoch_ms: int | None = None,
) -> dict[str, str]:
    env = dict(os.environ if environ is None else environ)
    tasks_path = tasks_path or settings_path.with_name("tasks.json")
    launch_path = launch_path or settings_path.with_name("launch.json")
    settings_text = (
        settings_path.read_text(encoding="utf-8") if settings_path.exists() else ""
    )
    settings_active = False
    stored_sdk_binding: dict[str, str] | None = None
    stored_cocoapods_binding: dict[str, str] | None = None
    stored_python_binding: dict[str, str] | None = None
    if _has_exact_managed_block(settings_text):
        try:
            stored_sdk_binding = _stored_sdk_binding(settings_text)
            stored_cocoapods_binding = _stored_cocoapods_binding(settings_text)
            stored_python_binding = _stored_python_binding(settings_text)
            baseline = settings_text.replace(
                _managed_segment(
                    stored_sdk_binding,
                    stored_cocoapods_binding,
                    stored_python_binding,
                ),
                "",
                1,
            )
            parsed = _parse_settings(baseline)
            settings_active = not any(key in parsed for key in MANAGED_KEYS)
        except (json.JSONDecodeError, OSError, RuntimeError, TypeError, ValueError):
            settings_active = False
    live_sdk_binding: dict[str, str] | None = None
    try:
        live_sdk_binding = _resolved_sdk_binding(env)
    except (_CANONICAL_FACADE.FacadeError, OSError, ValueError):
        pass
    if stored_sdk_binding is None:
        sdk_state = (
            "invalid_projection"
            if _has_any_managed_marker(settings_text)
            else "missing"
        )
    elif live_sdk_binding is None:
        sdk_state = "unavailable"
    elif live_sdk_binding != stored_sdk_binding:
        sdk_state = "drifted"
    else:
        sdk_state = "active"
    live_cocoapods_binding: dict[str, str] | None = None
    try:
        live_cocoapods_binding = _resolved_cocoapods_binding(env)
    except _CANONICAL_COCOAPODS.AppDependencyToolchainError:
        pass
    if stored_cocoapods_binding is None:
        cocoapods_state = (
            "invalid_projection"
            if _has_any_managed_marker(settings_text)
            else "missing"
        )
    elif live_cocoapods_binding is None:
        cocoapods_state = "unavailable"
    elif live_cocoapods_binding != stored_cocoapods_binding:
        cocoapods_state = "drifted"
    else:
        cocoapods_state = "active"
    live_python_binding: dict[str, str] | None = None
    try:
        live_python_binding = _resolved_python_binding(env)
    except (OSError, ValueError):
        pass
    if stored_python_binding is None:
        python_state = (
            "invalid_projection"
            if _has_any_managed_marker(settings_text)
            else "missing"
        )
    elif live_python_binding is None:
        python_state = "unavailable"
    elif live_python_binding != stored_python_binding:
        python_state = "drifted"
    else:
        python_state = "active"
    tasks_active = (
        tasks_path.exists()
        and tasks_path.read_text(encoding="utf-8") == _tasks_projection()
    )
    launch_active = (
        launch_path.exists()
        and launch_path.read_text(encoding="utf-8") == _launch_projection()
    )
    resolved = shutil.which("flutter", path=env.get("PATH", ""))
    expected = REPO_ROOT / "quwoquan_app/scripts/tools/flutter_facade/bin/flutter"
    if resolved is None:
        command_state = "missing"
    else:
        try:
            command_state = (
                "facade"
                if Path(resolved).resolve() == expected.resolve()
                else "real_sdk"
            )
        except OSError:
            command_state = "unresolved"
    projection_active = (
        settings_active
        and sdk_state == "active"
        and cocoapods_state == "active"
        and python_state == "active"
        and tasks_active
        and launch_active
    )
    projection_present = (
        _has_any_managed_marker(settings_text)
        or tasks_path.exists()
        or launch_path.exists()
    )
    projection_state = (
        "active"
        if projection_active
        else "partial"
        if projection_present
        else "inactive"
    )
    ide_state = (
        "active"
        if tasks_active and launch_active
        else "partial"
        if tasks_path.exists() or launch_path.exists()
        else "inactive"
    )
    receipt_state = _surface_receipt_state(
        surface=surface,
        sdk_binding=stored_sdk_binding if settings_active else None,
        cocoapods_binding=(
            stored_cocoapods_binding if settings_active else None
        ),
        python_binding=(
            stored_python_binding if settings_active else None
        ),
        receipt_root=receipt_root,
        max_age_seconds=max_age_seconds,
        now_epoch_ms=now_epoch_ms,
    )
    if surface is None:
        effective_state = "surface_required" if projection_active else (
            "inconsistent" if projection_present else "inactive"
        )
    elif projection_active and receipt_state == "active":
        effective_state = "active"
    elif projection_active:
        effective_state = "probe_required"
    else:
        effective_state = "inconsistent" if projection_present else "inactive"
    return {
        "projectionState": projection_state,
        "callerCommandResolution": command_state,
        "sdkResolutionState": sdk_state,
        "cocoaPodsResolutionState": cocoapods_state,
        "pythonResolutionState": python_state,
        "ideProfileState": ide_state,
        "targetSurface": surface or "none",
        "targetSurfaceReceiptState": receipt_state,
        "effectiveState": effective_state,
    }


probe_surface = _terminal_surface_state.probe_surface


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--settings",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        help="目标 settings.json（默认本仓库 .vscode/settings.json）",
    )
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--launch", type=Path)
    parser.add_argument("--surface", choices=sorted(PROFILE_SURFACES))
    parser.add_argument("--receipt-root", type=Path, default=RECEIPT_ROOT)
    parser.add_argument("--max-receipt-age-seconds", type=int, default=900)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--deactivate", action="store_true")
    group.add_argument("--status", action="store_true")
    group.add_argument("--probe-surface", action="store_true")
    args = parser.parse_args(argv)

    if args.probe_surface:
        if args.surface is None:
            parser.error("--probe-surface requires --surface")
        print(
            probe_surface(
                surface=args.surface,
                receipt_root=args.receipt_root,
            )
        )
        return 0
    if args.status:
        status_payload = status(
            args.settings,
            args.tasks,
            args.launch,
            surface=args.surface,
            receipt_root=args.receipt_root,
            max_age_seconds=args.max_receipt_age_seconds,
        )
        print(
            json.dumps(
                status_payload,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        if status_payload["effectiveState"] != "active":
            recovery = (
                "run the probe command inside the requested target terminal"
                if args.surface is not None
                else "run `make app-activate-flutter-facade` and Reload Window"
            )
            print(
                "GATE_BLOCK: APP.LAUNCH.workspace_entrypoint_inactive; " + recovery,
                file=sys.stderr,
            )
            return 2
        return 0
    if args.deactivate:
        outcome = deactivate(args.settings, args.tasks, args.launch)
    else:
        outcome = activate(args.settings, args.tasks, args.launch)
    print(outcome)
    if outcome in ("activated", "refreshed", "deactivated"):
        print(
            "[flutter-facade] 请重载编辑器窗口（Reload Window）使新终端 PATH 生效。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
