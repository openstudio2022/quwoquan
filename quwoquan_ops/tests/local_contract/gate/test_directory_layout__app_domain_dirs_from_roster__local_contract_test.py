"""端侧测试层的 domain 目录必须由 ContractGraph 名册派生，而不是门禁自带清单。

本文件承载：名册派生本身、patrol/legacy 允许清单与 support owner 语义。

由 1000 行硬顶拆分自 test_directory_layout__app_domain_dirs_from_roster__local_contract_test.py；
测试逐字搬移，共享常量与 helper 基类见
quwoquan_ops/tests/support/directory_layout_app_domain_dirs_test_support.py。
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.tests.support.directory_layout_app_domain_dirs_test_support import (
    VERIFIER_CONSTANTS_PATH,
    AppDomainTestDirsFromRosterCaseBase,
)


class AppDomainTestDirsFromRosterContractTest(AppDomainTestDirsFromRosterCaseBase):
    # -- 派生本身 ---------------------------------------------------------

    def test_test_file_discovery_is_stably_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "z__local_contract_test.dart").write_text(
                "void main() {}\n", encoding="utf-8"
            )
            (root / "a__local_contract_test.dart").write_text(
                "void main() {}\n", encoding="utf-8"
            )
            self.assertEqual(
                [path.name for path in self.verifier.iter_test_files(root)],
                ["a__local_contract_test.dart", "z__local_contract_test.dart"],
            )

    def test_object_test_dirs_are_service_container_and_cross_cutting_roots(
        self,
    ) -> None:
        expected = {"service", "runtime", "design_system", "l10n"}
        self.assertEqual(self.verifier.app_object_test_dirs(), expected)

    def test_every_layer_accepts_the_service_container(self) -> None:
        object_dirs = self.verifier.app_object_test_dirs()
        for layer in ("local_contract", "api_integration", "user_acceptance"):
            allowed = self.verifier.allowed_app_layer_dirs(layer, object_dirs)
            self.assertIn("service", allowed, f"{layer} 拒绝了 service 容器")

    def test_journeys_is_only_a_local_contract_or_user_acceptance_root(self) -> None:
        object_dirs = self.verifier.app_object_test_dirs()
        self.assertIn(
            "journeys",
            self.verifier.allowed_app_layer_dirs("local_contract", object_dirs),
        )
        self.assertNotIn(
            "journeys",
            self.verifier.allowed_app_layer_dirs("api_integration", object_dirs),
        )
        self.assertIn(
            "journeys",
            self.verifier.allowed_app_layer_dirs("user_acceptance", object_dirs),
        )

    def test_patrol_runner_root_is_not_a_legacy_allowance(self) -> None:
        object_dirs = self.verifier.app_object_test_dirs()
        self.assertEqual(
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["user_acceptance"],
            set(),
        )
        self.assertIn(
            "patrol",
            self.verifier.allowed_app_layer_dirs("user_acceptance", object_dirs),
        )
        self.assertNotIn(
            "patrol",
            self.verifier.allowed_app_layer_dirs("local_contract", object_dirs),
        )

    def test_patrol_runner_root_contains_only_pubspec_entries(self) -> None:
        runner_root = self.verifier.APP_ROOT / "user_acceptance/patrol"
        actual = {
            path.relative_to(runner_root).as_posix()
            for path in runner_root.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        self.assertEqual(actual, self.verifier.APP_PATROL_RUNNER_FILES)

    def test_patrol_target_discovery_rejects_textual_import_decoys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "nested/real__user_acceptance_test.dart"
            real.parent.mkdir(parents=True)
            real.write_text(
                "import 'package:patrol/patrol.dart';\nvoid main() {}\n",
                encoding="utf-8",
            )
            (root / "comment__user_acceptance_test.dart").write_text(
                "/*\nimport 'package:patrol/patrol.dart';\n*/\nvoid main() {}\n",
                encoding="utf-8",
            )
            (root / "string__user_acceptance_test.dart").write_text(
                'const text = "import \'package:patrol/patrol.dart\';";\n',
                encoding="utf-8",
            )
            (root / "wrong_suffix_test.dart").write_text(
                "import 'package:patrol/patrol.dart';\nvoid main() {}\n",
                encoding="utf-8",
            )

            self.assertEqual(
                self.verifier.app_patrol_user_acceptance_targets(root),
                [real],
            )

    def test_retired_empty_shell_allowances_do_not_return(self) -> None:
        self.assertNotIn(
            "app",
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["local_contract"],
        )
        self.assertNotIn(
            "core",
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["local_contract"],
        )
        self.assertNotIn(
            "ui",
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["local_contract"],
        )
        self.assertNotIn(
            "cloud",
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["local_contract"],
        )
        self.assertNotIn(
            "quality",
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["local_contract"],
        )
        self.assertNotIn(
            "ui",
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["api_integration"],
        )
        self.assertNotIn(
            "cloud",
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["api_integration"],
        )
        self.assertNotIn(
            "pages",
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["user_acceptance"],
        )
        self.assertNotIn(
            "quality",
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["user_acceptance"],
        )

    def test_patrol_allowance_does_not_return_after_object_cutover(self) -> None:
        self.assertEqual(
            self.verifier.APP_UNMIGRATED_LAYER_DIRS["user_acceptance"],
            set(),
        )

    def test_retired_empty_shell_roots_have_no_runnable_tests(self) -> None:
        for layer, name in (
            ("local_contract", "ui"),
            ("local_contract", "cloud"),
            ("local_contract", "quality"),
            ("api_integration", "cloud"),
        ):
            with self.subTest(layer=layer, name=name):
                self.assertEqual(
                    self.verifier.iter_app_test_files(
                        self.verifier.APP_ROOT / layer / name
                    ),
                    [],
                )

    def test_unmigrated_residue_never_contains_a_roster_domain(self) -> None:
        residue: set[str] = set()
        for names in self.verifier.APP_UNMIGRATED_LAYER_DIRS.values():
            residue |= set(names)
        self.assertEqual(sorted(residue & self.domains), [])

    def test_app_directory_constants_never_hardcode_a_roster_domain_name(self) -> None:
        """回归锁：端侧目录常量里出现 domain 字面量即代表第二真相源复活。"""
        tree = ast.parse(VERIFIER_CONSTANTS_PATH.read_text(encoding="utf-8"))
        literals: set[str] = set()
        for statement in tree.body:
            if not isinstance(statement, ast.Assign):
                continue
            if not any(
                isinstance(target, ast.Name) and target.id.startswith("APP_")
                for target in statement.targets
            ):
                continue
            for node in ast.walk(statement.value):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    literals.add(node.value)
        self.assertTrue(literals, "未采集到任何端侧目录常量字面量，扫描失效")
        self.assertEqual(sorted(literals & self.domains), [])

    def test_support_owner_is_derived_from_object_or_cross_cutting_shape(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]
        support_root = Path("test/support")
        roster = self.verifier.app_object_roster()

        self.assertEqual(
            self.verifier.app_support_path_identity(
                support_root.joinpath(
                    *self._owner_parts(domain, context, object_name), "fixture.dart"
                ),
                support_root,
                roster,
            ),
            ("object", domain, context, object_name),
        )
        self.assertEqual(
            self.verifier.app_support_path_identity(
                support_root / "runtime/transport/recording_executor.dart",
                support_root,
                roster,
            ),
            ("cross_cutting", "runtime"),
        )
        self.assertEqual(
            self.verifier.app_support_path_identity(
                support_root / "design_system/golden/font_loader.dart",
                support_root,
                roster,
            ),
            None,
        )

    def test_support_path_without_exact_object_owner_is_rejected(self) -> None:
        domain, context, _object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            service = self.verifier.opm.app_service_for_context(domain, context)
            shallow = (
                app_test_root
                / "support"
                / "service"
                / service
                / context
                / "fixture.dart"
            )
            shallow.parent.mkdir(parents=True)
            shallow.write_text("class Fixture {}\n", encoding="utf-8")
            unowned = app_test_root / "support/cloud_services/helper.dart"
            unowned.parent.mkdir(parents=True)
            unowned.write_text("class Helper {}\n", encoding="utf-8")

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 2, failures)
        self.assertTrue(all("no canonical support owner" in item for item in failures))

    def test_object_support_export_barrel_is_rejected(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            barrel = app_test_root.joinpath(
                "support",
                *self._owner_parts(domain, context, object_name),
                "repository_mock_reexports.dart",
            )
            barrel.parent.mkdir(parents=True)
            barrel.write_text(
                "export 'first_typed_double.dart';\n"
                "export 'second_typed_double.dart';\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("support export barrel", failures[0])
        self.assertIn("import the unique object-owned helper directly", failures[0])

    def test_cross_cutting_runtime_support_export_is_not_a_business_mock_barrel(
        self,
    ) -> None:
        def build(app_test_root: Path) -> None:
            barrel = app_test_root / "support/runtime/pageflip/pageflip.dart"
            barrel.parent.mkdir(parents=True)
            barrel.write_text(
                "export 'src/pageflip_engine.dart';\n",
                encoding="utf-8",
            )

        self.assertEqual(self._verify_app(build), [])

    def test_cross_cutting_root_cannot_hide_a_mock_reexport_barrel(self) -> None:
        def build(app_test_root: Path) -> None:
            barrel = app_test_root / "support/runtime/repository_mock_reexports.dart"
            barrel.parent.mkdir(parents=True)
            barrel.write_text(
                "export '../../content/content/post/post_typed_double.dart';\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("support export barrel", failures[0])

    def test_design_system_is_not_a_cross_cutting_support_owner(self) -> None:
        def build(app_test_root: Path) -> None:
            helper = app_test_root / "support/design_system/golden/font_loader.dart"
            helper.parent.mkdir(parents=True)
            helper.write_text("class FontLoader {}\n", encoding="utf-8")

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("no canonical support owner", failures[0])

    def test_object_support_cannot_import_another_object_support(self) -> None:
        source_object, target_object = sorted(self.objects)[:2]

        def build(app_test_root: Path) -> None:
            source = app_test_root.joinpath(
                "support", *self._owner_parts(*source_object), "source.dart"
            )
            target = app_test_root.joinpath(
                "support", *self._owner_parts(*target_object), "target.dart"
            )
            source.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            target.write_text("class TargetDouble implements Port {}\n", encoding="utf-8")
            source.write_text(
                "import '../../../../"
                + "/".join(self._owner_parts(*target_object))
                + "/target.dart';\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertTrue(any("cross-owner support edge" in item for item in failures), failures)

    def test_runtime_support_cannot_import_object_support(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            target = app_test_root.joinpath(
                "support",
                *self._owner_parts(domain, context, object_name),
                "target.dart",
            )
            target.parent.mkdir(parents=True)
            target.write_text("class TargetDouble implements Port {}\n", encoding="utf-8")
            source = app_test_root / "support/runtime/harness.dart"
            source.parent.mkdir(parents=True)
            source.write_text(
                "import '../"
                + "/".join(self._owner_parts(domain, context, object_name))
                + "/target.dart';\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertTrue(any("runtime support may use only runtime" in item for item in failures), failures)

    def test_conditional_import_and_export_include_every_uri_branch(self) -> None:
        tokens = self.verifier._dart_source_tokens(
            "import 'base.dart' if (dart.library.io) 'io.dart' "
            "if (dart.library.html) 'web.dart';\n"
            "export 'public.dart' if (dart.library.io) 'private_io.dart';\n"
        )
        self.assertEqual(
            self.verifier._dart_import_uris(tokens),
            ["base.dart", "io.dart", "web.dart"],
        )
        self.assertEqual(
            self.verifier._dart_export_uris(tokens),
            ["public.dart", "private_io.dart"],
        )

    def test_part_edge_cannot_cross_support_object_owner(self) -> None:
        source_object, target_object = sorted(self.objects)[:2]

        def build(app_test_root: Path) -> None:
            source = app_test_root.joinpath(
                "support", *self._owner_parts(*source_object), "source.dart"
            )
            target = app_test_root.joinpath(
                "support", *self._owner_parts(*target_object), "target.dart"
            )
            source.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            target.write_text("part of 'source.dart';\n", encoding="utf-8")
            source.write_text(
                "part '../../../../"
                + "/".join(self._owner_parts(*target_object))
                + "/target.dart';\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertTrue(any("cross-owner support edge" in item for item in failures), failures)


if __name__ == "__main__":
    unittest.main()
