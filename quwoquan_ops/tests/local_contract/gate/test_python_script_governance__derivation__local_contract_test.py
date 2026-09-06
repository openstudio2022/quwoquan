# spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-004
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.gate.python_script_governance.inventory import ripgrep_files
from quwoquan_ops.gate.verify_entrypoint_script_paths import (
    entrypoint_script_path_issues,
)
from quwoquan_ops.gate.verify_python_script_governance import (
    derive_report,
    main as governance_main,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


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

    def test_delivery_gate_routes_python_governance_to_its_requested_scope(
        self,
    ) -> None:
        gate = (
            REPOSITORY_ROOT / "quwoquan_ops/gate/gate_repo.sh"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "verify_python_script_governance.py --scope all --mode check",
            gate,
        )
        self.assertIn('service) python_script_scope="service"', gate)
        self.assertIn('app|patrol) python_script_scope="app"', gate)
        self.assertIn('portal|ops-portal) python_script_scope="ops"', gate)
        self.assertIn('data) python_script_scope="data"', gate)
        self.assertIn('--scope "$python_script_scope" --mode check', gate)

    def test_file_enumeration_falls_back_without_ripgrep(self) -> None:
        visible = self._write("quwoquan_app/scripts/runtime/visible.py")
        hidden = self._write("quwoquan_app/.hidden/visible.py")
        self._write("quwoquan_app/.qwq_output/ignored.py")
        self._write("quwoquan_app/scripts/runtime/ignored.txt")

        with patch(
            "quwoquan_ops.gate.python_script_governance.inventory.shutil.which",
            return_value=None,
        ):
            files = ripgrep_files(
                self.root / "quwoquan_app",
                include_globs=("*.py",),
                no_ignore=True,
            )

        self.assertEqual([hidden, visible], files)

    def test_file_enumeration_fallback_matches_root_level_double_star_glob(
        self,
    ) -> None:
        cache = self._write("quwoquan_app/.ruff_cache/state.py")

        with patch(
            "quwoquan_ops.gate.python_script_governance.inventory.shutil.which",
            return_value=None,
        ):
            files = ripgrep_files(
                self.root / "quwoquan_app",
                include_globs=("**/.ruff_cache/**",),
                no_ignore=True,
            )

        self.assertEqual([cache], files)

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

    def test_app_forbids_service_wrapper_and_cloud_layout_copies(
        self,
    ) -> None:
        self._write(
            "quwoquan_app/lib/service/content_service/content/post/presentation/page.dart"
        )
        self._write(
            "quwoquan_app/scripts/service/content_service/content/post/"
            "verify_post_contract.py"
        )
        self._write(
            "quwoquan_app/scripts/content_service/config/schema.yaml",
            "schema: forbidden\n",
        )
        self._write(
            "quwoquan_app/scripts/content_service/environments/gamma/run_bad.py",
            "def main() -> None:\n    pass\n",
        )

        report = derive_report(self.root, ("app",))
        codes = self._issue_codes(report)
        self.assertIn("APP.SERVICE_WRAPPER_FORBIDDEN", codes)
        self.assertIn("APP.CLOUD_LAYOUT_COPY_FORBIDDEN", codes)

    def test_service_verify_single_owner_emits_warning_not_issue(
        self,
    ) -> None:
        self._write(
            "quwoquan_service/services/content-service/internal/content/post/domain/post.go"
        )
        self._write(
            "quwoquan_service/scripts/verify/verify_content_only_boundaries.py",
            (
                "from pathlib import Path\n"
                "ROOT = Path(__file__).resolve().parents[2]\n"
                'SCAN = ROOT / "services" / "content-service" / "internal"\n'
            ),
        )
        self._write(
            "quwoquan_service/scripts/verify/verify_multi_service_scan.py",
            (
                "from pathlib import Path\n"
                "SERVICES_ROOT = Path('services')\n"
                "for path in SERVICES_ROOT.iterdir():\n"
                "    pass\n"
            ),
        )

        report = derive_report(self.root, ("service",))
        warning_codes = {
            str(warning["code"])
            for warning in report.get("warnings", [])  # type: ignore[union-attr]
        }
        self.assertIn("SERVICE.VERIFY_SINGLE_SERVICE_OWNER", warning_codes)
        self.assertNotIn(
            "SERVICE.VERIFY_SINGLE_SERVICE_OWNER",
            self._issue_codes(report),
        )

    def test_service_runtime_requires_known_concern_directory(self) -> None:
        self._write(
            "quwoquan_service/scripts/runtime/verify_flat_runtime.py",
            "def main() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_service/scripts/runtime/unknown/verify_unknown.py",
            "def main() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_service/scripts/runtime/packaging/verify_ok.py",
            "def main() -> None:\n    pass\n",
        )

        report = derive_report(self.root, ("service",))
        codes = self._issue_codes(report)
        self.assertIn("SERVICE.RUNTIME_FLAT_SCRIPT", codes)
        self.assertIn("SERVICE.RUNTIME_CONCERN_UNKNOWN", codes)
        self.assertFalse(
            any(
                issue["code"] in {
                    "SERVICE.RUNTIME_FLAT_SCRIPT",
                    "SERVICE.RUNTIME_CONCERN_UNKNOWN",
                }
                and "packaging/verify_ok.py" in issue["path"]
                for issue in report["issues"]  # type: ignore[index]
            )
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

    def test_render_and_collect_names_are_generators_without_hiding_orphans(
        self,
    ) -> None:
        render = self._write(
            "quwoquan_ops/ci/render_provider_release_evidence.py",
            "def render() -> None:\n    pass\n",
        )
        collect = self._write(
            "quwoquan_ops/cli/prod/collect_mainline_image_descriptors.py",
            "def collect() -> None:\n    pass\n",
        )
        orphan = self._write(
            "quwoquan_ops/ci/render_detached_release_evidence.py",
            "def render() -> None:\n    pass\n",
        )
        importer = self._write(
            "quwoquan_ops/ci/verify_generator_consumers.py",
            "from quwoquan_ops.ci import render_provider_release_evidence\n"
            "from quwoquan_ops.cli.prod import collect_mainline_image_descriptors\n",
        )

        report = derive_report(self.root, ("ops",))
        records = {
            record["path"]: record  # type: ignore[index]
            for record in report["scripts"]  # type: ignore[index]
        }

        for path in (render, collect):
            record = records[str(path.relative_to(self.root))]
            self.assertEqual("generator", record["role"])
            self.assertIn(
                str(importer.relative_to(self.root)),
                record["importedBy"],
            )
            self.assertFalse(record["orphanCandidate"])

        orphan_record = records[str(orphan.relative_to(self.root))]
        self.assertEqual("generator", orphan_record["role"])
        self.assertEqual((), orphan_record["referencedBy"])
        self.assertEqual((), orphan_record["importedBy"])
        self.assertTrue(orphan_record["orphanCandidate"])
        self.assertNotIn("SCRIPT.ROLE_UNCLASSIFIED", self._issue_codes(report))

    def test_explicit_lib_path_is_library_without_managed_importer(self) -> None:
        self._write(
            "quwoquan_service/scripts/runtime/packaging/lib/image_inputs.py",
            "VALUE = 1\n",
        )

        report = derive_report(self.root, ("service",))
        records = {
            record["path"]: record  # type: ignore[index]
            for record in report["scripts"]  # type: ignore[index]
        }
        library = records[
            "quwoquan_service/scripts/runtime/packaging/lib/image_inputs.py"
        ]
        self.assertEqual("lib", library["role"])
        self.assertFalse(library["orphanCandidate"])

    def test_repository_root_bootstrap_derives_library_role(self) -> None:
        bootstrap = self._write(
            "quwoquan_service/scripts/verify/repository_root.py",
            "def repository_root() -> str:\n    return 'repo'\n",
        )

        report = derive_report(self.root, ("service",))
        records = {
            record["path"]: record  # type: ignore[index]
            for record in report["scripts"]  # type: ignore[index]
        }
        record = records[str(bootstrap.relative_to(self.root))]

        self.assertEqual("lib", record["role"])
        self.assertFalse(record["orphanCandidate"])

    def test_all_python_files_receive_one_derived_boundary(self) -> None:
        self._write(
            "quwoquan_app/scripts/runtime/auth/verify_auth.py",
            "def main() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_app/test/local_contract/runtime/auth_contract_test.py",
            "def test_auth() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_app/test/support/harness.py",
            "VALUE = 1\n",
        )
        unknown = self._write(
            "quwoquan_app/misc/detached.py",
            "VALUE = 1\n",
        )
        self._write(
            "quwoquan_service/services/content-service/internal/content/post/"
            "application/projection.py",
            "VALUE = 1\n",
        )
        self._write(
            "quwoquan_service/services/content-service/generated/client.py",
            "VALUE = 1\n",
        )
        self._write(
            "quwoquan_service/services/content-service/tests/local_contract/"
            "content/post/test_projection.py",
            "def test_projection() -> None:\n    pass\n",
        )

        report = derive_report(self.root, ("app", "service"))
        python_files = report["pythonFiles"]  # type: ignore[index]
        boundaries = {
            str(record["path"]): str(record["boundary"])
            for record in python_files
        }

        self.assertEqual(7, report["summary"]["pythonFileCount"])  # type: ignore[index]
        self.assertEqual(len(python_files), len(boundaries))
        self.assertEqual(
            "managed_script",
            boundaries["quwoquan_app/scripts/runtime/auth/verify_auth.py"],
        )
        self.assertEqual(
            "test_evidence",
            boundaries[
                "quwoquan_app/test/local_contract/runtime/auth_contract_test.py"
            ],
        )
        self.assertEqual(
            "test_support",
            boundaries["quwoquan_app/test/support/harness.py"],
        )
        self.assertEqual(
            "production_module",
            boundaries[
                "quwoquan_service/services/content-service/internal/content/post/"
                "application/projection.py"
            ],
        )
        self.assertEqual(
            "generated",
            boundaries[
                "quwoquan_service/services/content-service/generated/client.py"
            ],
        )
        self.assertEqual("unknown", boundaries[str(unknown.relative_to(self.root))])
        self.assertIn("PYTHON.BOUNDARY_UNKNOWN", self._issue_codes(report))

    def test_ignored_python_file_cannot_escape_governance_boundary(self) -> None:
        self._write(".git/config", "[core]\nrepositoryformatversion = 0\n")
        self._write(".gitignore", "quwoquan_app/misc/\n")
        ignored = self._write(
            "quwoquan_app/misc/ignored_detached.py",
            "VALUE = 1\n",
        )

        report = derive_report(self.root, ("app",))
        boundaries = {
            str(record["path"]): str(record["boundary"])
            for record in report["pythonFiles"]  # type: ignore[index]
        }

        self.assertEqual(
            "unknown",
            boundaries[str(ignored.relative_to(self.root))],
        )
        self.assertIn("PYTHON.BOUNDARY_UNKNOWN", self._issue_codes(report))

    def test_source_cache_temp_names_and_unowned_tools_are_blocked(self) -> None:
        tool = self._write(
            "quwoquan_app/scripts/tools/device/orphan_probe.py",
            "def inspect() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_app/.ruff_cache/state.py",
            "VALUE = 1\n",
        )
        self._write(
            "quwoquan_app/scripts/tools/device/temp_probe.py",
            "def main() -> None:\n    pass\n",
        )

        report = derive_report(self.root, ("app",))
        codes = self._issue_codes(report)
        self.assertIn("PYTHON.SOURCE_CACHE_FORBIDDEN", codes)
        self.assertIn("PYTHON.TEMP_SCRIPT_NAME", codes)
        self.assertIn("SCRIPT.TOOL_OWNER_MISSING", codes)

        self._write(
            "quwoquan_app/scripts/README.md",
            f"- tools/device/{tool.name}: device owner evidence\n",
        )
        governed = derive_report(self.root, ("app",))
        self.assertFalse(
            any(
                issue["code"] == "SCRIPT.TOOL_OWNER_MISSING"
                and issue["path"] == str(tool.relative_to(self.root))
                for issue in governed["issues"]  # type: ignore[index]
            )
        )

    def test_embedded_python_import_in_shell_is_a_live_library_edge(self) -> None:
        library = self._write(
            "quwoquan_service/scripts/runtime/packaging/lib/image_inputs.py",
            "VALUE = 1\n",
        )
        shell = self._write(
            "quwoquan_service/scripts/runtime/packaging/build_package.sh",
            "python3 - <<'PY'\n"
            "from quwoquan_service.scripts.runtime.packaging.lib.image_inputs "
            "import VALUE\n"
            "print(VALUE)\n"
            "PY\n",
        )

        report = derive_report(self.root, ("service",))
        records = {
            record["path"]: record  # type: ignore[index]
            for record in report["scripts"]  # type: ignore[index]
        }
        self.assertIn(
            str(shell.relative_to(self.root)),
            records[str(library.relative_to(self.root))]["importedBy"],
        )

    def test_service_makefile_relative_scripts_and_ops_cross_scope_refs(
        self,
    ) -> None:
        self._write(
            "quwoquan_service/scripts/codegen/gen_redis_router_config.py",
            "def main() -> None:\n    pass\n",
        )
        self._write(
            "quwoquan_service/scripts/verify/structure/verify_go_single_module.py",
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
            "\tpython3 scripts/verify/structure/verify_go_single_module.py\n",
        )
        self._write(
            "quwoquan_ops/gate/gate_runtime_media.sh",
            "python3 quwoquan_service/scripts/content-service/"
            "verify_media_variant_registry_metadata.py\n",
        )
        self._write(
            "quwoquan_ops/gate/gate_repo.sh",
            "python3 quwoquan_service/scripts/verify/structure/verify_go_single_module.py\n",
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
            "quwoquan_service/scripts/verify/structure/verify_go_single_module.py"
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
            "quwoquan_data/scripts/content/execution/planning/__init__.py"
        )
        self._write(
            "quwoquan_data/scripts/content/execution/planning/selection_inputs.py",
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
            "quwoquan_data/scripts/content/execution/planning/selection_inputs.py"
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

    def test_entrypoint_scan_rejects_stale_app_test_script_paths(self) -> None:
        self._write(
            "quwoquan_app/test/local_contract/runtime/script_path_test.dart",
            "final source = _readAppFile("
            "'scripts/device/removed_startup_probe.py');\n",
        )

        issues = entrypoint_script_path_issues(self.root)

        self.assertTrue(
            any(
                "script_path_test.dart:1" in issue
                and "removed_startup_probe.py" in issue
                for issue in issues
            ),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
