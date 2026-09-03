#!/usr/bin/env python3
"""工作区终端注入的受版本控制具名激活入口（纯 PATH 注入）。

契约（specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003、
specs/feature-tree/runtime/runtime-config/design.md#dec-003）：

- 只做两类可逆注入：
  1. cursor scope：`.vscode/settings.json` 的 `terminal.integrated.env.osx`
     受管块（对所有 terminal profiles 生效），内容仅为受管 PATH bin 目录前置
     与钉定的 Flutter SDK / CocoaPods / Python 身份变量；另投影受控 IDE
     Run/Debug 的 tasks/launch 文件（`workspace_ide_debug` 薄包装）。
  2. user-zsh scope（显式 opt-in，`--scope user-zsh`）：在 `~/.config/quwoquan`
     写受管投影并在用户 zshrc 维护可识别 managed source block，source 仓库内
     `user_zsh_projection.zsh`。
- 受管 PATH 前置目录固定为（按序）：`quwoquan_app/scripts/tools/launcher/bin`
  （全局 `run.sh` wrapper 与字面 `flutter` dispatcher）、钉定真实 Flutter SDK
  bin、钉定 CocoaPods bin、钉定 Python bin。字面 `flutter run` 因此进入
  canonical launcher，其余 flutter 子命令由 dispatcher exact 透传真实 SDK。
- 除 launcher bin 内的 `flutter` dispatcher 外无第二个 shim；不改 ZDOTDIR、
  不生成 terminal receipt；terminal carrier receipt 与 `workspace_flutter_run`
  provenance 已整体退役。
- 可回退：`--deactivate` 移除全部注入并逐字恢复用户文件；`--status` 如实区分
  未激活 / 已激活 / 漂移。受管块以标记行界定 ownership：activate 对块内漂移
  直接以当前解析结果修复（refreshed），块外出现受管键则拒绝写入。
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
from _common.paths import REPO_ROOT  # noqa: E402

APP_ROOT = _SCRIPTS_ROOT.parent
DEFAULT_SETTINGS_PATH = REPO_ROOT / ".vscode/settings.json"
GENERATED_APP_LAUNCH_CONTRACT_PATH = (
    REPO_ROOT
    / "quwoquan_app/tool/app_launch_contract_codegen/app_launch_contract.generated.json"
)

BEGIN_MARKER = "// qwq-flutter-facade-begin"
END_MARKER = "// qwq-flutter-facade-end"
MANAGED_DART_KEY = "dart.addSdkToTerminalPath"
MANAGED_ENV_KEY = "terminal.integrated.env.osx"
# 历史受管键：新受管块不再写入，但块外出现任一键仍视为外来 ownership。
FOREIGN_MANAGED_KEYS = (
    MANAGED_DART_KEY,
    MANAGED_ENV_KEY,
    "terminal.integrated.profiles.osx",
    "terminal.integrated.defaultProfile.osx",
    "terminal.integrated.automationProfile.osx",
    "chat.tools.terminal.terminalProfile.osx",
)
CANONICAL_LAUNCHER_BIN_PATH = APP_ROOT / "scripts/tools/launcher/bin"
CANONICAL_FLUTTER_DISPATCHER_PATH = CANONICAL_LAUNCHER_BIN_PATH / "flutter"
CANONICAL_RUN_SH_WRAPPER_PATH = CANONICAL_LAUNCHER_BIN_PATH / "run.sh"
LAUNCHER_BIN_VALUE = "${workspaceFolder}/quwoquan_app/scripts/tools/launcher/bin"

USER_ZSH_CARRIER_PATH = Path(__file__).resolve().with_name("user_zsh_projection.zsh")
USER_ZSH_CONFIG_RELATIVE_PATH = Path(".config/quwoquan/flutter-facade.zsh")
USER_ZSH_CONFIG_MARKER = "# qwq-user-zsh-projection-v1"
USER_ZSH_SOURCE_BEGIN = "# >>> qwq flutter facade user-zsh projection >>>"
USER_ZSH_SOURCE_END = "# <<< qwq flutter facade user-zsh projection <<<"
USER_ZSH_PREFIX_NEWLINE_MARKER = "# qwq-user-zsh-prefix-newline"

SDK_EXECUTABLE_KEY = "QWQ_REAL_FLUTTER"
SDK_VERSION_KEY = "QWQ_REAL_FLUTTER_VERSION"
PYTHON_EXECUTABLE_KEY = "QWQ_WORKSPACE_PYTHON"
PYTHON_VERSION_KEY = "QWQ_WORKSPACE_PYTHON_VERSION"
USER_ZSH_CARRIER_DIGEST_KEY = "QWQ_USER_ZSH_CARRIER_DIGEST"
FLUTTER_DISPATCHER_DIGEST_KEY = "QWQ_FLUTTER_DISPATCHER_DIGEST"
RUN_SH_WRAPPER_DIGEST_KEY = "QWQ_RUN_SH_WRAPPER_DIGEST"
WORKSPACE_ENTRYPOINT_DIGEST_KEYS = (
    USER_ZSH_CARRIER_DIGEST_KEY,
    FLUTTER_DISPATCHER_DIGEST_KEY,
    RUN_SH_WRAPPER_DIGEST_KEY,
)
PYTHON_MINIMUM_VERSION = (3, 10)
TRUSTED_PYTHON_PREFIXES = (Path("/opt/homebrew/bin"), Path("/usr/local/bin"))
_SHA256_IDENTITY_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


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
WORKSPACE_ENTRYPOINT_INACTIVE_BLOCKER = _canonical_launch_blocker(
    "APP.LAUNCH.workspace_entrypoint_inactive"
)
COCOAPODS_MIXED_BLOCKER = _canonical_launch_blocker("APP.DEPENDENCY.cocoapods_mixed")


class WorkspaceEntrypointError(RuntimeError):
    """canonical Mac Terminal 入口缺失、漂移或权限不可用。"""


def _literal_physical_directory(path: Path, *, label: str) -> Path:
    expected = Path(os.path.abspath(path))
    try:
        metadata = expected.lstat()
        physical = expected.resolve(strict=True)
    except OSError as error:
        raise WorkspaceEntrypointError(f"{label} is unavailable: {expected}") from error
    if (
        expected.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or physical != expected
        or not os.access(expected, os.R_OK | os.X_OK)
    ):
        raise WorkspaceEntrypointError(
            f"{label} must be the readable/executable non-symlink physical directory: "
            f"{expected}"
        )
    return physical


def _literal_physical_file(
    path: Path,
    *,
    label: str,
    executable: bool,
) -> Path:
    expected = Path(os.path.abspath(path))
    try:
        metadata = expected.lstat()
        physical = expected.resolve(strict=True)
        physical_metadata = physical.stat()
    except OSError as error:
        raise WorkspaceEntrypointError(f"{label} is unavailable: {expected}") from error
    required_access = os.R_OK | (os.X_OK if executable else 0)
    if (
        expected.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or not stat.S_ISREG(physical_metadata.st_mode)
        or physical != expected
        or not os.access(expected, required_access)
    ):
        permission = "readable/executable" if executable else "readable"
        raise WorkspaceEntrypointError(
            f"{label} must be the {permission} regular non-symlink physical file: "
            f"{expected}"
        )
    return physical


def _sha256_identity(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise WorkspaceEntrypointError(
            f"workspace entrypoint bytes are unreadable: {path}"
        ) from error


def _workspace_entrypoint_binding() -> dict[str, str]:
    """预检 canonical launcher 物理入口，并冻结三份 exact bytes identity。"""
    launcher_bin = _literal_physical_directory(
        CANONICAL_LAUNCHER_BIN_PATH,
        label="canonical launcher bin",
    )
    dispatcher = _literal_physical_file(
        CANONICAL_FLUTTER_DISPATCHER_PATH,
        label="canonical Flutter dispatcher",
        executable=True,
    )
    wrapper = _literal_physical_file(
        CANONICAL_RUN_SH_WRAPPER_PATH,
        label="canonical run.sh wrapper",
        executable=True,
    )
    carrier = _literal_physical_file(
        USER_ZSH_CARRIER_PATH,
        label="canonical user-zsh carrier",
        executable=False,
    )
    if dispatcher.parent != launcher_bin or wrapper.parent != launcher_bin:
        raise WorkspaceEntrypointError(
            "dispatcher and run.sh wrapper must reside in canonical launcher bin"
        )
    return {
        USER_ZSH_CARRIER_DIGEST_KEY: _sha256_identity(carrier),
        FLUTTER_DISPATCHER_DIGEST_KEY: _sha256_identity(dispatcher),
        RUN_SH_WRAPPER_DIGEST_KEY: _sha256_identity(wrapper),
    }


def _required_workspace_entrypoint_binding() -> dict[str, str]:
    try:
        return _workspace_entrypoint_binding()
    except WorkspaceEntrypointError as error:
        raise SystemExit(
            f"GATE_BLOCK: {WORKSPACE_ENTRYPOINT_INACTIVE_BLOCKER}; {error}"
        ) from error



def _load_sibling_module(filename: str, module_name: str):
    """按物理路径加载同目录 canonical 模块，使假工作树整体复制后仍可运行。"""
    module_path = Path(__file__).resolve().with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load canonical module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CANONICAL_FACADE = _load_sibling_module(
    "flutter_facade.py", "qwq_workspace_flutter_facade_canonical"
)
_WORKSPACE_PROJECTION_IO = _load_sibling_module(
    "cursor_workspace_projection_io.py", "qwq_workspace_projection_io_canonical"
)
_USER_ZSH_PROJECTION_IO = _load_sibling_module(
    "user_zsh_projection_io.py", "qwq_user_zsh_projection_io_canonical"
)
_WORKSPACE_ACTIVATION_CLI = _load_sibling_module(
    "workspace_activation_cli.py", "qwq_workspace_activation_cli_canonical"
)


def _load_canonical_cocoapods_module():
    # canonical toolchain 模块内部使用 quwoquan_ops.* 绝对包导入，须以包身份加载。
    repo_root = str(REPO_ROOT)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        return importlib.import_module("quwoquan_ops.cli.lib.app_dependency_toolchain")
    except ImportError as error:
        raise RuntimeError(
            "unable to load canonical App dependency toolchain from "
            f"{REPO_ROOT / 'quwoquan_ops/cli/lib/app_dependency_toolchain.py'}"
        ) from error


_CANONICAL_COCOAPODS = _load_canonical_cocoapods_module()
COCOAPODS_STATUS_KEYS = tuple(_CANONICAL_COCOAPODS.COCOAPODS_ENVIRONMENT_KEYS)

_tasks_projection = _WORKSPACE_PROJECTION_IO.tasks_projection
_launch_projection = _WORKSPACE_PROJECTION_IO.launch_projection
_assert_projection_owned = _WORKSPACE_PROJECTION_IO.assert_projection_owned
_atomic_write = _WORKSPACE_PROJECTION_IO.atomic_write
_private_atomic_write = _USER_ZSH_PROJECTION_IO.private_atomic_write


# ---------------------------------------------------------------------------
# 钉定工具链身份解析（单轨：SDK 归 flutter_facade，CocoaPods 归 ops toolchain）
# ---------------------------------------------------------------------------


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
        "executable": str(physical_executable),
        "flutterVersion": version,
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
    try:
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
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
        version_parts = tuple(int(value) for value in payload["version"])
        executable = Path(str(payload["executable"])).resolve(strict=True)
    except (json.JSONDecodeError, KeyError, OSError, TypeError, ValueError):
        return None
    if (
        len(version_parts) != 3
        or version_parts < PYTHON_MINIMUM_VERSION
        or executable != resolved
    ):
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
        candidates.append(Path(sys.executable))
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


def _resolved_bindings(
    environ: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    try:
        sdk_binding = _resolved_sdk_binding(environ)
    except (_CANONICAL_FACADE.FacadeError, OSError, ValueError) as error:
        raise SystemExit(
            f"GATE_BLOCK: {WORKSPACE_FLUTTER_SDK_UNAVAILABLE_BLOCKER}; {error}"
        ) from error
    try:
        cocoapods_binding = _resolved_cocoapods_binding(environ)
    except _CANONICAL_COCOAPODS.AppDependencyToolchainError as error:
        raise SystemExit(f"GATE_BLOCK: {error}") from error
    try:
        python_binding = _resolved_python_binding(environ)
    except (OSError, ValueError) as error:
        raise SystemExit(
            f"GATE_BLOCK: {WORKSPACE_ENTRYPOINT_INACTIVE_BLOCKER}; {error}"
        ) from error
    return sdk_binding, cocoapods_binding, python_binding


def _identity_environment_entries(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
    entrypoint_binding: dict[str, str],
) -> list[tuple[str, str]]:
    """钉定工具链身份与三份 workspace entrypoint exact bytes。"""
    return [
        (SDK_EXECUTABLE_KEY, sdk_binding["executable"]),
        (SDK_VERSION_KEY, sdk_binding["flutterVersion"]),
        *[(key, cocoapods_binding[key]) for key in COCOAPODS_STATUS_KEYS],
        (PYTHON_EXECUTABLE_KEY, python_binding["executable"]),
        (PYTHON_VERSION_KEY, python_binding["version"]),
        *[(key, entrypoint_binding[key]) for key in WORKSPACE_ENTRYPOINT_DIGEST_KEYS],
    ]


# ---------------------------------------------------------------------------
# cursor scope：.vscode/settings.json 受管块 + IDE tasks/launch 投影
# ---------------------------------------------------------------------------


def _managed_terminal_env(
    sdk_binding: dict[str, str],
    cocoapods_binding: dict[str, str],
    python_binding: dict[str, str],
    entrypoint_binding: dict[str, str],
) -> dict[str, str]:
    flutter_bin = Path(sdk_binding["executable"]).parent
    pod_bin = Path(cocoapods_binding["QWQ_COCOAPODS_EXECUTABLE"]).parent
    python_bin = Path(python_binding["executable"]).parent
    env: dict[str, str] = {
        "PATH": (
            f"{LAUNCHER_BIN_VALUE}:{flutter_bin}:{pod_bin}:{python_bin}:${{env:PATH}}"
        ),
    }
    env.update(
        _identity_environment_entries(
            sdk_binding,
            cocoapods_binding,
            python_binding,
            entrypoint_binding,
        )
    )
    return env


def _managed_block(terminal_env: dict[str, str], indent: str = "    ") -> str:
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


def _strip_line_comments(text: str) -> str:
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def _parse_settings(text: str) -> dict:
    stripped = _strip_line_comments(text)
    stripped = re.sub(r",(\s*[}\]])", r"\1", stripped).strip()
    if not stripped:
        return {}
    return json.loads(stripped)


def _marked_segment_span(text: str) -> tuple[int, int] | None:
    """受管段以标记行界定 ownership；返回含首尾换行的 [start, end) 区间。"""
    begin_count = text.count(BEGIN_MARKER)
    end_count = text.count(END_MARKER)
    if begin_count == 0 and end_count == 0:
        return None
    if begin_count != 1 or end_count != 1:
        raise ValueError("managed settings markers are malformed")
    begin = text.index(BEGIN_MARKER)
    end = text.index(END_MARKER, begin) + len(END_MARKER)
    if "\n" not in text[:begin] or not text[end:].startswith("\n"):
        raise ValueError("managed settings segment boundaries are drifted")
    return text.rfind("\n", 0, begin), end + 1


def _settings_baseline(settings_path: Path, original: str) -> str:
    """移除受管段并验证块外无受管键；漂移的块内容不阻断（由新内容修复）。"""
    try:
        span = _marked_segment_span(original)
    except ValueError as error:
        raise SystemExit(
            f"GATE_BLOCK: {settings_path} contains a malformed managed settings block: "
            f"{error}"
        ) from error
    baseline = original if span is None else original[: span[0]] + original[span[1] :]
    try:
        parsed = _parse_settings(baseline)
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"GATE_BLOCK: {settings_path} is not parseable outside the managed block"
        ) from error
    foreign = [key for key in FOREIGN_MANAGED_KEYS if key in parsed]
    if foreign:
        raise SystemExit(
            f"GATE_BLOCK: {settings_path} already contains foreign managed keys: "
            + ",".join(sorted(foreign))
        )
    return baseline


def _settings_with_managed_block(
    settings_path: Path, original: str, terminal_env: dict[str, str]
) -> str:
    baseline = _settings_baseline(settings_path, original)
    if "{" not in baseline:
        raise SystemExit(
            f"GATE_BLOCK: {settings_path} is not a JSON object settings file"
        )
    opening = baseline.index("{")
    updated = (
        baseline[: opening + 1]
        + "\n"
        + _managed_block(terminal_env)
        + "\n"
        + baseline[opening + 1 :]
    )
    _parse_settings(updated)
    return updated


def activate(
    settings_path: Path,
    tasks_path: Path | None = None,
    launch_path: Path | None = None,
    environ: dict[str, str] | None = None,
) -> str:
    activation_environment = dict(os.environ if environ is None else environ)
    entrypoint_binding = _required_workspace_entrypoint_binding()
    sdk_binding, cocoapods_binding, python_binding = _resolved_bindings(
        activation_environment
    )
    tasks_path = tasks_path or settings_path.with_name("tasks.json")
    launch_path = launch_path or settings_path.with_name("launch.json")
    original = (
        settings_path.read_text(encoding="utf-8")
        if settings_path.exists()
        else "{\n}\n"
    )

    # 三份本地投影构成一个入口。先验证全部 ownership，再写任一字节，避免
    # settings 已激活而 tasks/launch 因外来配置拒绝后的半激活状态。
    tasks_content = _tasks_projection()
    launch_content = _launch_projection()
    _assert_projection_owned(tasks_path, tasks_content, allow_managed_drift=True)
    _assert_projection_owned(launch_path, launch_content, allow_managed_drift=True)
    updated = _settings_with_managed_block(
        settings_path,
        original,
        _managed_terminal_env(
            sdk_binding,
            cocoapods_binding,
            python_binding,
            entrypoint_binding,
        ),
    )
    settings_outcome = "unchanged"
    if updated != original:
        _atomic_write(settings_path, updated)
        settings_outcome = "refreshed" if BEGIN_MARKER in original else "activated"
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
    settings_changed = False
    settings_updated = ""
    if settings_path.exists():
        original = settings_path.read_text(encoding="utf-8")
        if BEGIN_MARKER in original or END_MARKER in original:
            settings_updated = _settings_baseline(settings_path, original)
            settings_changed = settings_updated != original
    changed = False
    for projection in (tasks_path, launch_path):
        if not projection.exists():
            continue
        projection.unlink()
        changed = True
    if settings_changed:
        _atomic_write(settings_path, settings_updated)
        changed = True
    return "deactivated" if changed else "unchanged"


def status(
    settings_path: Path,
    tasks_path: Path | None = None,
    launch_path: Path | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, str]:
    env = dict(os.environ if environ is None else environ)
    tasks_path = tasks_path or settings_path.with_name("tasks.json")
    launch_path = launch_path or settings_path.with_name("launch.json")
    settings_text = (
        settings_path.read_text(encoding="utf-8") if settings_path.exists() else ""
    )
    markers_present = BEGIN_MARKER in settings_text or END_MARKER in settings_text

    live_env: dict[str, str] | None = None
    resolution_error = ""
    try:
        live_env = _managed_terminal_env(
            _resolved_sdk_binding(env),
            _resolved_cocoapods_binding(env),
            _resolved_python_binding(env),
            _workspace_entrypoint_binding(),
        )
    except (
        _CANONICAL_FACADE.FacadeError,
        _CANONICAL_COCOAPODS.AppDependencyToolchainError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        WorkspaceEntrypointError,
    ) as error:
        resolution_error = str(error)

    if not markers_present:
        settings_state = "missing"
    elif live_env is None:
        settings_state = "unverifiable"
    else:
        try:
            settings_state = (
                "active"
                if _settings_with_managed_block(settings_path, settings_text, live_env)
                == settings_text
                else "drifted"
            )
        except (SystemExit, ValueError):
            settings_state = "drifted"

    stored_env: dict[str, str] | None = None
    try:
        parsed = _parse_settings(settings_text) if settings_text else {}
        candidate_env = parsed.get(MANAGED_ENV_KEY)
        if isinstance(candidate_env, dict):
            stored_env = {str(key): str(value) for key, value in candidate_env.items()}
    except json.JSONDecodeError:
        stored_env = None

    def _binding_state(keys: tuple[str, ...]) -> str:
        if stored_env is None or any(not stored_env.get(key) for key in keys):
            return "invalid_projection" if markers_present else "missing"
        if live_env is None:
            return "unavailable"
        if any(stored_env.get(key) != live_env.get(key) for key in keys):
            return "drifted"
        return "active"

    sdk_state = _binding_state((SDK_EXECUTABLE_KEY, SDK_VERSION_KEY))
    cocoapods_state = _binding_state(COCOAPODS_STATUS_KEYS)
    python_state = _binding_state((PYTHON_EXECUTABLE_KEY, PYTHON_VERSION_KEY))
    entrypoint_state = _binding_state(WORKSPACE_ENTRYPOINT_DIGEST_KEYS)

    tasks_active = (
        tasks_path.exists()
        and tasks_path.read_text(encoding="utf-8") == _tasks_projection()
    )
    launch_active = (
        launch_path.exists()
        and launch_path.read_text(encoding="utf-8") == _launch_projection()
    )
    ide_state = (
        "active"
        if tasks_active and launch_active
        else "partial"
        if tasks_path.exists() or launch_path.exists()
        else "inactive"
    )

    present = markers_present or tasks_path.exists() or launch_path.exists()
    if settings_state == "active" and ide_state == "active":
        projection_state = "active"
    elif not present:
        projection_state = "inactive"
    else:
        projection_state = "drifted"
    payload = {
        "projectionState": projection_state,
        "settingsState": settings_state,
        "sdkResolutionState": sdk_state,
        "cocoaPodsResolutionState": cocoapods_state,
        "pythonResolutionState": python_state,
        "workspaceEntrypointState": entrypoint_state,
        "workspaceEntrypointDigests": (
            {
                key: live_env[key]
                for key in WORKSPACE_ENTRYPOINT_DIGEST_KEYS
                if live_env and live_env.get(key)
            }
        ),
        "ideProfileState": ide_state,
    }
    if resolution_error:
        payload["resolutionError"] = resolution_error
    return payload


_USER_ZSH_PROJECTION_MODULE = _load_sibling_module(
    "user_zsh_projection.py",
    "qwq_user_zsh_projection",
)
_USER_ZSH_PROJECTION = _USER_ZSH_PROJECTION_MODULE.UserZshProjection(
    carrier_path=USER_ZSH_CARRIER_PATH,
    identity_environment_entries=_identity_environment_entries,
    required_workspace_entrypoint_binding=_required_workspace_entrypoint_binding,
    workspace_entrypoint_binding=_workspace_entrypoint_binding,
    resolved_bindings=_resolved_bindings,
    resolved_sdk_binding=_resolved_sdk_binding,
    resolved_cocoapods_binding=_resolved_cocoapods_binding,
    resolved_python_binding=_resolved_python_binding,
    private_atomic_write=_private_atomic_write,
    workspace_entrypoint_digest_keys=WORKSPACE_ENTRYPOINT_DIGEST_KEYS,
    resolution_error_types=(
        _CANONICAL_FACADE.FacadeError,
        _CANONICAL_COCOAPODS.AppDependencyToolchainError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        WorkspaceEntrypointError,
    ),
)
_literal_existing_home = _USER_ZSH_PROJECTION.literal_existing_home
_user_zsh_paths = _USER_ZSH_PROJECTION.user_zsh_paths
_generated_user_zsh_projection = _USER_ZSH_PROJECTION.generated_user_zsh_projection
_user_zsh_projection_is_recognized = _USER_ZSH_PROJECTION.user_zsh_projection_is_recognized
_user_zsh_block = _USER_ZSH_PROJECTION.user_zsh_block
_strip_user_zsh_block = _USER_ZSH_PROJECTION.strip_user_zsh_block
_with_user_zsh_block = _USER_ZSH_PROJECTION.with_user_zsh_block
activate_user_zsh = _USER_ZSH_PROJECTION.activate_user_zsh
deactivate_user_zsh = _USER_ZSH_PROJECTION.deactivate_user_zsh
user_zsh_status = _USER_ZSH_PROJECTION.user_zsh_status

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


_merge_outcomes = _WORKSPACE_ACTIVATION_CLI.merge_outcomes


def main(argv: list[str]) -> int:
    return _WORKSPACE_ACTIVATION_CLI.run_cli(
        argv,
        description=__doc__,
        default_settings_path=DEFAULT_SETTINGS_PATH,
        workspace_entrypoint_inactive_blocker=WORKSPACE_ENTRYPOINT_INACTIVE_BLOCKER,
        cursor_activate=activate,
        cursor_deactivate=deactivate,
        cursor_status=status,
        user_zsh_activate=activate_user_zsh,
        user_zsh_deactivate=deactivate_user_zsh,
        user_zsh_status=user_zsh_status,
        user_zsh_paths=_user_zsh_paths,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SystemExit as error:
        # typed GATE_BLOCK 以字符串携带；CLI 契约统一用退出码 2 表示阻断。
        if isinstance(error.code, str):
            print(error.code, file=sys.stderr)
            raise SystemExit(2) from None
        raise
