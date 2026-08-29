#!/usr/bin/env python3
"""工作区 `flutter` facade：把本 App 的字面 `flutter run` 归一化进 canonical launcher。

契约（specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003）：
- 只接管「cwd 位于本 App 项目内」的 `run` 子命令，归一化进 `run.sh` 同一执行体，
  launch provenance 固定为 `workspace_flutter_run`；其余子命令与其他 Flutter 项目全部
  原样透传真实 SDK。
- 真实 SDK 单轨解析：`QWQ_REAL_FLUTTER` → `FLUTTER_ROOT/bin/flutter` → PATH 中排除
  facade 自身后的首个 flutter；解析结果指回 facade 自身即拒绝（防递归）。
- 接管前把仓库根 realpath 物理化，废弃 recovery 工作树的物理路径继续被
  run.sh 阻断，symlink 到 canonical 主工作树的逻辑路径不被误伤。
- trust 生成、构建、安装、activation、启动与 attach 全部归 canonical launcher，
  本 facade 不生成任何配置事实。

本模块必须保持自足（无仓库内跨树 import），使其可与 run.sh 一起按相对位置
整体验证；单轨 SDK 解析的其他 Python 消费方经 `quwoquan_ops/cli/lib/
app_dependency_toolchain.py` 委托本模块，不得复制解析逻辑。
"""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

FACADE_PACKAGE_DIR = Path(__file__).resolve().parent
FACADE_EXECUTABLE = FACADE_PACKAGE_DIR / "bin" / "flutter"
APP_ROOT = FACADE_PACKAGE_DIR.parents[2]
CANONICAL_LAUNCHER = APP_ROOT / "run.sh"
LAUNCH_PROVENANCE_WORKSPACE_FLUTTER_RUN = "workspace_flutter_run"
MOBILE_TARGET_PLATFORM_PREFIXES = ("ios", "android")

USAGE_HINT = (
    "受支持入口：`./quwoquan_app/run.sh --env alpha|beta|gamma -d <device>`，"
    "或在启用工作区 facade 的终端执行 `flutter run [-d <device>]`"
    "（QWQ_ENVIRONMENT 显式选择环境，默认 Alpha）。"
)


class FacadeError(Exception):
    """typed facade 失败：message 面向终端用户，指向合法入口。"""


def _fail(message: str) -> "NoReturn":  # noqa: F821 - 注释型返回
    print(f"[flutter-facade] GATE_BLOCK: {message}", file=sys.stderr)
    print(f"[flutter-facade] {USAGE_HINT}", file=sys.stderr)
    raise SystemExit(2)


def _is_facade_copy(candidate: Path) -> bool:
    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    if resolved in (
        FACADE_EXECUTABLE.resolve(),
        Path(__file__).resolve(),
    ):
        return True
    package_dir = resolved.parent.parent
    return (
        resolved.name == "flutter"
        and resolved.parent.name == "bin"
        and package_dir.name == "flutter_facade"
        and (package_dir / "flutter_facade.py").is_file()
    )


def _physical_executable(candidate: Path) -> Path:
    expanded = candidate.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as error:
        raise FacadeError(f"Flutter SDK executable 无法解析：{expanded}: {error}") from error
    if _is_facade_copy(resolved):
        raise FacadeError("真实 Flutter SDK 解析回 workspace facade，构成递归")
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise FacadeError(f"Flutter SDK executable 不是可执行文件：{resolved}")
    return resolved


def _flutter_version_payload(candidate: Path) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [str(candidate), "--version", "--machine"],
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


def _validate_flutter_version(candidate: Path) -> Path:
    version_file = APP_ROOT / ".flutter-version"
    try:
        expected = version_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise FacadeError(f"无法读取 Flutter 版本真相源 {version_file}: {error}") from error
    if not expected:
        raise FacadeError(f"Flutter 版本真相源为空：{version_file}")
    payload = _flutter_version_payload(candidate)
    actual = str(payload.get("frameworkVersion") or "").strip()
    if actual != expected:
        raise FacadeError(
            f"Flutter SDK 版本漂移：工作区要求 {expected}，实际为 {actual or '<missing>'}"
        )
    return candidate


def resolved_flutter_identity(environ: dict[str, str]) -> dict[str, str]:
    """返回经钉定版本验证的 SDK 身份；digest 不泄露本机绝对路径。"""

    executable = resolve_real_flutter(environ)
    payload = _flutter_version_payload(executable)
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


def _validated_candidate(candidate: Path) -> Path:
    return _validate_flutter_version(_physical_executable(candidate))


def resolve_real_flutter(environ: dict[str, str]) -> Path:
    """单轨解析真实 Flutter SDK；解析到任一 workspace facade 副本即失败。"""
    explicit = environ.get("QWQ_REAL_FLUTTER", "").strip()
    if explicit:
        return _validated_candidate(Path(explicit))

    flutter_root = environ.get("FLUTTER_ROOT", "").strip()
    if flutter_root:
        candidate = Path(flutter_root) / "bin" / "flutter"
        try:
            return _validated_candidate(candidate)
        except FacadeError as error:
            raise FacadeError(f"FLUTTER_ROOT 无效：{error}") from error

    facade_bin_dir = FACADE_EXECUTABLE.parent.resolve()
    for path_entry in environ.get("PATH", "").split(os.pathsep):
        entry = path_entry.strip()
        if not entry:
            continue
        candidate = Path(entry) / "flutter"
        try:
            if candidate.parent.resolve() == facade_bin_dir:
                continue
        except OSError:
            continue
        if (
            candidate.is_file()
            and os.access(candidate, os.X_OK)
            and not _is_facade_copy(candidate)
        ):
            return _validated_candidate(candidate)

    fallback = shutil.which("flutter")
    if fallback and not _is_facade_copy(Path(fallback)):
        return _validated_candidate(Path(fallback))
    raise FacadeError(
        "无法解析真实 Flutter SDK：请设置 FLUTTER_ROOT，"
        "或把真实 SDK 的 bin 目录放入 PATH"
    )


def _first_subcommand(argv: list[str]) -> str:
    for token in argv:
        if not token.startswith("-"):
            return token
    return ""


def _enclosing_flutter_project(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pubspec.yaml").is_file():
            return candidate
    return None


def _should_take_over(argv: list[str], cwd: Path) -> bool:
    if _first_subcommand(argv) != "run":
        return False
    project_root = _enclosing_flutter_project(cwd)
    return project_root is not None and project_root == APP_ROOT


def _parse_run_arguments(argv: list[str]) -> str:
    """解析接管模式支持的参数闭集，返回显式 device id（可为空）。"""
    device_id = ""
    index = argv.index("run") + 1
    tokens = argv[index:]
    position = 0
    while position < len(tokens):
        token = tokens[position]
        if token in ("-d", "--device-id"):
            if position + 1 >= len(tokens):
                raise FacadeError(f"{token} 需要一个设备 id")
            device_id = tokens[position + 1]
            position += 2
            continue
        if token.startswith("-d=") or token.startswith("--device-id="):
            device_id = token.split("=", 1)[1]
            position += 1
            continue
        raise FacadeError(
            f"workspace_flutter_run surface 不支持参数 {token}；"
            "环境用 QWQ_ENVIRONMENT 选择，其余启动配置由 canonical launcher 拥有"
        )
    if device_id == "":
        return ""
    if not device_id.strip():
        raise FacadeError("设备 id 不能为空")
    return device_id.strip()


def _list_mobile_devices(real_flutter: Path) -> list[dict[str, object]]:
    try:
        completed = subprocess.run(
            [str(real_flutter), "devices", "--machine"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FacadeError(f"设备发现失败：{exc}") from exc
    if completed.returncode != 0:
        raise FacadeError(
            "设备发现失败："
            f"`flutter devices --machine` 退出码 {completed.returncode}"
        )
    payload = completed.stdout.strip()
    start = payload.find("[")
    if start < 0:
        raise FacadeError("设备发现输出不是 JSON 设备清单")
    try:
        devices = json.loads(payload[start:])
    except json.JSONDecodeError as exc:
        raise FacadeError(f"设备清单 JSON 解析失败：{exc}") from exc
    mobile: list[dict[str, object]] = []
    for device in devices:
        target_platform = str(device.get("targetPlatform", ""))
        if target_platform.startswith(MOBILE_TARGET_PLATFORM_PREFIXES):
            mobile.append(device)
    return mobile


def _select_device(argv: list[str], real_flutter: Path) -> str:
    explicit = _parse_run_arguments(argv)
    if explicit:
        return explicit
    devices = _list_mobile_devices(real_flutter)
    if len(devices) == 1:
        return str(devices[0]["id"])
    if not devices:
        raise FacadeError(
            "没有可用的移动设备；请先启动 Simulator/Emulator 或连接登记设备"
        )
    inventory = "\n".join(
        f"  {device.get('id')}  {device.get('name')}" for device in devices
    )
    raise FacadeError(
        "存在多台可用移动设备，必须显式 `flutter run -d <device>` 选择其一，"
        f"不按最近使用猜测：\n{inventory}"
    )


def _take_over_run(argv: list[str], real_flutter: Path) -> "NoReturn":  # noqa: F821
    device_id = _select_device(argv, real_flutter)
    launcher = CANONICAL_LAUNCHER
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise FacadeError(f"canonical launcher 缺失或不可执行：{launcher}")
    environ = dict(os.environ)
    environ["QWQ_REAL_FLUTTER"] = str(real_flutter)
    environ["QWQ_APP_LAUNCH_PROVENANCE"] = LAUNCH_PROVENANCE_WORKSPACE_FLUTTER_RUN
    # realpath 物理化：symlink 视图下也从物理仓库根启动，使 run.sh 的
    # recovery 工作树阻断只命中真正废弃的物理树。
    os.chdir(APP_ROOT)
    os.execve(str(launcher), [str(launcher), "-d", device_id], environ)
    raise AssertionError("unreachable")


def main(argv: list[str]) -> int:
    try:
        real_flutter = resolve_real_flutter(dict(os.environ))
        if _should_take_over(argv, Path.cwd()):
            _take_over_run(argv, real_flutter)
        os.execv(str(real_flutter), [str(real_flutter), *argv])
        raise AssertionError("unreachable")
    except FacadeError as error:
        _fail(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
