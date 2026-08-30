# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-004
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
#
# 层：local_contract。字面 `flutter run` 的工作区 facade 命令契约：
# 透传/接管判定、真实 SDK 单轨解析（QWQ_REAL_FLUTTER）、防递归、
# 设备选择分层、symlink 工作区 realpath 物理化，以及未经 facade/canonical
# handoff 的原始 Xcode backend fail-closed 时指向合法入口。
# 断言面为执行行为、退出码与捕获产物，不做脚本源码文本断言。

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = APP_DIR.parent
FACADE_DIR = APP_DIR / "scripts/tools/flutter_facade"
FACADE_BIN = FACADE_DIR / "bin"
FACADE_EXECUTABLE = FACADE_BIN / "flutter"
BACKEND_PREPARE_SCRIPT = APP_DIR / "scripts/ios/build_prepare_dart_defines.sh"
APP_ARTIFACT_MANIFEST = (
    REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml"
)
CANONICAL_LAUNCHER_SCRIPT = APP_DIR / "run.sh"


def _load_facade_module():
    spec = importlib.util.spec_from_file_location(
        "flutter_facade_under_test", FACADE_DIR / "flutter_facade.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUBPROCESS_TIMEOUT_SECONDS = 30


def _write_executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _write_fake_real_flutter(
    root: Path,
    *,
    capture_path: Path,
    devices: list[dict[str, object]] | None = None,
    exit_code: int = 0,
) -> Path:
    devices_json = json.dumps(devices if devices is not None else [])
    return _write_executable(
        root / "fake-sdk/bin/flutter",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$*" == "--version --machine" ]]; then\n'
        '  printf \'%s\' \'{"frameworkVersion":"3.47.0","frameworkRevision":"fixture-revision"}\'\n'
        "  exit 0\n"
        "fi\n"
        f"printf '%s\\n' \"$*\" >> {json.dumps(str(capture_path))}\n"
        'if [[ "${1:-}" == "devices" ]]; then\n'
        f"  printf '%s' {json.dumps(devices_json)}\n"
        "  exit 0\n"
        "fi\n"
        f"exit {exit_code}\n",
    )


def _write_probe_environment_spy(
    root: Path,
    *,
    capture_path: Path,
) -> Path:
    """模拟 Flutter tool state 写入，并捕获版本探针实际收到的环境。"""
    return _write_executable(
        root / "probe-spy-sdk/bin/flutter",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$*" == "--version --machine" ]]; then\n'
        f"  {json.dumps(sys.executable)} - {json.dumps(str(capture_path))} <<'PY'\n"
        "import json\n"
        "import os\n"
        "import stat\n"
        "import sys\n"
        "from pathlib import Path\n"
        "home = os.environ.get('HOME')\n"
        "config_home = os.environ.get('XDG_CONFIG_HOME')\n"
        "cache_home = os.environ.get('XDG_CACHE_HOME')\n"
        "state_root = Path(config_home) if config_home else "
        "Path(home or '.') / '.config'\n"
        "tool_state = state_root / 'flutter' / 'tool_state'\n"
        "tool_state.parent.mkdir(parents=True, exist_ok=True)\n"
        "tool_state.write_text('{}', encoding='utf-8')\n"
        "payload = {\n"
        "    'cwd': os.getcwd(),\n"
        "    'HOME': home,\n"
        "    'XDG_CONFIG_HOME': config_home,\n"
        "    'XDG_CACHE_HOME': cache_home,\n"
        "    'PATH': os.environ.get('PATH'),\n"
        "    'outputRoot': os.environ.get('QWQ_OUTPUT_ROOT'),\n"
        "    'secret': os.environ.get('QWQ_PROBE_SECRET_DO_NOT_LEAK'),\n"
        "    'modes': {\n"
        "        key: stat.S_IMODE(Path(value).stat().st_mode)\n"
        "        for key, value in {\n"
        "            'HOME': home,\n"
        "            'XDG_CONFIG_HOME': config_home,\n"
        "            'XDG_CACHE_HOME': cache_home,\n"
        "        }.items()\n"
        "        if value\n"
        "    },\n"
        "}\n"
        "Path(sys.argv[1]).write_text(json.dumps(payload), encoding='utf-8')\n"
        "print(json.dumps({\n"
        "    'frameworkVersion': '3.47.0',\n"
        "    'frameworkRevision': 'fixture-revision',\n"
        "}))\n"
        "PY\n"
        "  exit 0\n"
        "fi\n"
        "exit 64\n",
    )


def _install_fake_workspace(root: Path) -> dict[str, Path]:
    """把真实 facade 复制进假 App 树，run.sh 替换为捕获替身。"""
    app_root = root / "quwoquan_app"
    (app_root).mkdir(parents=True)
    (app_root / "pubspec.yaml").write_text("name: quwoquan_app\n", encoding="utf-8")
    (app_root / ".flutter-version").write_text("3.47.0\n", encoding="utf-8")
    capture = root / "launcher-capture.json"
    _write_executable(
        app_root / "run.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "python3 - \"$@\" <<'PY'\n"
        "import json, os, sys\n"
        "payload = {\n"
        "    'argv': sys.argv[1:],\n"
        "    'pwd': os.getcwd(),\n"
        "    'launchProvenance': os.environ.get('QWQ_APP_LAUNCH_PROVENANCE', ''),\n"
        "    'realFlutter': os.environ.get('QWQ_REAL_FLUTTER', ''),\n"
        "    'environment': os.environ.get('QWQ_ENVIRONMENT', ''),\n"
        "}\n"
        f"with open({json.dumps(str(capture))}, 'w', encoding='utf-8') as fh:\n"
        "    json.dump(payload, fh)\n"
        "PY\n",
    )
    fake_facade_dir = app_root / "scripts/tools/flutter_facade"
    shutil.copytree(FACADE_DIR, fake_facade_dir)
    return {
        "app_root": app_root,
        "capture": capture,
        "facade": fake_facade_dir / "bin/flutter",
    }


def _clean_environment(**overrides: str) -> dict[str, str]:
    environment = dict(os.environ)
    for key in (
        "QWQ_REAL_FLUTTER",
        "QWQ_APP_LAUNCH_PROVENANCE",
        "QWQ_ENVIRONMENT",
        "QWQ_OUTPUT_ROOT",
        "FLUTTER_ROOT",
    ):
        environment.pop(key, None)
    environment.update(overrides)
    return environment


def _run_facade(
    facade: Path,
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(facade), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )


MOBILE_DEVICE_A = {
    "id": "SIM-AAAA",
    "name": "iPhone 15",
    "targetPlatform": "ios",
    "emulator": True,
}
MOBILE_DEVICE_B = {
    "id": "EMU-BBBB",
    "name": "Pixel 8",
    "targetPlatform": "android-arm64",
    "emulator": True,
}
DESKTOP_DEVICE = {
    "id": "macos",
    "name": "macOS",
    "targetPlatform": "darwin",
    "emulator": False,
}


class FlutterFacadeCommandContractTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_facade_path_directory_contains_single_executable(self) -> None:
        self.assertTrue(
            FACADE_EXECUTABLE.is_file(),
            "工作区 facade 可执行文件缺失：scripts/tools/flutter_facade/bin/flutter",
        )
        self.assertTrue(os.access(FACADE_EXECUTABLE, os.X_OK))
        occupants = sorted(item.name for item in FACADE_BIN.iterdir())
        self.assertEqual(
            occupants,
            ["flutter"],
            "PATH 专用目录只允许 flutter 一个占位，不得把其他脚本暴露进 PATH",
        )

    def test_facade_passes_through_non_run_subcommands(self) -> None:
        capture = self.root / "sdk-capture.log"
        real_flutter = _write_fake_real_flutter(self.root, capture_path=capture)
        other_project = self.root / "other_project"
        other_project.mkdir()
        (other_project / "pubspec.yaml").write_text(
            "name: other_project\n", encoding="utf-8"
        )
        result = _run_facade(
            FACADE_EXECUTABLE,
            ["pub", "get", "--offline"],
            cwd=other_project,
            env=_clean_environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            capture.read_text(encoding="utf-8").strip(),
            "pub get --offline",
            "非 run 子命令必须把原始 argv 原样透传真实 SDK",
        )

    def test_version_probe_uses_explicit_output_root_outside_workspace(
        self,
    ) -> None:
        workspace = _install_fake_workspace(self.root)
        external_temporary = tempfile.TemporaryDirectory()
        self.addCleanup(external_temporary.cleanup)
        explicit_output_root = (
            Path(external_temporary.name) / "canonical-output"
        ).resolve()
        capture = self.root / "explicit-output-probe-environment.json"
        real_flutter = _write_probe_environment_spy(
            self.root,
            capture_path=capture,
        )
        environment = _clean_environment(
            QWQ_REAL_FLUTTER=str(real_flutter),
            QWQ_OUTPUT_ROOT=str(explicit_output_root),
            PATH="/usr/bin:/bin",
            QWQ_PROBE_SECRET_DO_NOT_LEAK="probe-secret-sentinel",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(
                    workspace["app_root"]
                    / "scripts/tools/flutter_facade/resolve_real_flutter.py"
                ),
                "--format",
                "json",
            ],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        managed_root = (
            explicit_output_root / "env/repo/local/flutter-facade-probe"
        )
        probe_environment = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(
            Path(probe_environment["HOME"]),
            managed_root / "home",
        )
        self.assertEqual(
            Path(probe_environment["XDG_CONFIG_HOME"]),
            managed_root / "config",
        )
        self.assertEqual(
            Path(probe_environment["XDG_CACHE_HOME"]),
            managed_root / "cache",
        )
        self.assertFalse(
            (self.root / ".qwq_output").exists(),
            "显式外部 output root 不得在 source projection 创建 derived output",
        )
        self.assertIsNone(
            probe_environment["outputRoot"],
            "QWQ_OUTPUT_ROOT 只定位 facade probe，不得传给 Flutter child",
        )
        self.assertIsNone(probe_environment["secret"])
        terminal_output = result.stdout + result.stderr
        self.assertNotIn("probe-secret-sentinel", terminal_output)
        self.assertNotIn(str(explicit_output_root), terminal_output)

    def test_version_probe_rejects_relative_output_root_without_path_disclosure(
        self,
    ) -> None:
        workspace = _install_fake_workspace(self.root)
        capture = self.root / "relative-output-probe-environment.json"
        real_flutter = _write_probe_environment_spy(
            self.root,
            capture_path=capture,
        )
        sensitive_relative_path = "relative-probe-secret-sentinel/output"
        environment = _clean_environment(
            QWQ_REAL_FLUTTER=str(real_flutter),
            QWQ_OUTPUT_ROOT=sensitive_relative_path,
            PATH="/usr/bin:/bin",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(
                    workspace["app_root"]
                    / "scripts/tools/flutter_facade/resolve_real_flutter.py"
                ),
                "--format",
                "json",
            ],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("GATE_BLOCK", result.stderr)
        self.assertIn("QWQ_OUTPUT_ROOT", result.stderr)
        self.assertFalse(capture.exists(), "非法 output root 必须在启动 Flutter 前阻断")
        self.assertFalse((self.root / ".qwq_output").exists())
        self.assertNotIn(sensitive_relative_path, result.stdout + result.stderr)

    def test_version_probe_seals_home_xdg_and_arbitrary_secret_environment(
        self,
    ) -> None:
        workspace = _install_fake_workspace(self.root)
        capture = self.root / "probe-environment.json"
        real_flutter = _write_probe_environment_spy(
            self.root,
            capture_path=capture,
        )
        environment = _clean_environment(
            QWQ_REAL_FLUTTER=str(real_flutter),
            PATH="/usr/bin:/bin",
            QWQ_PROBE_SECRET_DO_NOT_LEAK="probe-secret-sentinel",
        )
        for key in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            environment.pop(key, None)

        result = subprocess.run(
            [
                sys.executable,
                str(
                    workspace["app_root"]
                    / "scripts/tools/flutter_facade/resolve_real_flutter.py"
                ),
                "--format",
                "json",
            ],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(
            (self.root / ".config").exists(),
            "HOME/XDG 缺席时版本探针不得在 repo root 写 .config/flutter/tool_state",
        )
        probe_environment = json.loads(capture.read_text(encoding="utf-8"))
        managed_root = (
            self.root / ".qwq_output/env/repo/local/flutter-facade-probe"
        ).resolve()
        for key in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            value = Path(probe_environment[key]).resolve()
            self.assertTrue(value.is_relative_to(managed_root), (key, value))
            self.assertEqual(probe_environment["modes"][key], 0o700)
        self.assertEqual(probe_environment["PATH"], "/usr/bin:/bin")
        self.assertIsNone(
            probe_environment["secret"],
            "版本探针必须采用 allowlist env，不得继承任意 secret",
        )
        terminal_output = result.stdout + result.stderr
        self.assertNotIn("probe-secret-sentinel", terminal_output)
        self.assertNotIn(str(managed_root), terminal_output)

    def test_facade_passthrough_propagates_real_sdk_exit_code(self) -> None:
        capture = self.root / "sdk-capture.log"
        real_flutter = _write_fake_real_flutter(
            self.root, capture_path=capture, exit_code=42
        )
        result = _run_facade(
            FACADE_EXECUTABLE,
            ["--version"],
            cwd=self.root,
            env=_clean_environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertEqual(result.returncode, 42)

    def test_facade_passes_through_run_outside_this_app(self) -> None:
        capture = self.root / "sdk-capture.log"
        real_flutter = _write_fake_real_flutter(self.root, capture_path=capture)
        other_project = self.root / "other_project"
        other_project.mkdir()
        (other_project / "pubspec.yaml").write_text(
            "name: other_project\n", encoding="utf-8"
        )
        result = _run_facade(
            FACADE_EXECUTABLE,
            ["run", "-d", "SIM-AAAA"],
            cwd=other_project,
            env=_clean_environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            capture.read_text(encoding="utf-8").strip(),
            "run -d SIM-AAAA",
            "其他 Flutter 项目的 run 必须透传，不得被本仓库 facade 接管",
        )

    def test_facade_takes_over_run_inside_this_app_with_explicit_device(self) -> None:
        workspace = _install_fake_workspace(self.root)
        capture = self.root / "sdk-capture.log"
        real_flutter = _write_fake_real_flutter(self.root, capture_path=capture)
        result = _run_facade(
            workspace["facade"],
            ["run", "-d", "SIM-AAAA"],
            cwd=workspace["app_root"],
            env=_clean_environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(workspace["capture"].read_text(encoding="utf-8"))
        self.assertIn("-d", payload["argv"])
        self.assertIn("SIM-AAAA", payload["argv"])
        self.assertEqual(payload["launchProvenance"], "workspace_flutter_run")
        self.assertEqual(payload["realFlutter"], str(real_flutter))

    def test_facade_auto_selects_single_available_mobile_device(self) -> None:
        workspace = _install_fake_workspace(self.root)
        capture = self.root / "sdk-capture.log"
        real_flutter = _write_fake_real_flutter(
            self.root,
            capture_path=capture,
            devices=[MOBILE_DEVICE_A, DESKTOP_DEVICE],
        )
        result = _run_facade(
            workspace["facade"],
            ["run"],
            cwd=workspace["app_root"],
            env=_clean_environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(workspace["capture"].read_text(encoding="utf-8"))
        self.assertIn("SIM-AAAA", payload["argv"])

    def test_facade_requires_device_choice_with_multiple_mobile_devices(self) -> None:
        workspace = _install_fake_workspace(self.root)
        capture = self.root / "sdk-capture.log"
        real_flutter = _write_fake_real_flutter(
            self.root,
            capture_path=capture,
            devices=[MOBILE_DEVICE_A, MOBILE_DEVICE_B],
        )
        result = _run_facade(
            workspace["facade"],
            ["run"],
            cwd=workspace["app_root"],
            env=_clean_environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SIM-AAAA", result.stderr)
        self.assertIn("EMU-BBBB", result.stderr)
        self.assertFalse(
            workspace["capture"].exists(),
            "多设备且未显式 -d 时不得调用 canonical launcher",
        )

    def test_facade_rejects_recursive_real_flutter(self) -> None:
        workspace = _install_fake_workspace(self.root)
        result = _run_facade(
            workspace["facade"],
            ["--version"],
            cwd=workspace["app_root"],
            env=_clean_environment(QWQ_REAL_FLUTTER=str(workspace["facade"])),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(workspace["capture"].exists())

    def test_facade_rejects_unsupported_run_arguments(self) -> None:
        workspace = _install_fake_workspace(self.root)
        capture = self.root / "sdk-capture.log"
        real_flutter = _write_fake_real_flutter(self.root, capture_path=capture)
        result = _run_facade(
            workspace["facade"],
            ["run", "--dart-define", "APP_RUNTIME_ENV=beta"],
            cwd=workspace["app_root"],
            env=_clean_environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            workspace["capture"].exists(),
            "不支持的 run 参数必须拒绝，不得静默丢弃后继续启动",
        )

    def test_facade_physicalizes_symlinked_workspace_before_launcher(self) -> None:
        physical_root = self.root / "physical"
        physical_root.mkdir()
        workspace = _install_fake_workspace(physical_root)
        linked_root = self.root / "linked"
        linked_root.symlink_to(physical_root)
        linked_app = linked_root / "quwoquan_app"
        capture = self.root / "sdk-capture.log"
        real_flutter = _write_fake_real_flutter(self.root, capture_path=capture)
        result = _run_facade(
            linked_app / "scripts/tools/flutter_facade/bin/flutter",
            ["run", "-d", "SIM-AAAA"],
            cwd=linked_app,
            env=_clean_environment(QWQ_REAL_FLUTTER=str(real_flutter)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(workspace["capture"].read_text(encoding="utf-8"))
        self.assertEqual(
            Path(payload["pwd"]),
            workspace["app_root"].resolve(),
            "facade 必须在调用 canonical launcher 前把 symlink 工作区物理化",
        )

    def test_launch_surface_values_bind_to_metadata_closed_enum(self) -> None:
        import yaml

        manifest = yaml.safe_load(APP_ARTIFACT_MANIFEST.read_text(encoding="utf-8"))
        provenances = set(manifest["launch_provenances"])
        module = _load_facade_module()
        self.assertIn(
            module.LAUNCH_PROVENANCE_WORKSPACE_FLUTTER_RUN,
            provenances,
            "facade 的 launch surface 必须属于 metadata launch_provenances 闭集",
        )

    def test_canonical_launcher_rejects_launch_surface_outside_closed_enum(
        self,
    ) -> None:
        environment = dict(os.environ)
        environment["QWQ_APP_LAUNCH_PROVENANCE"] = "icon_cold_launch_forged"
        result = subprocess.run(
            [str(CANONICAL_LAUNCHER_SCRIPT), "-d", "SIM-AAAA"],
            cwd=APP_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("APP.LAUNCH.launch_surface_unsupported", result.stderr)

    def test_workspace_activation_is_idempotent_and_reversible(self) -> None:
        activate_script = FACADE_DIR / "activate_cursor_workspace.py"
        settings = self.root / ".vscode/settings.json"
        settings.parent.mkdir(parents=True)
        original = (
            "{\n"
            "    // 用户已有注释必须保留\n"
            '    "dart.analysisExcludedFolders": ["quwoquan_app/vendor"]\n'
            "}\n"
        )
        settings.write_text(original, encoding="utf-8")

        sdk_capture = self.root / "activation-sdk.log"
        real_flutter = _write_fake_real_flutter(
            self.root / "activation", capture_path=sdk_capture
        )
        fake_pod = self.root / "activation-pod/bin/pod"
        fake_pod.parent.mkdir(parents=True)
        fake_pod.write_text(
            "#!/bin/sh\n"
            'SELF="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"\n'
            'if [ "$1" = "--version" ]; then\n'
            "  printf '%s\\n' '1.16.2'\n"
            "  exit 0\n"
            "fi\n"
            'if [ "$1" = "env" ]; then\n'
            "  printf '### Stack\\nCocoaPods : 1.16.2\\nRuby : 3.3.0\\n"
            "RubyGems : 3.5.0\\n### Plugins\\n"
            "cocoapods-deintegrate : 1.0.5\\nExecutable Path: %s\\n' "
            '"$SELF"\n'
            "  exit 0\n"
            "fi\n"
            "exit 64\n",
            encoding="utf-8",
        )
        fake_pod.chmod(0o755)
        activation_environment = _clean_environment(
            QWQ_REAL_FLUTTER=str(real_flutter),
            PATH=f"{fake_pod.parent}:/usr/bin:/bin",
        )

        def run_activation(
            *args: str,
            environment: dict[str, str] | None = None,
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    str(activate_script),
                    "--settings",
                    str(settings),
                    *args,
                ],
                env=environment or activation_environment,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
                check=False,
            )

        first = run_activation()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout.strip().splitlines()[0], "activated")
        merged = settings.read_text(encoding="utf-8")
        self.assertIn("用户已有注释必须保留", merged)
        self.assertIn("dart.analysisExcludedFolders", merged)
        self.assertIn(
            "flutter_facade/bin",
            merged,
            "激活必须 prepend facade bin",
        )
        self.assertIn(
            "${env:PATH}",
            merged,
            "激活必须保留 ${env:PATH}，不得替换全局 PATH",
        )
        self.assertIn('"FLUTTER_ROOT"', merged)
        self.assertIn('"QWQ_REAL_FLUTTER_VERSION": "3.47.0"', merged)
        self.assertIn('"QWQ_REAL_FLUTTER_COMMAND_RESOLUTION_DIGEST": "sha256:', merged)

        second = run_activation()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout.strip(), "unchanged")
        self.assertEqual(settings.read_text(encoding="utf-8"), merged)

        rollback = run_activation(
            "--deactivate",
            environment=_clean_environment(PATH="/usr/bin:/bin"),
        )
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertEqual(rollback.stdout.strip().splitlines()[0], "deactivated")
        self.assertEqual(
            settings.read_text(encoding="utf-8"),
            original,
            "回退必须逐字恢复用户原有 settings 内容",
        )

    def test_workspace_activation_refuses_foreign_terminal_env_key(self) -> None:
        activate_script = FACADE_DIR / "activate_cursor_workspace.py"
        settings = self.root / "settings.json"
        sdk_capture = self.root / "foreign-key-sdk.log"
        real_flutter = _write_fake_real_flutter(
            self.root / "foreign-key", capture_path=sdk_capture
        )
        settings.write_text(
            "{\n"
            '    "terminal.integrated.env.osx": {"PATH": "/custom/bin:${env:PATH}"}\n'
            "}\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(activate_script), "--settings", str(settings)],
            env=_clean_environment(
                QWQ_REAL_FLUTTER=str(real_flutter),
                PATH="/usr/bin:/bin",
            ),
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GATE_BLOCK", result.stderr)
        self.assertIn(
            "/custom/bin",
            settings.read_text(encoding="utf-8"),
            "存在外部管理键时不得改写用户 settings",
        )

    def test_raw_backend_blocker_names_supported_entrypoints(self) -> None:
        environment = dict(os.environ)
        for key in (
            "QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH",
            "QWQ_IOS_RUNTIME_CONFIG_PACKAGE_PATH",
            "QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON",
            "QWQ_LAUNCH_HANDOFF_JSON",
            "DART_DEFINES",
        ):
            environment.pop(key, None)
        environment["CONFIGURATION"] = "Debug-nonprod"
        environment["QWQ_APP_BUILD_PROFILE"] = "nonprod"
        environment["TARGET_BUILD_DIR"] = str(self.root / "build")
        environment["UNLOCALIZED_RESOURCES_FOLDER_PATH"] = "Runner.app"
        environment["QWQ_IOS_STACKCTL_PYTHON"] = sys.executable
        result = subprocess.run(
            ["bash", str(BACKEND_PREPARE_SCRIPT)],
            cwd=APP_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "run.sh",
            result.stderr,
            "raw backend 的 typed blocker 必须指引 canonical launcher 入口",
        )
        self.assertIn(
            "flutter",
            result.stderr.lower(),
            "raw backend 的 typed blocker 必须指引工作区 facade 激活入口",
        )


if __name__ == "__main__":
    unittest.main()
