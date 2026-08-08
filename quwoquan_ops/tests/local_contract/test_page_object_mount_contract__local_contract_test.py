from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = (
    ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime"
    / "page"
    / "verify_page_object_contract.py"
)
PAGE_CONTRACT = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "page_object_contract.yaml"
)
SURFACES = PAGE_CONTRACT.with_name("ui_surfaces.yaml")


def load_verifier():
    scripts_dir = str(VERIFIER_PATH.parent)
    sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            "verify_page_object_contract_for_mount_test",
            VERIFIER_PATH,
        )
        if spec is None or spec.loader is None:
            raise AssertionError("cannot load page object verifier")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts_dir)


class PageObjectMountContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.subject = load_verifier()

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001
    def test_startup_recovery_is_a_strict_route_less_root_shell(self) -> None:
        document = yaml.safe_load(PAGE_CONTRACT.read_text(encoding="utf-8"))
        page = next(
            row
            for row in document["pages"]
            if row["page_id"] == "app.startup_recovery"
        )
        self.assertEqual("shell", page["page_kind"])
        for forbidden in (
            "parent_page_id",
            "additional_parent_page_ids",
            "route_id",
            "additional_route_ids",
            "route_registration_evidence",
        ):
            self.assertNotIn(forbidden, page)
        self.assertEqual("public", page["auth_requirement"])
        self.assertNotIn("inherit_from", page["telemetry_descriptor"])
        self.assertEqual(
            "page.app.startup_recovery",
            page["telemetry_descriptor"]["event_namespace"],
        )
        self.assertEqual(
            [
                "enter",
                "phase_change",
                "external_action",
                "runtime_reentry",
                "exit",
                "failure",
            ],
            page["telemetry_descriptor"]["lifecycle"],
        )
        self.assertTrue(
            self.subject._is_route_less_root_shell(
                kind=page["page_kind"],
                parent=page.get("parent_page_id"),
                own_route_ids=[],
                source=page["source_path"],
                experience_owner=page["experience_owner"],
            )
        )

        expected_mounts = {
            "lib/runtime/shell/recovery/bootstrap_recovery.dart",
            "lib/runtime/shell/recovery/runtime_recovery_host.dart",
            "lib/runtime/shell/composition/quwoquan_app_shell.dart",
            "lib/runtime/di/navigation/app_router_recovery_page.dart",
        }
        self.assertEqual(expected_mounts, set(page["mount_evidence"]))
        self.assertEqual(
            [],
            self.subject._root_shell_mount_errors(
                page["page_id"],
                entry_widget=page["entry_widget"],
                source=page["source_path"],
                evidence_paths=page["mount_evidence"],
            ),
        )

        surface_document = yaml.safe_load(SURFACES.read_text(encoding="utf-8"))
        surfaces = {row["id"]: row for row in surface_document["surfaces"]}
        self.assertEqual(
            [],
            self.subject._root_shell_surface_owner_errors(
                page["page_id"],
                surface_ids=page["surface_ids"],
                surfaces=surfaces,
                experience_owner=page["experience_owner"],
            ),
        )
        self.assertEqual("home", surfaces["appShell"]["route_id"])

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001
    def test_parent_or_route_never_qualifies_as_route_less_root_shell(self) -> None:
        self.assertFalse(
            self.subject._is_route_less_root_shell(
                kind="shell",
                parent="app.main_shell",
                own_route_ids=[],
                source="lib/runtime/shell/recovery/root_page.dart",
                experience_owner="app",
            )
        )
        self.assertFalse(
            self.subject._is_route_less_root_shell(
                kind="shell",
                parent=None,
                own_route_ids=["home"],
                source="lib/runtime/shell/recovery/root_page.dart",
                experience_owner="app",
            )
        )
        self.assertFalse(
            self.subject._is_route_less_root_shell(
                kind="embedded",
                parent=None,
                own_route_ids=[],
                source="lib/runtime/shell/recovery/root_page.dart",
                experience_owner="app",
            )
        )
        self.assertFalse(
            self.subject._is_route_less_root_shell(
                kind="shell",
                parent=None,
                own_route_ids=[],
                source="lib/service/content_service/content/post/presentation/fake_page.dart",
                experience_owner="content",
            )
        )

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001
    def test_parent_closure_is_direct_and_non_transitive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            lib = app / "lib"
            lib.mkdir()
            (lib / "parent.dart").write_text(
                "import 'direct.dart' if (dart.library.io) 'direct_io.dart';\n"
                "export 'only_exported.dart';\n"
                "part 'parent_part.dart';\n",
                encoding="utf-8",
            )
            (lib / "direct.dart").write_text(
                "import 'transitive.dart';\npart 'direct_part.dart';\n",
                encoding="utf-8",
            )
            (lib / "direct_io.dart").write_text(
                "part 'direct_io_part.dart';\n",
                encoding="utf-8",
            )
            (lib / "parent_part.dart").write_text(
                "part of 'parent.dart';\n",
                encoding="utf-8",
            )
            (lib / "direct_part.dart").write_text(
                "part of 'direct.dart';\n",
                encoding="utf-8",
            )
            (lib / "direct_io_part.dart").write_text(
                "part of 'direct_io.dart';\n",
                encoding="utf-8",
            )
            (lib / "transitive.dart").write_text("// transitive\n", encoding="utf-8")
            (lib / "only_exported.dart").write_text(
                "// export only\n",
                encoding="utf-8",
            )
            with mock.patch.object(self.subject, "APP", app):
                closure = self.subject._direct_app_dart_closure(
                    "lib/parent.dart"
                )
        self.assertEqual(
            {
                "lib/parent.dart",
                "lib/parent_part.dart",
                "lib/direct.dart",
                "lib/direct_part.dart",
                "lib/direct_io.dart",
                "lib/direct_io_part.dart",
            },
            closure,
        )
        self.assertNotIn("lib/transitive.dart", closure)
        self.assertNotIn("lib/only_exported.dart", closure)

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001
    def test_part_owner_must_be_exactly_one_real_library(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            lib = app / "lib"
            lib.mkdir()
            (lib / "part.dart").write_text(
                "part of 'owner.dart';\n",
                encoding="utf-8",
            )
            (lib / "owner.dart").write_text(
                "part 'part.dart';\n",
                encoding="utf-8",
            )
            (lib / "another_part.dart").write_text(
                "part of 'owner.dart';\npart 'part.dart';\n",
                encoding="utf-8",
            )
            with mock.patch.object(self.subject, "APP", app):
                self.assertEqual(
                    "lib/owner.dart",
                    self.subject._dart_library_owner("lib/part.dart"),
                )
                (lib / "second_owner.dart").write_text(
                    "part 'part.dart';\n",
                    encoding="utf-8",
                )
                self.assertIsNone(
                    self.subject._dart_library_owner("lib/part.dart")
                )
                (lib / "second_owner.dart").unlink()
                (lib / "owner.dart").unlink()
                self.assertIsNone(
                    self.subject._dart_library_owner("lib/part.dart")
                )

        actual_owner = self.subject._dart_library_owner(
            "lib/runtime/di/navigation/app_router_recovery_page.dart"
        )
        self.assertEqual("lib/runtime/di/navigation/app_router.dart", actual_owner)

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001
    def test_each_parent_needs_evidence_and_extraneous_evidence_is_rejected(self) -> None:
        closures = {
            "parent.one": {"lib/one.dart", "lib/one_part.dart"},
            "parent.two": {"lib/two.dart", "lib/two_direct.dart"},
        }
        self.assertEqual(
            [],
            self.subject._parent_mount_evidence_errors(
                "child",
                parent_closures=closures,
                evidence_paths=["lib/one_part.dart", "lib/two_direct.dart"],
            ),
        )
        missing_parent = self.subject._parent_mount_evidence_errors(
            "child",
            parent_closures=closures,
            evidence_paths=["lib/one_part.dart"],
        )
        self.assertTrue(any("parent.two" in error for error in missing_parent))
        extraneous = self.subject._parent_mount_evidence_errors(
            "child",
            parent_closures=closures,
            evidence_paths=[
                "lib/one_part.dart",
                "lib/two_direct.dart",
                "lib/transitive.dart",
            ],
        )
        self.assertTrue(any("lib/transitive.dart" in error for error in extraneous))

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001
    def test_parent_route_registration_may_inject_a_direct_typed_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            lib = app / "lib"
            lib.mkdir()
            (lib / "parent.dart").write_text(
                "class ParentPage {}\n",
                encoding="utf-8",
            )
            (lib / "router.dart").write_text(
                "import 'slot.dart';\n",
                encoding="utf-8",
            )
            (lib / "slot.dart").write_text(
                "import 'transitive.dart';\nChildPage buildChild() => ChildPage();\n",
                encoding="utf-8",
            )
            (lib / "transitive.dart").write_text(
                "class TransitiveHelper {}\n",
                encoding="utf-8",
            )
            pages = {
                "parent": {
                    "source_path": "lib/parent.dart",
                    "route_registration_evidence": ["lib/router.dart"],
                }
            }
            with mock.patch.object(self.subject, "APP", app):
                closures = self.subject._declared_parent_mount_closures(
                    {"parent_page_id": "parent"},
                    pages,
                )
            self.assertIn("lib/router.dart", closures["parent"])
            self.assertIn("lib/slot.dart", closures["parent"])
            self.assertNotIn("lib/transitive.dart", closures["parent"])
            self.assertEqual(
                [],
                self.subject._parent_mount_evidence_errors(
                    "child",
                    parent_closures=closures,
                    evidence_paths=["lib/slot.dart"],
                ),
            )

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001
    def test_mount_token_is_checked_per_evidence_file(self) -> None:
        self.assertTrue(self.subject._mounts_entry_widget("const Target();", "Target"))
        self.assertTrue(
            self.subject._mounts_entry_widget("Target.create();", "Target")
        )
        self.assertTrue(
            self.subject._mounts_entry_widget("class Child extends Target {}", "Target")
        )
        self.assertFalse(
            self.subject._mounts_entry_widget("// Target is only mentioned", "Target")
        )

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001
    def test_root_mounts_must_equal_all_direct_constructor_sites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            lib = app / "lib"
            lib.mkdir()
            (lib / "root_page.dart").write_text(
                "class RootPage {}\n",
                encoding="utf-8",
            )
            (lib / "a.dart").write_text(
                "import 'root_page.dart';\nconst RootPage();\n",
                encoding="utf-8",
            )
            (lib / "b.dart").write_text(
                "import 'root_page.dart';\nRootPage.named();\n",
                encoding="utf-8",
            )
            (lib / "host.dart").write_text(
                "import 'root_page.dart';\npart 'host_part.dart';\n",
                encoding="utf-8",
            )
            (lib / "host_part.dart").write_text(
                "part of 'host.dart';\nRootPage();\n",
                encoding="utf-8",
            )
            (lib / "comment.dart").write_text(
                "import 'root_page.dart';\n// RootPage();\n"
                "const marker = 'RootPage()';\n",
                encoding="utf-8",
            )
            (lib / "unbound.dart").write_text(
                "RootPage(); // no import, not a valid consumer library\n",
                encoding="utf-8",
            )
            (lib / "extra.dart").write_text(
                "import 'root_page.dart';\n// no constructor\n",
                encoding="utf-8",
            )
            with mock.patch.object(self.subject, "APP", app):
                self.assertEqual(
                    [],
                    self.subject._root_shell_mount_errors(
                        "root",
                        entry_widget="RootPage",
                        source="lib/root_page.dart",
                        evidence_paths=[
                            "lib/a.dart",
                            "lib/b.dart",
                            "lib/host_part.dart",
                        ],
                    ),
                )
                missing = self.subject._root_shell_mount_errors(
                    "root",
                    entry_widget="RootPage",
                    source="lib/root_page.dart",
                    evidence_paths=["lib/a.dart"],
                )
                extra = self.subject._root_shell_mount_errors(
                    "root",
                    entry_widget="RootPage",
                    source="lib/root_page.dart",
                    evidence_paths=[
                        "lib/a.dart",
                        "lib/b.dart",
                        "lib/host_part.dart",
                        "lib/extra.dart",
                    ],
                )
        self.assertTrue(any("lib/b.dart" in error for error in missing))
        self.assertTrue(any("lib/extra.dart" in error for error in extra))

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001
    def test_root_surface_owner_mismatch_is_blocked(self) -> None:
        errors = self.subject._root_shell_surface_owner_errors(
            "root",
            surface_ids=["wrong"],
            surfaces={"wrong": {"owner": "content", "route_id": "home"}},
            experience_owner="app",
        )
        self.assertEqual(1, len(errors))
        self.assertIn("owner", errors[0])

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md#gwt-001
    def test_only_a_valid_root_shell_may_skip_surface_route_membership(self) -> None:
        self.assertIsNone(
            self.subject._surface_route_membership_error(
                "root",
                surface_id="appShell",
                surface_route="home",
                effective_routes=set(),
                is_route_less_root_shell=True,
            )
        )
        error = self.subject._surface_route_membership_error(
            "business.fake",
            surface_id="appShell",
            surface_route="home",
            effective_routes=set(),
            is_route_less_root_shell=False,
        )
        self.assertIsNotNone(error)
        self.assertIn("home", error)

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md#gwt-001
    def test_live_disk_page_without_contract_owner_is_rejected(self) -> None:
        errors = self.subject._page_source_ownership_errors(
            disk_paths={"lib/service/example/presentation/orphan_page.dart"},
            source_owner_ids={},
        )

        self.assertEqual(1, len(errors))
        self.assertIn("磁盘页面未登记 canonical contract", errors[0])

    # spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md#gwt-001
    def test_duplicate_contract_source_owner_is_rejected(self) -> None:
        source = "lib/service/example/presentation/shared_page.dart"
        errors = self.subject._page_source_ownership_errors(
            disk_paths={source},
            source_owner_ids={source: ["example.first", "example.second"]},
        )

        self.assertEqual(1, len(errors))
        self.assertIn("source_path 重复", errors[0])
        self.assertIn("example.first", errors[0])
        self.assertIn("example.second", errors[0])


if __name__ == "__main__":
    unittest.main()
