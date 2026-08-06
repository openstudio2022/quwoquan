# spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-004
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.gate.verify_entrypoint_script_paths import (
    entrypoint_script_path_issues,
)
from quwoquan_ops.gate.verify_python_script_governance import (
    derive_report,
    main as governance_main,
)


class PythonScriptGovernanceDerivationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _write(self, relative: str, text: str = "") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    @staticmethod
    def _issue_codes(report: dict[str, object]) -> set[str]:
        return {
            str(issue["code"])
            for issue in report["issues"]  # type: ignore[index]
        }

    def test_app_paths_derive_service_object_and_reject_flat_or_milestone_names(
        self,
    ) -> None:
        self._write(
            "quwoquan_app/lib/service/content_service/post/post/presentation/page.dart"
        )
        self._write(
            "quwoquan_app/scripts/content_service/post/post/verify_post_contract.py"
        )
        self._write("quwoquan_app/scripts/content/verify_post_contract.py")
        self._write("quwoquan_app/scripts/runtime/verify_runtime_contract.py")
        self._write(
            "quwoquan_app/scripts/content_service/post/ghost/verify_ghost_contract.py"
        )
        milestone = "t" + "3"
        self._write(f"quwoquan_app/scripts/gamma/run_local_gamma_{milestone}.py")

        report = derive_report(self.root, ("app",))

        self.assertEqual(
            {
                "APP.OBJECT_OWNER_MISSING",
                "APP.RUNTIME_FLAT_SCRIPT",
                "APP.SCRIPT_ROOT_UNSUPPORTED",
                "SCRIPT.MILESTONE_NAME",
            },
            self._issue_codes(report),
        )

    def test_service_paths_derive_kebab_service_owner_and_split_contract_verify(
        self,
    ) -> None:
        self._write(
            "quwoquan_service/services/content-service/internal/content/post/domain/post.go"
        )
        self._write(
            "quwoquan_service/scripts/content-service/content/post/verify_post_contract.py"
        )
        self._write("quwoquan_service/scripts/contracts/verify_contract.py")
        self._write("quwoquan_service/scripts/recommendation/policy_advisor.py")

        report = derive_report(self.root, ("service",))

        self.assertEqual(
            {
                "SCRIPT.ROLE_UNCLASSIFIED",
                "SERVICE.CONTRACTS_VERIFY_MIXED",
                "SERVICE.SCRIPT_ROOT_UNSUPPORTED",
            },
            self._issue_codes(report),
        )

    def test_roles_keep_acceptance_runner_generator_and_imported_lib_distinct(
        self,
    ) -> None:
        self._write(
            "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
            "content-service/smoke/run_feed_probe.py"
        )
        self._write(
            "quwoquan_app/scripts/tools/generate_icons.py",
            "def main() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_app/scripts/tools/helper.py",
            "VALUE = 1\n",
        )
        self._write(
            "quwoquan_app/scripts/tools/run_job.py",
            "from helper import VALUE\n\nprint(VALUE)\n",
        )
        self._write(
            "Makefile",
            "icons:\n\tpython3 quwoquan_app/scripts/tools/generate_icons.py\n",
        )

        report = derive_report(self.root, ("app", "ops"))
        records = {
            record["path"]: record  # type: ignore[index]
            for record in report["scripts"]  # type: ignore[index]
        }

        acceptance = records[
            "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
            "content-service/smoke/run_feed_probe.py"
        ]
        self.assertEqual("runner", acceptance["role"])
        self.assertFalse(acceptance["orphanCandidate"])

        generator = records["quwoquan_app/scripts/tools/generate_icons.py"]
        self.assertEqual("generator", generator["role"])
        self.assertFalse(generator["orphanCandidate"])

        helper = records["quwoquan_app/scripts/tools/helper.py"]
        self.assertEqual("lib", helper["role"])
        self.assertFalse(helper["orphanCandidate"])

    def test_service_makefile_relative_scripts_and_ops_cross_scope_refs(
        self,
    ) -> None:
        self._write(
            "quwoquan_service/scripts/codegen/gen_redis_router_config.py",
            "def main() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_service/scripts/verify/verify_go_single_module.py",
            "def main() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_service/scripts/content-service/"
            "verify_media_variant_registry_metadata.py",
            "def main() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_service/scripts/search-service/run_search_orphan.py",
            "def main() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_service/Makefile",
            "verify-redis-routes:\n"
            "\tpython3 scripts/codegen/gen_redis_router_config.py --check\n"
            "verify-go-single-module:\n"
            "\tpython3 scripts/verify/verify_go_single_module.py\n",
        )
        self._write(
            "quwoquan_ops/gate/gate_runtime_media.sh",
            "python3 quwoquan_service/scripts/content-service/"
            "verify_media_variant_registry_metadata.py\n",
        )
        self._write(
            "quwoquan_ops/gate/gate_repo.sh",
            "python3 quwoquan_service/scripts/verify/verify_go_single_module.py\n",
        )

        report = derive_report(self.root, ("service", "ops"))
        records = {
            record["path"]: record  # type: ignore[index]
            for record in report["scripts"]  # type: ignore[index]
        }

        redis = records[
            "quwoquan_service/scripts/codegen/gen_redis_router_config.py"
        ]
        self.assertEqual("generator", redis["role"])
        self.assertIn(
            "quwoquan_service/Makefile",
            redis["referencedBy"],
        )
        self.assertFalse(redis["orphanCandidate"])

        go_single = records[
            "quwoquan_service/scripts/verify/verify_go_single_module.py"
        ]
        self.assertIn("quwoquan_service/Makefile", go_single["referencedBy"])
        self.assertIn(
            "quwoquan_ops/gate/gate_repo.sh",
            go_single["referencedBy"],
        )
        self.assertFalse(go_single["orphanCandidate"])

        media = records[
            "quwoquan_service/scripts/content-service/"
            "verify_media_variant_registry_metadata.py"
        ]
        self.assertIn(
            "quwoquan_ops/gate/gate_runtime_media.sh",
            media["referencedBy"],
        )
        self.assertFalse(media["orphanCandidate"])

        orphan = records[
            "quwoquan_service/scripts/search-service/run_search_orphan.py"
        ]
        self.assertEqual("runner", orphan["role"])
        self.assertTrue(orphan["orphanCandidate"])

    def test_workflow_relative_and_segmented_stackctl_paths_are_live_edges(
        self,
    ) -> None:
        workflow_runner = self._write(
            "quwoquan_app/scripts/device/run_workflow_probe.py",
            "def main() -> None:\n    pass\n",
        )
        stackctl_runner = self._write(
            "quwoquan_app/scripts/gamma/run_segmented_probe.py",
            "def main() -> None:\n    pass\n",
        )
        self._write(
            ".github/workflows/app-probes.yml",
            "steps:\n"
            "  - run: python3 scripts/device/run_workflow_probe.py\n",
        )
        self._write(
            "quwoquan_ops/cli/stackctl.py",
            'runner = ROOT / "quwoquan_app" / "scripts" / "gamma" '
            '/ "run_segmented_probe.py"\n',
        )

        report = derive_report(self.root, ("app", "ops"))
        records = {
            record["path"]: record  # type: ignore[index]
            for record in report["scripts"]  # type: ignore[index]
        }

        workflow = records[str(workflow_runner.relative_to(self.root))]
        self.assertIn(
            ".github/workflows/app-probes.yml",
            workflow["referencedBy"],
        )
        self.assertFalse(workflow["orphanCandidate"])

        stackctl = records[str(stackctl_runner.relative_to(self.root))]
        self.assertIn("quwoquan_ops/cli/stackctl.py", stackctl["referencedBy"])
        self.assertFalse(stackctl["orphanCandidate"])

    def test_data_package_modules_derive_lib_without_fake_import_edges(
        self,
    ) -> None:
        self._write("quwoquan_data/scripts/__init__.py")
        self._write("quwoquan_data/scripts/content/__init__.py")
        self._write("quwoquan_data/scripts/content/execution/__init__.py")
        self._write(
            "quwoquan_data/scripts/content/execution/selection_inputs.py",
            "def select() -> tuple[object, ...]:\n    return ()\n",
        )
        self._write(
            "quwoquan_data/scripts/content/review/quality/dirty_data.py",
            "def inspect() -> tuple[object, ...]:\n    return ()\n",
        )
        self._write(
            "quwoquan_data/scripts/content/execution/detached_task.py",
            "def main() -> None:\n"
            "    pass\n\n"
            'if __name__ == "__main__":\n'
            "    main()\n",
        )
        self._write(
            "quwoquan_data/scripts/content/execution/run_orphan_campaign.py",
            "def main() -> None:\n    pass\n",
        )
        self._write("quwoquan_data/scripts/content/tools/__init__.py")
        self._write(
            "quwoquan_data/scripts/content/tools/orphan_probe.py",
            "def inspect() -> None:\n    pass\n",
        )

        report = derive_report(self.root, ("data",))
        records = {
            record["path"]: record  # type: ignore[index]
            for record in report["scripts"]  # type: ignore[index]
        }

        library = records[
            "quwoquan_data/scripts/content/execution/selection_inputs.py"
        ]
        self.assertEqual("lib", library["role"])
        self.assertEqual((), library["importedBy"])
        self.assertEqual((), library["referencedBy"])
        self.assertFalse(library["orphanCandidate"])

        namespace_library = records[
            "quwoquan_data/scripts/content/review/quality/dirty_data.py"
        ]
        self.assertEqual("lib", namespace_library["role"])
        self.assertEqual((), namespace_library["importedBy"])

        detached = records[
            "quwoquan_data/scripts/content/execution/detached_task.py"
        ]
        self.assertEqual("unclassified", detached["role"])
        self.assertTrue(detached["orphanCandidate"])

        runner = records[
            "quwoquan_data/scripts/content/execution/run_orphan_campaign.py"
        ]
        self.assertEqual("runner", runner["role"])
        self.assertTrue(runner["orphanCandidate"])

        tool = records["quwoquan_data/scripts/content/tools/orphan_probe.py"]
        self.assertEqual("tool", tool["role"])
        self.assertNotEqual("lib", tool["role"])

    def test_report_mode_is_byte_idempotent_and_orphans_remain_advisory(
        self,
    ) -> None:
        self._write("quwoquan_app/scripts/tools/verify_unused_contract.py")
        first = self.root / "first.json"
        second = self.root / "second.json"

        self.assertEqual(
            0,
            governance_main(
                [
                    "--repo-root",
                    str(self.root),
                    "--scope",
                    "app",
                    "--mode",
                    "report",
                    "--output",
                    str(first),
                ]
            ),
        )
        self.assertEqual(
            0,
            governance_main(
                [
                    "--repo-root",
                    str(self.root),
                    "--scope",
                    "app",
                    "--mode",
                    "report",
                    "--output",
                    str(second),
                ]
            ),
        )

        self.assertEqual(first.read_bytes(), second.read_bytes())
        report = derive_report(self.root, ("app",))
        self.assertEqual(1, report["summary"]["orphanCandidateCount"])  # type: ignore[index]
        self.assertNotIn(
            "SCRIPT.ORPHAN",
            self._issue_codes(report),
        )

        all_first = self.root / "all_first.json"
        all_second = self.root / "all_second.json"
        for output in (all_first, all_second):
            self.assertEqual(
                0,
                governance_main(
                    [
                        "--repo-root",
                        str(self.root),
                        "--scope",
                        "all",
                        "--mode",
                        "report",
                        "--output",
                        str(output),
                    ]
                ),
            )
        self.assertEqual(all_first.read_bytes(), all_second.read_bytes())

    def test_entrypoint_scan_includes_stackctl_and_reports_missing_script(
        self,
    ) -> None:
        self._write(
            "quwoquan_ops/cli/stackctl.py",
            'SCRIPT = "quwoquan_service/scripts/runtime/missing.py"\n',
        )
        self._write(
            "quwoquan_service/Makefile",
            "bad:\n\tpython3 scripts/verify/missing_relative.py\n",
        )
        self._write(
            "quwoquan_service/scripts/verify/help_points_missing.py",
            '"""python3 scripts/verify/also_missing.py"""\n',
        )

        issues = entrypoint_script_path_issues(self.root)

        self.assertTrue(any("stackctl.py:1" in issue for issue in issues))
        self.assertTrue(
            any(
                "quwoquan_service/Makefile:" in issue
                and "missing_relative.py" in issue
                for issue in issues
            )
        )
        self.assertTrue(
            any(
                "help_points_missing.py:" in issue and "also_missing.py" in issue
                for issue in issues
            )
        )


if __name__ == "__main__":
    unittest.main()
