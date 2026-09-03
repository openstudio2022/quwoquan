# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
#
# 层：local_contract。真实 Flutter SDK 单轨解析库契约（facade 接管已退役）：
# - `resolved_flutter_identity` 的正确解析与 digest 语义；
# - 解析优先级 QWQ_REAL_FLUTTER → FLUTTER_ROOT → PATH；
# - 钉定版本漂移拒绝；解析到已退役 shim 副本路径的防御；
# - 版本探针 allowlist env 与用户状态封闭（不写源码树 / 不泄露 secret）。
# 断言面为执行行为、退出码与捕获产物，不做脚本源码文本断言。

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = APP_DIR.parent
FACADE_DIR = APP_DIR / "scripts/tools/flutter_facade"
SUBPROCESS_TIMEOUT_SECONDS = 30

FIXTURE_VERSION_PAYLOAD = {
    "frameworkVersion": "3.47.0",
    "frameworkRevision": "fixture-revision",
    "engineRevision": "fixture-engine",
    "dartSdkVersion": "3.10.0",
    "channel": "stable",
}


def _load_facade_module():
    spec = importlib.util.spec_from_file_location(
        "flutter_facade_under_test", FACADE_DIR / "flutter_facade.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _write_fake_real_flutter(
    root: Path,
    *,
    relative: str = "fake-sdk/bin/flutter",
    payload: dict[str, object] | None = None,
) -> Path:
    encoded = json.dumps(payload if payload is not None else FIXTURE_VERSION_PAYLOAD)
    return _write_executable(
        root / relative,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$*" == "--version --machine" ]]; then\n'
        f"  printf '%s' {json.dumps(encoded)}\n"
        "  exit 0\n"
        "fi\n"
        "exit 64\n",
    )


def _write_retired_shim_copy(root: Path) -> Path:
    """构造历史 workspace facade shim 的结构性副本（废弃工作树残留形态）。"""
    package_dir = root / "stale-worktree/quwoquan_app/scripts/tools/flutter_facade"
    (package_dir / "flutter_facade.py").parent.mkdir(parents=True, exist_ok=True)
    (package_dir / "flutter_facade.py").write_text(
        "# stale retired facade module copy\n", encoding="utf-8"
    )
    return _write_executable(
        package_dir / "bin/flutter",
        "#!/usr/bin/env bash\nexit 99\n",
    )


def _write_launcher_dispatcher_copy(root: Path) -> Path:
    """构造 launcher bin `flutter` dispatcher 的结构性副本（bin/flutter + run.sh）。"""
    bin_dir = root / "copied-worktree/quwoquan_app/scripts/tools/launcher/bin"
    _write_executable(bin_dir / "run.sh", "#!/usr/bin/env bash\nexit 99\n")
    return _write_executable(
        bin_dir / "flutter",
        "#!/usr/bin/env bash\nexit 99\n",
    )


def _install_fake_workspace(root: Path) -> Path:
    """把解析库复制进假 App 树，使探针状态根落在假 repo 内可断言。"""
    app_root = root / "quwoquan_app"
    facade_dir = app_root / "scripts/tools/flutter_facade"
    facade_dir.mkdir(parents=True)
    (app_root / ".flutter-version").write_text("3.47.0\n", encoding="utf-8")
    for name in ("flutter_facade.py", "resolve_real_flutter.py"):
        shutil.copy2(FACADE_DIR / name, facade_dir / name)
    return facade_dir


def _write_probe_environment_spy(root: Path, *, capture_path: Path) -> Path:
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


def _clean_environment(**overrides: str) -> dict[str, str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if key.startswith("QWQ_"):
            environment.pop(key)
    environment.pop("FLUTTER_ROOT", None)
    environment.update(overrides)
    return environment


def _run_resolver(
    facade_dir: Path,
    *args: str,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(facade_dir / "resolve_real_flutter.py"), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )


class FlutterSdkResolutionContractTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_resolved_identity_exposes_executable_version_and_digest(self) -> None:
        real_flutter = _write_fake_real_flutter(self.root)
        module = _load_facade_module()
        identity = module.resolved_flutter_identity(
            _clean_environment(QWQ_REAL_FLUTTER=str(real_flutter))
        )
        self.assertEqual(identity["executable"], str(real_flutter.resolve()))
        self.assertEqual(identity["flutterVersion"], "3.47.0")
        canonical = json.dumps(
            {
                key: str(FIXTURE_VERSION_PAYLOAD[key])
                for key in (
                    "frameworkVersion",
                    "frameworkRevision",
                    "engineRevision",
                    "dartSdkVersion",
                    "channel",
                )
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(
            identity["commandResolutionDigest"],
            "sha256:" + hashlib.sha256(canonical).hexdigest(),
            "digest 必须是规范化 identity JSON 的 sha256，不泄露本机绝对路径",
        )

    def test_resolver_cli_prints_path_and_json_formats(self) -> None:
        facade_dir = _install_fake_workspace(self.root)
        real_flutter = _write_fake_real_flutter(self.root)
        env = _clean_environment(QWQ_REAL_FLUTTER=str(real_flutter))

        path_result = _run_resolver(facade_dir, cwd=self.root, env=env)
        self.assertEqual(path_result.returncode, 0, path_result.stderr)
        self.assertEqual(
            path_result.stdout.strip(), str(real_flutter.resolve())
        )

        json_result = _run_resolver(
            facade_dir, "--format", "json", cwd=self.root, env=env
        )
        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        identity = json.loads(json_result.stdout)
        self.assertEqual(
            set(identity),
            {"executable", "flutterVersion", "commandResolutionDigest"},
        )
        self.assertEqual(identity["flutterVersion"], "3.47.0")

    def test_explicit_identity_wins_over_flutter_root_and_path(self) -> None:
        explicit = _write_fake_real_flutter(self.root, relative="explicit/bin/flutter")
        from_root = _write_fake_real_flutter(self.root, relative="rooted/bin/flutter")
        on_path = _write_fake_real_flutter(self.root, relative="pathed/bin/flutter")
        module = _load_facade_module()
        resolved = module.resolve_real_flutter(
            _clean_environment(
                QWQ_REAL_FLUTTER=str(explicit),
                FLUTTER_ROOT=str(from_root.parent.parent),
                PATH=f"{on_path.parent}:/usr/bin:/bin",
            )
        )
        self.assertEqual(resolved, explicit.resolve())

        resolved_from_root = module.resolve_real_flutter(
            _clean_environment(
                FLUTTER_ROOT=str(from_root.parent.parent),
                PATH=f"{on_path.parent}:/usr/bin:/bin",
            )
        )
        self.assertEqual(resolved_from_root, from_root.resolve())

        resolved_from_path = module.resolve_real_flutter(
            _clean_environment(PATH=f"{on_path.parent}:/usr/bin:/bin")
        )
        self.assertEqual(resolved_from_path, on_path.resolve())

    def test_invalid_flutter_root_is_typed_and_does_not_fall_through(self) -> None:
        on_path = _write_fake_real_flutter(self.root, relative="pathed/bin/flutter")
        module = _load_facade_module()
        with self.assertRaises(module.FacadeError) as context:
            module.resolve_real_flutter(
                _clean_environment(
                    FLUTTER_ROOT=str(self.root / "missing-root"),
                    PATH=f"{on_path.parent}:/usr/bin:/bin",
                )
            )
        self.assertIn("FLUTTER_ROOT", str(context.exception))

    def test_version_drift_is_rejected_against_pinned_truth_source(self) -> None:
        drifted = _write_fake_real_flutter(
            self.root,
            payload={"frameworkVersion": "3.0.0"},
        )
        module = _load_facade_module()
        with self.assertRaises(module.FacadeError) as context:
            module.resolve_real_flutter(
                _clean_environment(QWQ_REAL_FLUTTER=str(drifted))
            )
        self.assertIn("3.47.0", str(context.exception))
        self.assertIn("3.0.0", str(context.exception))

    def test_explicit_retired_shim_copy_is_rejected(self) -> None:
        shim = _write_retired_shim_copy(self.root)
        module = _load_facade_module()
        with self.assertRaises(module.FacadeError) as context:
            module.resolve_real_flutter(
                _clean_environment(QWQ_REAL_FLUTTER=str(shim))
            )
        self.assertIn("已退役", str(context.exception))

    def test_path_scan_skips_retired_shim_copy_and_resolves_real_sdk(self) -> None:
        shim = _write_retired_shim_copy(self.root)
        real_flutter = _write_fake_real_flutter(self.root)
        module = _load_facade_module()
        resolved = module.resolve_real_flutter(
            _clean_environment(
                PATH=f"{shim.parent}:{real_flutter.parent}:/usr/bin:/bin"
            )
        )
        self.assertEqual(
            resolved,
            real_flutter.resolve(),
            "PATH 上的已退役 shim 副本必须被跳过，解析到真实 SDK",
        )

    def test_path_scan_skips_launcher_dispatcher_and_resolves_real_sdk(self) -> None:
        # 受管 PATH 首位是 launcher bin（flutter dispatcher）；facade 解析真实
        # SDK 时必须按物理形态跳过它，否则 dispatcher 委托解析会形成递归。
        dispatcher = _write_launcher_dispatcher_copy(self.root)
        real_flutter = _write_fake_real_flutter(self.root)
        module = _load_facade_module()
        resolved = module.resolve_real_flutter(
            _clean_environment(
                PATH=f"{dispatcher.parent}:{real_flutter.parent}:/usr/bin:/bin"
            )
        )
        self.assertEqual(
            resolved,
            real_flutter.resolve(),
            "PATH 上的 launcher dispatcher 必须被跳过，解析到真实 SDK",
        )

    def test_explicit_launcher_dispatcher_is_rejected(self) -> None:
        dispatcher = _write_launcher_dispatcher_copy(self.root)
        module = _load_facade_module()
        with self.assertRaises(module.FacadeError) as context:
            module.resolve_real_flutter(
                _clean_environment(QWQ_REAL_FLUTTER=str(dispatcher))
            )
        self.assertIn("dispatcher", str(context.exception))

    def test_repository_launcher_dispatcher_is_structurally_detected(self) -> None:
        module = _load_facade_module()
        repository_dispatcher = APP_DIR / "scripts/tools/launcher/bin/flutter"
        self.assertTrue(repository_dispatcher.is_file())
        with self.assertRaises(module.FacadeError):
            module.resolve_real_flutter(
                _clean_environment(QWQ_REAL_FLUTTER=str(repository_dispatcher))
            )

    def test_unresolvable_sdk_is_typed_via_cli(self) -> None:
        facade_dir = _install_fake_workspace(self.root)
        result = _run_resolver(
            facade_dir,
            cwd=self.root,
            env=_clean_environment(PATH="/usr/bin:/bin"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("GATE_BLOCK", result.stderr)
        self.assertIn("FLUTTER_ROOT", result.stderr)

    # ------------------------------------------------------------------
    # 版本探针 allowlist env 与状态封闭
    # ------------------------------------------------------------------

    def test_version_probe_uses_explicit_output_root_outside_workspace(
        self,
    ) -> None:
        facade_dir = _install_fake_workspace(self.root)
        external_temporary = tempfile.TemporaryDirectory()
        self.addCleanup(external_temporary.cleanup)
        explicit_output_root = (
            Path(external_temporary.name) / "canonical-output"
        ).resolve()
        capture = self.root / "explicit-output-probe-environment.json"
        real_flutter = _write_probe_environment_spy(self.root, capture_path=capture)
        environment = _clean_environment(
            QWQ_REAL_FLUTTER=str(real_flutter),
            QWQ_OUTPUT_ROOT=str(explicit_output_root),
            PATH="/usr/bin:/bin",
            QWQ_PROBE_SECRET_DO_NOT_LEAK="probe-secret-sentinel",
        )

        result = _run_resolver(
            facade_dir, "--format", "json", cwd=self.root, env=environment
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        managed_root = explicit_output_root / "env/repo/local/flutter-facade-probe"
        probe_environment = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(Path(probe_environment["HOME"]), managed_root / "home")
        self.assertEqual(
            Path(probe_environment["XDG_CONFIG_HOME"]), managed_root / "config"
        )
        self.assertEqual(
            Path(probe_environment["XDG_CACHE_HOME"]), managed_root / "cache"
        )
        self.assertFalse(
            (self.root / ".qwq_output").exists(),
            "显式外部 output root 不得在 source projection 创建 derived output",
        )
        self.assertIsNone(
            probe_environment["outputRoot"],
            "QWQ_OUTPUT_ROOT 只定位探针状态根，不得传给 Flutter child",
        )
        self.assertIsNone(probe_environment["secret"])
        terminal_output = result.stdout + result.stderr
        self.assertNotIn("probe-secret-sentinel", terminal_output)
        self.assertNotIn(str(explicit_output_root), terminal_output)

    def test_version_probe_rejects_relative_output_root_without_path_disclosure(
        self,
    ) -> None:
        facade_dir = _install_fake_workspace(self.root)
        capture = self.root / "relative-output-probe-environment.json"
        real_flutter = _write_probe_environment_spy(self.root, capture_path=capture)
        sensitive_relative_path = "relative-probe-secret-sentinel/output"
        environment = _clean_environment(
            QWQ_REAL_FLUTTER=str(real_flutter),
            QWQ_OUTPUT_ROOT=sensitive_relative_path,
            PATH="/usr/bin:/bin",
        )

        result = _run_resolver(
            facade_dir, "--format", "json", cwd=self.root, env=environment
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
        facade_dir = _install_fake_workspace(self.root)
        capture = self.root / "probe-environment.json"
        real_flutter = _write_probe_environment_spy(self.root, capture_path=capture)
        environment = _clean_environment(
            QWQ_REAL_FLUTTER=str(real_flutter),
            PATH="/usr/bin:/bin",
            QWQ_PROBE_SECRET_DO_NOT_LEAK="probe-secret-sentinel",
        )
        for key in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            environment.pop(key, None)

        result = _run_resolver(
            facade_dir, "--format", "json", cwd=self.root, env=environment
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


if __name__ == "__main__":
    unittest.main()
