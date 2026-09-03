#!/usr/bin/env python3
"""真实 Flutter SDK 单轨解析库。

契约（specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003）：
- 受管 PATH 的字面 `flutter` 由 launcher bin 的 `flutter` dispatcher 单轨承接
  （`run` 归一化进入 canonical launcher，其余子命令 exact 透传真实 SDK）；工作区
  facade 接管、terminal carrier receipt 与 `workspace_flutter_run` provenance 已
  整体退役。
- 本模块只保留单轨 SDK 解析：`QWQ_REAL_FLUTTER` → `FLUTTER_ROOT/bin/flutter` →
  PATH 首个 flutter；解析到 launcher `flutter` dispatcher（含任何工作树拷贝，
  防 dispatcher→facade→dispatcher 递归）或任一历史 facade shim 副本即拒绝。
- 版本探针使用 allowlist env，并把 Flutter tool state 封闭进可删除输出树，
  不向源码树或用户 HOME 写字节。

本模块必须保持自足（无仓库内跨树 import），使其可与 run.sh 一起按相对位置
整体验证。单轨 SDK 解析的其他 Python 消费方经
`quwoquan_ops/cli/lib/app_dependency_toolchain.py` 委托本模块，不得复制解析逻辑。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

FACADE_PACKAGE_DIR = Path(__file__).resolve().parent
APP_ROOT = FACADE_PACKAGE_DIR.parents[2]
REPO_ROOT = APP_ROOT.parent
FLUTTER_PROBE_STATE_ROOT = REPO_ROOT / ".qwq_output/env/repo/local/flutter-facade-probe"
FLUTTER_PROBE_OS_ENV_KEYS = (
    "PATH",
    "SHELL",
    "USER",
    "LOGNAME",
    "LANG",
    "LANGUAGE",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "LC_COLLATE",
    "LC_MONETARY",
    "LC_NUMERIC",
    "LC_TIME",
    "TERM",
    "TMPDIR",
    "TMP",
    "TEMP",
    "DEVELOPER_DIR",
    "SDKROOT",
    "TOOLCHAINS",
    "SystemRoot",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
)


class FacadeError(Exception):
    """typed 解析失败：message 面向终端用户，指向合法入口。"""


def _is_facade_copy(candidate: Path) -> bool:
    """识别历史 workspace facade shim 的结构性副本（bin/flutter + flutter_facade.py）。

    shim 已退役，但废弃工作树或旧 checkout 里仍可能残留其字节；解析防御保留。
    """

    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    package_dir = resolved.parent.parent
    return (
        resolved.name == "flutter"
        and resolved.parent.name == "bin"
        and package_dir.name == "flutter_facade"
        and (package_dir / "flutter_facade.py").is_file()
    )


def _is_launcher_dispatcher_copy(candidate: Path) -> bool:
    """识别 launcher bin `flutter` dispatcher（含任何工作树拷贝）的结构性副本。

    dispatcher 位于受管 PATH 首位；解析真实 SDK 时必须按物理路径跳过它，
    否则 dispatcher 委托本模块解析会形成递归。
    """

    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    bin_dir = resolved.parent
    return (
        resolved.name == "flutter"
        and bin_dir.name == "bin"
        and bin_dir.parent.name == "launcher"
        and (bin_dir / "run.sh").is_file()
    )


def _is_workspace_shim_copy(candidate: Path) -> bool:
    return _is_facade_copy(candidate) or _is_launcher_dispatcher_copy(candidate)


def _physical_executable(candidate: Path) -> Path:
    expanded = candidate.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as error:
        raise FacadeError(
            f"Flutter SDK executable 无法解析：{expanded}: {error}"
        ) from error
    if _is_facade_copy(resolved):
        raise FacadeError("真实 Flutter SDK 解析到已退役的 workspace facade shim 副本")
    if _is_launcher_dispatcher_copy(resolved):
        raise FacadeError(
            "真实 Flutter SDK 解析到 launcher flutter dispatcher；"
            "请把真实 SDK 的 bin 目录放入 PATH 或设置 QWQ_REAL_FLUTTER"
        )
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise FacadeError(f"Flutter SDK executable 不是可执行文件：{resolved}")
    return resolved


def _ensure_private_probe_directory(path: Path) -> Path:
    """创建仅当前用户可访问且不经 symlink 跳转的探针状态目录。"""

    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        expected = Path(os.path.abspath(path))
        resolved = path.resolve(strict=True)
        if resolved != expected:
            raise FacadeError("Flutter SDK 版本探针状态目录包含 symlink")

        flags = os.O_RDONLY
        flags |= getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise FacadeError("Flutter SDK 版本探针状态路径不是目录")
            if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
                raise FacadeError("Flutter SDK 版本探针状态目录 owner 不匹配")
            os.fchmod(descriptor, 0o700)
            if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o700:
                raise FacadeError("Flutter SDK 版本探针状态目录权限不安全")
        finally:
            os.close(descriptor)
    except FacadeError:
        raise
    except OSError as error:
        reason = error.strerror or error.__class__.__name__
        raise FacadeError(
            f"Flutter SDK 版本探针状态目录初始化失败：{reason}"
        ) from error
    return resolved


def _flutter_probe_state_root(environ: dict[str, str]) -> Path:
    """选择版本探针状态根；显式 output root 必须保持字面绝对路径。"""

    if "QWQ_OUTPUT_ROOT" not in environ:
        return FLUTTER_PROBE_STATE_ROOT
    raw_output_root = environ["QWQ_OUTPUT_ROOT"]
    output_root = Path(raw_output_root)
    if (
        not raw_output_root
        or not output_root.is_absolute()
        or str(output_root) != raw_output_root
        or any(part in {"", ".", ".."} for part in output_root.parts[1:])
    ):
        raise FacadeError("QWQ_OUTPUT_ROOT 必须是非空 literal absolute path")
    return output_root / "env/repo/local/flutter-facade-probe"


def _flutter_probe_environment(environ: dict[str, str]) -> dict[str, str]:
    """构造版本探针 allowlist env，并把所有用户状态封闭进可删除输出树。"""

    state_root = _ensure_private_probe_directory(_flutter_probe_state_root(environ))
    home = _ensure_private_probe_directory(state_root / "home")
    config_home = _ensure_private_probe_directory(state_root / "config")
    cache_home = _ensure_private_probe_directory(state_root / "cache")
    probe_environment = {
        key: environ[key]
        for key in FLUTTER_PROBE_OS_ENV_KEYS
        if environ.get(key, "").strip()
    }
    probe_environment.setdefault("PATH", os.defpath)
    probe_environment.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_CACHE_HOME": str(cache_home),
            "PUB_CACHE": str(cache_home / "pub-cache"),
            "FLUTTER_SUPPRESS_ANALYTICS": "true",
        }
    )
    return probe_environment


def _flutter_version_payload(
    candidate: Path,
    environ: dict[str, str],
) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [str(candidate), "--version", "--machine"],
            env=_flutter_probe_environment(environ),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise FacadeError(f"无法读取 Flutter SDK 版本：{error}") from error
    if completed.returncode != 0:
        raise FacadeError(
            "Flutter SDK 版本探针失败："
            f"`{candidate} --version --machine` 退出码 {completed.returncode}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise FacadeError("Flutter SDK 版本探针没有返回 machine JSON") from error
    if not isinstance(payload, dict):
        raise FacadeError("Flutter SDK 版本探针返回值不是 object")
    return payload


def _validate_flutter_version(candidate: Path, environ: dict[str, str]) -> Path:
    version_file = APP_ROOT / ".flutter-version"
    try:
        expected = version_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise FacadeError(
            f"无法读取 Flutter 版本真相源 {version_file}: {error}"
        ) from error
    if not expected:
        raise FacadeError(f"Flutter 版本真相源为空：{version_file}")
    payload = _flutter_version_payload(candidate, environ)
    actual = str(payload.get("frameworkVersion") or "").strip()
    if actual != expected:
        raise FacadeError(
            f"Flutter SDK 版本漂移：工作区要求 {expected}，实际为 {actual or '<missing>'}"
        )
    return candidate


def resolved_flutter_identity(environ: dict[str, str]) -> dict[str, str]:
    """返回经钉定版本验证的 SDK 身份；digest 不泄露本机绝对路径。"""

    executable = resolve_real_flutter(environ)
    payload = _flutter_version_payload(executable, environ)
    identity = {
        "frameworkVersion": str(payload.get("frameworkVersion") or "").strip(),
        "frameworkRevision": str(payload.get("frameworkRevision") or "").strip(),
        "engineRevision": str(payload.get("engineRevision") or "").strip(),
        "dartSdkVersion": str(payload.get("dartSdkVersion") or "").strip(),
        "channel": str(payload.get("channel") or "").strip(),
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "executable": str(executable),
        "flutterVersion": identity["frameworkVersion"],
        "commandResolutionDigest": "sha256:" + hashlib.sha256(canonical).hexdigest(),
    }


def _validated_candidate(candidate: Path, environ: dict[str, str]) -> Path:
    return _validate_flutter_version(_physical_executable(candidate), environ)


def resolve_real_flutter(environ: dict[str, str]) -> Path:
    """单轨解析真实 Flutter SDK；解析到任一历史 facade shim 副本即失败。"""
    explicit = environ.get("QWQ_REAL_FLUTTER", "").strip()
    if explicit:
        return _validated_candidate(Path(explicit), environ)

    flutter_root = environ.get("FLUTTER_ROOT", "").strip()
    if flutter_root:
        candidate = Path(flutter_root) / "bin" / "flutter"
        try:
            return _validated_candidate(candidate, environ)
        except FacadeError as error:
            raise FacadeError(f"FLUTTER_ROOT 无效：{error}") from error

    for path_entry in environ.get("PATH", "").split(os.pathsep):
        entry = path_entry.strip()
        if not entry:
            continue
        candidate = Path(entry) / "flutter"
        if (
            candidate.is_file()
            and os.access(candidate, os.X_OK)
            and not _is_workspace_shim_copy(candidate)
        ):
            return _validated_candidate(candidate, environ)

    fallback = shutil.which("flutter")
    if fallback and not _is_workspace_shim_copy(Path(fallback)):
        return _validated_candidate(Path(fallback), environ)
    raise FacadeError(
        "无法解析真实 Flutter SDK：请设置 FLUTTER_ROOT，"
        "或把真实 SDK 的 bin 目录放入 PATH"
    )
