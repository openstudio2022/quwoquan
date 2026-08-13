"""端侧测试层的 domain 目录必须由 ContractGraph 名册派生，而不是门禁自带清单。

本文件承载：_verify_app 驱动的目录判定接受/拒绝行为与 App Python 证据边界。

由 1000 行硬顶拆分自 test_directory_layout__app_domain_dirs_from_roster__local_contract_test.py；
测试逐字搬移，共享常量与 helper 基类见
quwoquan_ops/tests/support/directory_layout_app_domain_dirs_test_support.py。
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.tests.support.directory_layout_app_domain_dirs_test_support import (
    GATE_REPO_PATH,
    MAKEFILE_PATH,
    REPO_ROOT,
    AppDomainTestDirsFromRosterCaseBase,
)


class AppDomainTestDirsFromRosterContractTest(AppDomainTestDirsFromRosterCaseBase):
    # -- 目录判定行为 -----------------------------------------------------

    def test_baseline_tree_without_domain_dirs_is_accepted(self) -> None:
        self.assertEqual(self._verify_app(lambda _root: None), [])

    def test_roster_owned_object_paths_are_accepted_in_every_layer(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            for layer in ("local_contract", "api_integration", "user_acceptance"):
                target = app_test_root.joinpath(
                    layer,
                    *self._owner_parts(domain, context, object_name),
                    f"owned__{layer}_test.dart",
                )
                target.parent.mkdir(parents=True)
                target.write_text("void main() {}\n", encoding="utf-8")

        self.assertEqual(self._verify_app(build), [])

    def test_directory_outside_the_roster_is_rejected(self) -> None:
        unknown = "not_a_contract_graph_domain"
        self.assertNotIn(unknown, self.domains)

        def build(app_test_root: Path) -> None:
            (app_test_root / "local_contract" / unknown).mkdir()

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn(unknown, failures[0])
        self.assertIn("is not an allowed test directory", failures[0])

    def test_shallow_object_path_is_rejected(self) -> None:
        domain, context, _object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            service = self.verifier.opm.app_service_for_context(domain, context)
            target = app_test_root.joinpath(
                "local_contract",
                "service",
                service,
                context,
                "shallow__local_contract_test.dart",
            )
            target.parent.mkdir(parents=True)
            target.write_text("void main() {}\n", encoding="utf-8")

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("service/<service>/<context>/<object>", failures[0])

    def test_unknown_object_below_real_domain_context_is_rejected(self) -> None:
        domain, context, _object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            service = self.verifier.opm.app_service_for_context(domain, context)
            target = app_test_root.joinpath(
                "local_contract",
                "service",
                service,
                context,
                "not_a_roster_object",
                "case__local_contract_test.dart",
            )
            target.parent.mkdir(parents=True)
            target.write_text("void main() {}\n", encoding="utf-8")

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("ContractGraph-owned", failures[0])

    def test_object_test_directory_rejects_non_test_dart_and_python_helpers(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner = app_test_root.joinpath(
                "local_contract", *self._owner_parts(domain, context, object_name)
            )
            owner.mkdir(parents=True)
            (owner / "repository_mock_reexports.dart").write_text(
                "part 'helper.dart';\n", encoding="utf-8"
            )
            (owner / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 2, failures)
        self.assertTrue(all("non-test source" in item for item in failures), failures)

    def test_object_test_directory_rejects_a_dart_part_helper(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner = app_test_root.joinpath(
                "local_contract",
                *self._owner_parts(domain, context, object_name),
                "owner__local_contract_test.dart",
            )
            owner.parent.mkdir(parents=True)
            owner.write_text(
                "part 'owner_steps.dart';\nvoid main() {}\n", encoding="utf-8"
            )
            (owner.parent / "owner_steps.dart").write_text(
                "part of 'owner__local_contract_test.dart';\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertTrue(any("owner_steps.dart" in item for item in failures), failures)
        self.assertTrue(any("non-test source" in item for item in failures), failures)

    # -- legacy allowance 只能显式阻断 ---------------------------------

    def test_stale_unmigrated_residue_entry_is_rejected(self) -> None:
        failures = self._verify_app(
            lambda _root: None,
            allowances={"local_contract": {"ui"}},
        )
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("local_contract/ui", failures[0])
        self.assertIn("stale allowance", failures[0])

    def test_empty_legacy_directory_is_rejected(self) -> None:
        def build(app_test_root: Path) -> None:
            (app_test_root / "api_integration/ui").mkdir()

        failures = self._verify_app(
            build,
            allowances={"api_integration": {"ui"}},
        )
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("empty-shell", failures[0])
        self.assertIn("no Dart/Python tests", failures[0])

    def test_non_test_artifacts_do_not_satisfy_legacy_allowance(self) -> None:
        def build(app_test_root: Path) -> None:
            artifact = (
                app_test_root
                / "user_acceptance/pages/settings/goldens/settings_dark.png"
            )
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"not-a-test")

        failures = self._verify_app(
            build,
            allowances={"user_acceptance": {"pages"}},
        )
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("empty-shell", failures[0])
        self.assertIn("non-test artifacts", failures[0])

    def test_each_remaining_legacy_test_is_rejected(self) -> None:
        def build(app_test_root: Path) -> None:
            target = (
                app_test_root / "local_contract/ui/legacy__local_contract_test.dart"
            )
            target.parent.mkdir(parents=True)
            target.write_text("void main() {}\n", encoding="utf-8")

        failures = self._verify_app(
            build,
            allowances={"local_contract": {"ui"}},
        )
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("legacy__local_contract_test.dart", failures[0])
        self.assertIn("remains under legacy test root", failures[0])

    def test_runnable_test_blocks_api_cloud_allowance_retirement(self) -> None:
        def build(app_test_root: Path) -> None:
            target = (
                app_test_root
                / "api_integration/cloud/chat/"
                "roster__api_integration_test.dart"
            )
            target.parent.mkdir(parents=True)
            target.write_text("void main() {}\n", encoding="utf-8")

        failures = self._verify_app(
            build,
            allowances={"api_integration": {"cloud"}},
        )
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("roster__api_integration_test.dart", failures[0])
        self.assertIn("remains under legacy test root", failures[0])

    def test_python_test_below_legacy_root_is_not_omitted(self) -> None:
        def build(app_test_root: Path) -> None:
            target = (
                app_test_root
                / "local_contract/ui/discovery/"
                "works_video_session_lifecycle__local_contract_test.py"
            )
            target.parent.mkdir(parents=True)
            target.write_text("def test_lifecycle():\n    assert True\n", encoding="utf-8")

        failures = self._verify_app(
            build,
            allowances={"local_contract": {"ui"}},
        )
        self.assertEqual(len(failures), 1, failures)
        self.assertIn(
            "works_video_session_lifecycle__local_contract_test.py",
            failures[0],
        )
        self.assertIn("remains under legacy test root", failures[0])

    # -- 跨对象 Journey 按依赖真实度分 local_contract / user_acceptance --

    def test_user_acceptance_journey_direct_test_is_accepted(self) -> None:
        def build(app_test_root: Path) -> None:
            journey = app_test_root / "user_acceptance/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__user_acceptance_test.dart").write_text(
                "void main() {}\n", encoding="utf-8"
            )

        self.assertEqual(self._verify_app(build), [])

    def test_local_contract_journey_with_widget_boundary_is_accepted(self) -> None:
        def build(app_test_root: Path) -> None:
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                "void main() { testWidgets('journey', (tester) async {}); }\n",
                encoding="utf-8",
            )

        self.assertEqual(self._verify_app(build), [])

    def test_local_contract_journey_resolves_relative_test_support_import(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner_path = "/".join(self._owner_parts(domain, context, object_name))
            support = app_test_root.joinpath(
                "support", *self._owner_parts(domain, context, object_name),
                "assistant_facets_typed_double.dart",
            )
            support.parent.mkdir(parents=True)
            support.write_text(
                "class ScenarioAssistantFacets implements AssistantFacets {}\n",
                encoding="utf-8",
            )
            journey = (
                app_test_root
                / "local_contract/journeys/assistant_creation_suggest"
            )
            journey.mkdir(parents=True)
            (journey / "assistant_creation_suggest__local_contract_test.dart").write_text(
                f"import '../../../support/{owner_path}/"
                "assistant_facets_typed_double.dart';\n"
                "void main() { final repository = ScenarioAssistantFacets(); }\n",
                encoding="utf-8",
            )

        self.assertEqual(self._verify_app(build), [])

    def test_commented_or_stringified_support_import_is_rejected(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner_path = "/".join(self._owner_parts(domain, context, object_name))
            support = app_test_root.joinpath(
                "support", *self._owner_parts(domain, context, object_name),
                "assistant_facets_typed_double.dart",
            )
            support.parent.mkdir(parents=True)
            support.write_text("class ScenarioAssistantFacets {}\n", encoding="utf-8")
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                f"// import '../../../support/{owner_path}/"
                "assistant_facets_typed_double.dart';\n"
                f"const fakeImport = \"import '../../../support/{owner_path}/"
                "assistant_facets_typed_double.dart';\";\n"
                "/* class _Fake implements Port {} */\n"
                "const fakeClass = 'class _Fake implements Port {}';\n"
                "void main() {}\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("typed double, Provider, or Widget", failures[0])

    def test_existing_relative_import_outside_test_support_is_rejected(self) -> None:
        def build(app_test_root: Path) -> None:
            helper = app_test_root.parent / "lib/testing/not_support.dart"
            helper.parent.mkdir(parents=True)
            helper.write_text("class NotSupportDouble {}\n", encoding="utf-8")
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                "import '../../../../lib/testing/not_support.dart';\n"
                "void main() { final value = NotSupportDouble(); }\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("typed double, Provider, or Widget", failures[0])

    def test_relative_import_escaping_test_support_is_rejected(self) -> None:
        def build(app_test_root: Path) -> None:
            outside = app_test_root.parents[1] / "outside.dart"
            outside.write_text("class EscapedDouble {}\n", encoding="utf-8")
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                "import '../../../../../outside.dart';\n"
                "void main() { final value = EscapedDouble(); }\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("typed double, Provider, or Widget", failures[0])

    def test_missing_relative_test_support_import_is_rejected(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner_path = "/".join(self._owner_parts(domain, context, object_name))
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                f"import '../../../support/{owner_path}/"
                "missing_double.dart';\n"
                "void main() { final value = MissingDouble(); }\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("does not resolve to a Dart typed double", failures[0])

    def test_local_journey_rejects_unreferenced_typed_double_import(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner_path = "/".join(self._owner_parts(domain, context, object_name))
            support = app_test_root.joinpath(
                "support",
                *self._owner_parts(domain, context, object_name),
                "typed_double.dart",
            )
            support.parent.mkdir(parents=True)
            support.write_text(
                "class ScenarioDouble implements ScenarioPort {}\n",
                encoding="utf-8",
            )
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                f"import '../../../support/{owner_path}/typed_double.dart';\n"
                "void main() {}\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("not referenced by executable test code", failures[0])

    def test_local_journey_rejects_support_without_typed_double_boundary(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner_path = "/".join(self._owner_parts(domain, context, object_name))
            support = app_test_root.joinpath(
                "support",
                *self._owner_parts(domain, context, object_name),
                "fixture.dart",
            )
            support.parent.mkdir(parents=True)
            support.write_text("class ScenarioFixture {}\n", encoding="utf-8")
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                f"import '../../../support/{owner_path}/fixture.dart';\n"
                "void main() { ScenarioFixture(); }\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("typed double, Provider, or Widget", failures[0])

    def test_local_journey_allows_plain_fixture_alongside_referenced_typed_boundary(
        self,
    ) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner_path = "/".join(self._owner_parts(domain, context, object_name))
            support = app_test_root.joinpath(
                "support", *self._owner_parts(domain, context, object_name)
            )
            support.mkdir(parents=True)
            (support / "fixture.dart").write_text(
                "const fixtureId = 'fixture';\n", encoding="utf-8"
            )
            (support / "typed_double.dart").write_text(
                "class ScenarioDouble implements ScenarioPort {}\n",
                encoding="utf-8",
            )
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                f"import '../../../support/{owner_path}/fixture.dart';\n"
                f"import '../../../support/{owner_path}/typed_double.dart';\n"
                "void main() { fixtureId; ScenarioDouble(); }\n",
                encoding="utf-8",
            )

        self.assertEqual(self._verify_app(build), [])

    def test_local_journey_finds_typed_boundary_declared_in_support_part(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner_path = "/".join(self._owner_parts(domain, context, object_name))
            support = app_test_root.joinpath(
                "support", *self._owner_parts(domain, context, object_name)
            )
            support.mkdir(parents=True)
            (support / "typed_double.dart").write_text(
                "part 'typed_double_impl.dart';\n", encoding="utf-8"
            )
            (support / "typed_double_impl.dart").write_text(
                "part of 'typed_double.dart';\n"
                "class ScenarioDouble implements ScenarioPort {}\n",
                encoding="utf-8",
            )
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                f"import '../../../support/{owner_path}/typed_double.dart';\n"
                "void main() { ScenarioDouble(); }\n",
                encoding="utf-8",
            )

        self.assertEqual(self._verify_app(build), [])

    def test_local_contract_journey_without_local_boundary_is_rejected(self) -> None:
        def build(app_test_root: Path) -> None:
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                "void main() {}\n", encoding="utf-8"
            )

        failures = self._verify_app(build)
        self.assertTrue(any("typed double, Provider, or Widget" in item for item in failures))

    def test_local_contract_python_journey_with_typed_double_is_accepted(self) -> None:
        def build(app_test_root: Path) -> None:
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.py").write_text(
                "class _PortDouble(Port):\n    pass\n\n"
                "def test_forward_share():\n    assert _PortDouble\n",
                encoding="utf-8",
            )

        self.assertEqual(self._verify_app(build), [])

    def test_python_journey_comment_or_string_class_is_not_execution(self) -> None:
        def build(app_test_root: Path) -> None:
            journey = app_test_root / "local_contract/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.py").write_text(
                "# class _PortDouble(Port): pass\n"
                "DECOY = 'class _PortDouble(Port): pass'\n"
                "def test_forward_share():\n    assert DECOY\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertTrue(
            any("typed double, Provider, or Widget" in item for item in failures),
            failures,
        )

    def test_api_integration_journeys_are_rejected(self) -> None:
        def build(app_test_root: Path) -> None:
            journey = app_test_root / "api_integration/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__api_integration_test.dart").write_text(
                "void main() {}\n", encoding="utf-8"
            )

        failures = self._verify_app(build)
        self.assertTrue(any("is not an allowed test directory" in item for item in failures))
        self.assertTrue(any("is forbidden" in item for item in failures))

    def test_user_acceptance_journey_rejects_wrong_facet_suffix(self) -> None:
        def build(app_test_root: Path) -> None:
            journey = app_test_root / "user_acceptance/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__local_contract_test.dart").write_text(
                "void main() {}\n", encoding="utf-8"
            )

        failures = self._verify_app(build)
        self.assertTrue(any("__user_acceptance_test.dart" in item for item in failures))

    def test_user_acceptance_journey_rejects_nested_directories(self) -> None:
        def build(app_test_root: Path) -> None:
            root = app_test_root / "user_acceptance/journeys"
            nested = root / "forward_share/nested"
            nested.mkdir(parents=True)
            (nested / "case__user_acceptance_test.dart").write_text(
                "void main() {}\n", encoding="utf-8"
            )

        failures = self._verify_app(build)
        self.assertTrue(any("journey tests must be direct" in item for item in failures))

    def test_user_acceptance_rejects_object_support_import(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner_parts = self._owner_parts(domain, context, object_name)
            owner_path = "/".join(owner_parts)
            support = app_test_root.joinpath(
                "support", *owner_parts, "typed_double.dart"
            )
            support.parent.mkdir(parents=True)
            support.write_text(
                "class ScenarioDouble implements ScenarioPort {}\n",
                encoding="utf-8",
            )
            test = app_test_root.joinpath(
                "user_acceptance",
                *owner_parts,
                "scenario__user_acceptance_test.dart",
            )
            test.parent.mkdir(parents=True)
            test.write_text(
                f"import '../../../../../support/{owner_path}/typed_double.dart';\n"
                "void main() { ScenarioDouble(); }\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("production Remote composition", failures[0])

    def test_user_acceptance_rejects_object_support_import_from_a_part(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner_path = "/".join(self._owner_parts(domain, context, object_name))
            support = app_test_root.joinpath(
                "support",
                *self._owner_parts(domain, context, object_name),
                "typed_double.dart",
            )
            support.parent.mkdir(parents=True)
            support.write_text(
                "class ScenarioDouble implements ScenarioPort {}\n",
                encoding="utf-8",
            )
            journey = app_test_root / "user_acceptance/journeys/forward_share"
            journey.mkdir(parents=True)
            (journey / "forward_share__user_acceptance_test.dart").write_text(
                "part 'forward_share_steps.dart';\nvoid main() {}\n",
                encoding="utf-8",
            )
            (journey / "forward_share_steps.dart").write_text(
                "part of 'forward_share__user_acceptance_test.dart';\n"
                f"import '../../../support/{owner_path}/typed_double.dart';\n",
                encoding="utf-8",
            )

        failures = self._verify_app(build)
        self.assertTrue(
            any("production Remote composition" in item for item in failures),
            failures,
        )

    def test_app_python_outside_root_local_contract_is_not_evidence(self) -> None:
        domain, context, object_name = sorted(self.objects)[0]

        def build(app_test_root: Path) -> None:
            owner_parts = self._owner_parts(domain, context, object_name)
            for layer in ("api_integration", "user_acceptance"):
                test = app_test_root.joinpath(
                    layer,
                    *owner_parts,
                    f"case__{layer}_test.py",
                )
                test.parent.mkdir(parents=True, exist_ok=True)
                test.write_text("def test_case():\n    assert True\n", encoding="utf-8")
            package_test = app_test_root.parent.joinpath(
                "packages/example/test/local_contract/case__local_contract_test.py"
            )
            package_test.parent.mkdir(parents=True)
            package_test.write_text("def test_case():\n    assert True\n", encoding="utf-8")

        failures = self._verify_app(build)
        self.assertEqual(len(failures), 3, failures)
        self.assertTrue(all("Python" in item for item in failures), failures)

    # -- App Python runner 单轨 -------------------------------------------

    def test_app_python_local_contract_runner_is_canonical_and_not_directly_duplicated(
        self,
    ) -> None:
        makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
        gate_repo = GATE_REPO_PATH.read_text(encoding="utf-8")

        self.assertEqual(
            makefile.count("test-app-python-local-contract: prepare-test-python"),
            1,
        )
        self.assertEqual(
            makefile.count("quwoquan_app/test/local_contract -q"),
            1,
        )
        self.assertEqual(
            makefile.count("$(MAKE) test-app-python-local-contract"),
            1,
        )
        self.assertEqual(gate_repo.count("make test-app-python-local-contract"), 1)
        self.assertNotIn(
            "quwoquan_app/test/local_contract/runtime/ios_runtime_dart_defines__local_contract_test.py",
            gate_repo,
        )
        self.assertNotIn(
            "quwoquan_app.test.local_contract.runtime.production_release_artifact__local_contract_test",
            gate_repo,
        )

    def test_app_python_canonical_evidence_is_root_local_contract_only(self) -> None:
        python_evidence = [
            path.relative_to(REPO_ROOT).as_posix()
            for component, path, _layer in self.verifier.iter_canonical_files()
            if component == "app" and path.suffix == ".py"
        ]
        self.assertTrue(python_evidence, "当前 App Python local_contract 前提为空")
        self.assertTrue(
            all(
                path.startswith("quwoquan_app/test/local_contract/")
                for path in python_evidence
            ),
            python_evidence,
        )
        self.assertTrue(
            all("/packages/" not in f"/{path}" for path in python_evidence),
            python_evidence,
        )

    def test_patrol_scope_discovers_canonical_uat_files_by_real_import(self) -> None:
        gate_repo = GATE_REPO_PATH.read_text(encoding="utf-8")

        self.assertIn("verify_test_directory_layout.py", gate_repo)
        self.assertIn("--list-patrol-user-acceptance-targets", gate_repo)
        self.assertIn('for target in "${patrol_targets[@]}"', gate_repo)
        self.assertIn('patrol_args+=(--target "$target")', gate_repo)
        self.assertIn('patrol test "${patrol_args[@]}"', gate_repo)
        self.assertNotIn("patrol test test/user_acceptance/patrol/", gate_repo)


if __name__ == "__main__":
    unittest.main()
