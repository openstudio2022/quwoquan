"""local_contract: App identity 共享可写状态隔离门禁的正负例。

门禁判据是「退役的共享可写 identity 状态不复存在，且每个环境的选择都是静态可读的」。
只在真实仓库上跑一次 OK 无法证明判据还成立——违规样本必须能被构造出来并被拒绝，
因此这里用 tempfile 合成一棵最小 App 树，逐条构造违规形态。
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = (
    ROOT
    / "quwoquan_app/scripts/runtime/platform/verify_app_identity_state_isolation.py"
)

#: 门禁扫描的运行时入口，相对 `quwoquan_app/`。任一入口重新消费退役状态都必须被拒。
SCANNED_RUNTIME_PATHS = (
    "run.sh",
    "scripts/device/run_app_instance.sh",
    "scripts/device/verify_ios_hot_restart.py",
    "scripts/device/build_startup_environment_matrix.py",
    "scripts/ios/build_prepare_dart_defines.sh",
)

#: 退役状态的两个词法指纹：一个是生成脚本名，一个是被生成文件名。两者都不得再出现在
#: 运行时路径里，否则「共享可写 xcconfig 已删除」只是表象。
RETIRED_STATE_MARKERS = (
    "write_environment_xcconfig",
    "QWQEnvironment.xcconfig",
)

_LAUNCHER = """#!/usr/bin/env bash
set -euo pipefail
flutter run --flavor "$QWQ_APP_RUNTIME_ENV" --dart-define-from-file=defines.json
"""

# 非 Prod flavor 只能由 run.sh 单点决定；这里刻意不出现 `flutter run`，
# 一旦本文件自己拉起 flutter，环境选择就分叉成两处真相。
_APP_INSTANCE = """#!/usr/bin/env bash
set -euo pipefail
exec bash "$APP_DIR/run.sh" "$@"
"""

_HOT_RESTART = """#!/usr/bin/env python3
\"\"\"iOS 热重启验证入口。\"\"\"
"""

_STARTUP_MATRIX = """#!/usr/bin/env python3
\"\"\"启动环境矩阵构建入口。\"\"\"
"""

_DART_DEFINES = """#!/usr/bin/env bash
set -euo pipefail
echo "prepare dart defines"
"""

_PUBSPEC = """name: quwoquan_app
flutter:
  default-flavor: alpha
"""

_IDENTITY = {
    "environments": ["alpha", "beta", "gamma", "prod"],
    "applicationIdSuffixByEnvironment": {
        "alpha": ".alpha",
        "beta": ".beta",
        "gamma": ".gamma",
        "prod": "",
    },
}


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_app_identity_state_isolation", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_canonical_tree(root: Path) -> Path:
    """写出一棵门禁认为完全合规的最小 App 树，返回 `quwoquan_app/` 目录。"""

    app = root / "quwoquan_app"
    _write(app / "run.sh", _LAUNCHER)
    _write(app / "scripts/device/run_app_instance.sh", _APP_INSTANCE)
    _write(app / "scripts/device/verify_ios_hot_restart.py", _HOT_RESTART)
    _write(app / "scripts/device/build_startup_environment_matrix.py", _STARTUP_MATRIX)
    _write(app / "scripts/ios/build_prepare_dart_defines.sh", _DART_DEFINES)
    _write(app / "pubspec.yaml", _PUBSPEC)
    _write(
        app / "android/app/app_identity.generated.json",
        json.dumps(_IDENTITY, indent=2, ensure_ascii=False) + "\n",
    )
    return app


class AppIdentityStateIsolationGateTest(unittest.TestCase):
    def test_canonical_identity_tree_is_accepted(self) -> None:
        """合规树必须零 issue：否则任何拒绝断言都只是在测门禁的误报。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            _write_canonical_tree(root)
            self.assertEqual(module.collect_issues(root), [])

    def test_retired_shared_state_files_are_rejected(self) -> None:
        """共享可写 xcconfig 与它的生成脚本是同一份债的两端，缺一条都会漏判。"""

        module = _load_module()
        for relative in (
            "ios/Flutter/QWQEnvironment.xcconfig",
            "scripts/ios/write_environment_xcconfig.sh",
        ):
            with self.subTest(relative=relative):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    app = _write_canonical_tree(root)
                    _write(app / relative, "# 退役状态复活\n")
                    issues = module.collect_issues(root)
                    self.assertIn(
                        f"shared mutable App identity state must not exist: "
                        f"quwoquan_app/{relative}",
                        issues,
                    )

    def test_runtime_path_consuming_retired_state_is_rejected(self) -> None:
        """删掉文件但让入口继续读写它，等于把共享状态挪到运行时；每个入口都要拦。"""

        module = _load_module()
        for relative in SCANNED_RUNTIME_PATHS:
            for marker in RETIRED_STATE_MARKERS:
                with self.subTest(relative=relative, marker=marker):
                    with tempfile.TemporaryDirectory() as tmp:
                        root = Path(tmp).resolve()
                        app = _write_canonical_tree(root)
                        target = app / relative
                        target.write_text(
                            target.read_text(encoding="utf-8")
                            + f"# {marker}\n",
                            encoding="utf-8",
                        )
                        self.assertIn(
                            f"runtime path mutates or consumes retired identity "
                            f"state: quwoquan_app/{relative}",
                            module.collect_issues(root),
                        )

    def test_launcher_must_select_the_canonical_flavor(self) -> None:
        """flavor 必须由 run.sh 显式静态选择；靠环境变量隐式生效就退回了共享状态。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = _write_canonical_tree(root)
            _write(
                app / "run.sh",
                "#!/usr/bin/env bash\nset -euo pipefail\nflutter run\n",
            )
            self.assertIn(
                "run.sh must select the canonical Flutter flavor",
                module.collect_issues(root),
            )

    def test_app_instance_must_delegate_flavor_selection_to_launcher(self) -> None:
        """自己拉起 flutter 或不再委派，都会让 flavor 选择出现第二份真相源。"""

        module = _load_module()
        expected = (
            "run_app_instance.sh must delegate non-Prod flavor selection to run.sh"
        )
        variants = {
            "no_delegation": (
                "#!/usr/bin/env bash\nset -euo pipefail\necho '直接启动'\n"
            ),
            "self_launch": (
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                'exec bash "$APP_DIR/run.sh" || flutter run\n'
            ),
        }
        for name, source in variants.items():
            with self.subTest(variant=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    app = _write_canonical_tree(root)
                    _write(app / "scripts/device/run_app_instance.sh", source)
                    self.assertIn(expected, module.collect_issues(root))

    def test_unflavored_shared_runner_scheme_is_rejected(self) -> None:
        """无 flavor 的 Runner scheme 一旦可选，Xcode 侧就能绕过静态 flavor 选择。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = _write_canonical_tree(root)
            _write(
                app / "ios/Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme",
                "<Scheme/>\n",
            )
            self.assertIn(
                "unflavored shared Runner scheme must not remain selectable",
                module.collect_issues(root),
            )

    def test_pubspec_must_pin_the_deterministic_default_flavor(self) -> None:
        """默认 flavor 缺失时，未显式选择的构建会落到不确定的环境上。"""

        module = _load_module()
        for source in (
            "name: quwoquan_app\nflutter:\n  uses-material-design: true\n",
            "name: quwoquan_app\nflutter:\n  default-flavor: prod\n",
        ):
            with self.subTest(source=source):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    app = _write_canonical_tree(root)
                    _write(app / "pubspec.yaml", source)
                    self.assertIn(
                        "pubspec.yaml must make alpha the deterministic default flavor",
                        module.collect_issues(root),
                    )

    def test_generated_identity_matrix_must_cover_four_environments(self) -> None:
        """四环境是闭集且有序：少一个或换顺序都说明 codegen 输入已经漂移。"""

        module = _load_module()
        expected = "generated App identity environment matrix is incomplete"
        for environments in (
            ["alpha", "beta", "prod"],
            ["alpha", "beta", "gamma", "prod", "prod-gray"],
            ["prod", "gamma", "beta", "alpha"],
        ):
            with self.subTest(environments=environments):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    app = _write_canonical_tree(root)
                    _write(
                        app / "android/app/app_identity.generated.json",
                        json.dumps({"environments": environments}) + "\n",
                    )
                    self.assertIn(expected, module.collect_issues(root))

    def test_invalid_generated_identity_document_is_rejected(self) -> None:
        """codegen 产物损坏必须是显式失败，不能因为解析不出来就当作通过。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = _write_canonical_tree(root)
            _write(
                app / "android/app/app_identity.generated.json",
                '{"environments": ["alpha",\n',
            )
            issues = module.collect_issues(root)
            self.assertTrue(
                any(
                    issue.startswith("generated App identity document is invalid:")
                    for issue in issues
                ),
                msg=f"issues={issues}",
            )

    def test_missing_required_input_is_rejected(self) -> None:
        """输入缺失时门禁必须报缺，而不是把「读不到」当成「没有违规」。"""

        module = _load_module()
        for relative in (
            *SCANNED_RUNTIME_PATHS,
            "pubspec.yaml",
            "android/app/app_identity.generated.json",
        ):
            with self.subTest(relative=relative):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    app = _write_canonical_tree(root)
                    (app / relative).unlink()
                    self.assertIn(
                        f"required App identity input is missing: "
                        f"quwoquan_app/{relative}",
                        module.collect_issues(root),
                    )

    def test_cli_maps_issues_to_exit_codes(self) -> None:
        """`--repo-root` 是门禁唯一可注入点；退出码必须随 issue 有无翻转。"""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            app = _write_canonical_tree(root)
            self.assertEqual(module.main(["--repo-root", str(root)]), 0)
            _write(app / "ios/Flutter/QWQEnvironment.xcconfig", "QWQ_ENV=alpha\n")
            self.assertEqual(module.main(["--repo-root", str(root)]), 1)

    def test_real_repository_currently_holds_the_invariant(self) -> None:
        """合成树证明判据可判，真实仓库证明判据当下成立。"""

        module = _load_module()
        self.assertEqual(module.collect_issues(ROOT), [])


if __name__ == "__main__":
    unittest.main()
