"""垂类架构防回退门的永久零缺口正负例与 canonical wiring。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_vertical_architecture_ratchet.py"
VERIFIER_PACKAGE_PATH = ROOT / "quwoquan_ops/gate/vertical_architecture_ratchet"
BASELINE_PATH = (
    ROOT
    / "quwoquan_ops/policies/gates/vertical_architecture_ratchet_baseline.yaml"
)
MAKEFILE_PATH = ROOT / "Makefile"
GATE_REPO_PATH = ROOT / "quwoquan_ops/gate/gate_repo.sh"
LOCAL_CONTRACT_TARGET = "test-vertical-architecture-ratchet-local-contract"
MIGRATION_TEST = (
    "quwoquan_ops/tests/local_contract/stackctl/"
    "test_travel_to_gathering_migration__cutover_rollback__local_contract_test.py"
)
RATCHET_TEST = (
    "quwoquan_ops/tests/local_contract/gate/"
    "test_vertical_architecture_ratchet__local_contract_test.py"
)
CAMPUS_REUSE_TEST = (
    "quwoquan_ops/tests/local_contract/gate/"
    "test_campus_gathering_reuse__metadata__local_contract_test.py"
)


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_vertical_architecture_ratchet",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier: {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class VerticalArchitectureRatchetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_verifier()

    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)
        self.baseline_path = self.root / "baseline.yaml"
        self._write(
            "quwoquan_service/contracts/metadata/_shared/domain_taxonomy.yaml",
            textwrap.dedent(
                """
                domains:
                - id: travel
                  mode: content
                  label: {en: Travel}
                  assistant_domain_ids: [travel_companion]
                  sub_categories: [trip_guide]
                - id: campus
                  mode: content
                  label: {en: Campus}
                  assistant_domain_ids: [campus_life]
                  sub_categories: [student_club]
                - id: technology
                  mode: content
                  label: {en: Technology}
                  assistant_domain_ids: [tech]
                  sub_categories: [digital_product]
                """
            ).lstrip(),
        )
        self._domains = {"content", "tag", "assistant", "gateway", "campus"}
        self._write_contract_graph()
        self._write_baseline()

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _write_contract_graph(self) -> None:
        self._write(
            "quwoquan_service/generated/contract_graph.json",
            json.dumps(
                {"objects": [{"domain": domain} for domain in sorted(self._domains)]}
            ),
        )

    def _write_service_owner(self, service: str, domain: str) -> None:
        self._write(
            f"quwoquan_service/services/{service}/contracts/domain.yaml",
            f"domain: {domain}\n",
        )

    @staticmethod
    def _entries(summaries) -> list[dict]:
        return [
            {"path": path, "count": summary.count, "digest": summary.digest}
            for path, summary in sorted(summaries.items())
        ]

    def _write_baseline(self, snapshot=None) -> None:
        empty = {}
        snapshot = snapshot or self.module.Snapshot(
            vertical_terms=frozenset(),
            service_domains={},
            platform_vertical_branches=empty,
            content_vertical_usage=empty,
            domain_taxonomy_runtime_consumers=empty,
            travel_service_dependencies={
                "app": empty,
                "assistant": empty,
                "api_edge": empty,
                "runtime": empty,
                "ops": empty,
            },
        )

        def bucket(owner: str, entries) -> dict:
            return {
                "owner": owner,
                "retirement_condition": "temporary-tree debt reaches zero",
                "entries": self._entries(entries),
            }

        document = {
            "schema": self.module.BASELINE_SCHEMA,
            "governance": {
                "owner": "travel-journey",
                "reason": "temporary-tree contract",
                "retirement_condition": "vertical architecture debt reaches zero",
            },
            "platform_vertical_branches": bucket(
                "architecture", snapshot.platform_vertical_branches
            ),
            "content_vertical_usage": bucket(
                "content", snapshot.content_vertical_usage
            ),
            "domain_taxonomy_runtime_consumers": bucket(
                "taxonomy", snapshot.domain_taxonomy_runtime_consumers
            ),
        }
        self.baseline_path.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def _evaluate(self):
        return self.module.evaluate(
            self.root,
            self.baseline_path,
        )

    def test_new_campus_service_is_blocked_from_taxonomy_and_owner_metadata(self) -> None:
        self._write_service_owner("campus-service", "campus")
        self._write(
            "quwoquan_service/services/campus-service/internal/api.go",
            "package campus\n",
        )

        failures, _ = self._evaluate()

        self.assertTrue(
            any(
                "vertical_service" in failure and "campus-service" in failure
                for failure in failures
            ),
            failures,
        )

    def test_case_travel_business_branch_is_blocked(self) -> None:
        self._write(
            "quwoquan_app/lib/feed/vertical_router.dart",
            textwrap.dedent(
                """
                String route(String value) {
                  switch (value) {
                    case 'travel':
                      return 'trip';
                    default:
                      return 'topic';
                  }
                }
                """
            ).lstrip(),
        )

        failures, _ = self._evaluate()

        self.assertTrue(
            any("platform_vertical_branches" in failure for failure in failures),
            failures,
        )

    def test_content_vertical_literal_comparison_is_blocked(self) -> None:
        self._write(
            "quwoquan_service/runtime/recommendation/vertical_policy.go",
            textwrap.dedent(
                """
                package recommendation

                func route(contentVertical string) string {
                    if contentVertical == "campus" {
                        return "campus-policy"
                    }
                    return "topic-policy"
                }
                """
            ).lstrip(),
        )

        failures, _ = self._evaluate()

        self.assertTrue(
            any("platform_vertical_branches" in failure for failure in failures),
            failures,
        )

    def test_new_open_content_vertical_usage_is_blocked(self) -> None:
        self._write(
            "quwoquan_app/lib/feed/open_payload.dart",
            "final payload = {'contentVertical': input};\n",
        )

        failures, _ = self._evaluate()

        self.assertTrue(
            any("content_vertical_usage" in failure for failure in failures),
            failures,
        )

    def test_new_domain_taxonomy_runtime_consumer_is_blocked(self) -> None:
        self._write(
            "quwoquan_service/runtime/taxonomy/loader.go",
            'package taxonomy\nconst source = "domain_taxonomy.yaml"\n',
        )

        failures, _ = self._evaluate()

        self.assertTrue(
            any(
                "domain_taxonomy_runtime_consumers" in failure
                for failure in failures
            ),
            failures,
        )

    def test_tag_taxonomy_and_experience_package_registry_data_is_legal(self) -> None:
        self._write_service_owner("tag-service", "tag")
        self._write(
            "quwoquan_service/services/tag-service/contracts/tag/registry.yaml",
            textwrap.dedent(
                """
                object: TagTaxonomy
                topics:
                - id: campus
                  distribution: community
                  presentation: card
                  experiencePackage: student_club
                """
            ).lstrip(),
        )

        failures, _ = self._evaluate()

        self.assertEqual([], failures)

    def test_copy_tests_and_migration_tools_do_not_create_false_positives(self) -> None:
        forbidden_example = (
            'switch (value) { case "travel": return contentVertical; }\n'
            'const source = "domain_taxonomy.yaml";\n'
        )
        self._write("quwoquan_app/lib/l10n/example.dart", forbidden_example)
        self._write("quwoquan_app/test/example_test.dart", forbidden_example)
        self._write(
            "quwoquan_service/runtime/migrations/example.py",
            forbidden_example,
        )

        failures, _ = self._evaluate()

        self.assertEqual([], failures)

    def test_clean_hit_reduction_is_accepted_automatically(self) -> None:
        path = self._write(
            "quwoquan_app/lib/feed/legacy_payload.dart",
            "final first = contentVertical;\nfinal second = contentVertical;\n",
        )
        snapshot, issues = self.module.build_snapshot(self.root)
        self.assertEqual([], issues)
        self._write_baseline(snapshot)
        path.write_text("final first = contentVertical;\n", encoding="utf-8")

        failures, report = self._evaluate()

        self.assertEqual([], failures)
        self.assertTrue(
            any("content_vertical_usage" in item for item in report["reductions"]),
            report,
        )

    def test_equal_count_replacement_cannot_move_debt(self) -> None:
        path = self._write(
            "quwoquan_app/lib/feed/legacy_payload.dart",
            "final first = contentVertical;\n",
        )
        snapshot, issues = self.module.build_snapshot(self.root)
        self.assertEqual([], issues)
        self._write_baseline(snapshot)
        path.write_text("final replacement = contentVertical;\n", encoding="utf-8")

        failures, _ = self._evaluate()

        self.assertTrue(
            any("等量命中摘要改变" in failure for failure in failures),
            failures,
        )

    def test_new_travel_service_dependency_is_blocked_in_each_caller_area(self) -> None:
        probes = {
            "app": (
                "quwoquan_app/lib/runtime/new_client.dart",
                "import 'runtime/transport/generated/travel/client.dart';\n",
            ),
            "assistant": (
                "quwoquan_service/services/assistant-service/config/schema.yaml",
                "upstream: travel-service\n",
            ),
            "api_edge": (
                "quwoquan_service/services/api-edge/config/routes.yaml",
                "upstream: travel-service\n",
            ),
            "runtime": (
                "quwoquan_service/runtime/auth/service_credentials.go",
                'var legacyScope = "travel.trip.read"\n',
            ),
            "ops": (
                "quwoquan_ops/cli/lib/nonprod_data_assistant.py",
                'SKILL_ID = "travel_journey_manager"\n',
            ),
        }
        for area, (relative, content) in probes.items():
            with self.subTest(area=area):
                if area == "assistant":
                    self._write_service_owner("assistant-service", "assistant")
                elif area == "api_edge":
                    self._write_service_owner("api-edge", "gateway")
                probe = self._write(relative, content)
                failures, _ = self._evaluate()
                self.assertTrue(
                    any(
                        f"travel_service_dependencies.{area}" in failure
                        for failure in failures
                    ),
                    failures,
                )
                probe.unlink()

    def test_retired_travel_service_directory_is_blocked_even_when_empty(self) -> None:
        (self.root / self.module.RETIRED_TRAVEL_SERVICE).mkdir(parents=True)

        failures, report = self._evaluate()

        self.assertTrue(
            any("retired_travel_service" in failure for failure in failures),
            failures,
        )
        self.assertTrue(report["retired_travel_service_present"], report)

    def test_restored_travel_service_owner_and_source_are_still_blocked(self) -> None:
        self._write_service_owner("travel-service", "travel")
        self._write(
            "quwoquan_service/services/travel-service/internal/sentinel.go",
            "package travel\n",
        )

        failures, _ = self._evaluate()

        self.assertTrue(
            any("retired_travel_service" in failure for failure in failures),
            failures,
        )
        self.assertTrue(
            any("vertical_service" in failure for failure in failures),
            failures,
        )

    def test_retired_travel_service_symlink_is_blocked(self) -> None:
        target = self.root / "parked-travel-owner"
        target.mkdir()
        retired = self.root / self.module.RETIRED_TRAVEL_SERVICE
        retired.parent.mkdir(parents=True, exist_ok=True)
        retired.symlink_to(target, target_is_directory=True)

        failures, report = self._evaluate()

        self.assertTrue(
            any("retired_travel_service" in failure for failure in failures),
            failures,
        )
        self.assertTrue(report["retired_travel_service_present"], report)

    def test_materialized_travel_domain_owner_is_blocked(self) -> None:
        self._write(
            ".qwq_output/env/repo/local/service-contract-view/cache/run/"
            "travel/contracts/domain.yaml",
            "domain: travel\n",
        )

        failures, report = self._evaluate()

        self.assertTrue(
            any("materialized_travel_owner" in failure for failure in failures),
            failures,
        )
        self.assertEqual(1, report["materialized_travel_owners"])

    def test_parked_materialized_travel_tree_is_blocked_even_when_empty(self) -> None:
        (
            self.root / ".qwq_output/travel-service-materialized.parked-20260807"
        ).mkdir(parents=True)

        failures, _ = self._evaluate()

        self.assertTrue(
            any("materialized_travel_owner" in failure for failure in failures),
            failures,
        )

    def test_contract_graph_travel_object_operation_source_and_document_are_blocked(
        self,
    ) -> None:
        self._write(
            "quwoquan_service/generated/contract_graph.json",
            json.dumps(
                {
                    "objects": [
                        {
                            "id": "travel.trip_plan",
                            "domain": "travel",
                            "sourcePath": "travel/travel/trip_plan/object.yaml",
                        }
                    ],
                    "operations": [
                        {
                            "id": "travel.trip_plan.GetTripPlan",
                            "domain": "travel",
                            "objectId": "travel.trip_plan",
                            "sourcePath": "travel/travel/trip_plan/operations.yaml",
                        }
                    ],
                    "sources": [
                        {
                            "path": "travel/travel/trip_plan/object.yaml",
                            "sha256": "a" * 64,
                        }
                    ],
                    "documents": [
                        {
                            "path": "travel/travel/trip_plan/object.yaml",
                            "sha256": "a" * 64,
                            "content": {"object": "TripPlan"},
                        }
                    ],
                }
            ),
        )

        failures, report = self._evaluate()

        self.assertTrue(
            any("contract_graph_travel_ghost" in failure for failure in failures),
            failures,
        )
        self.assertEqual(4, report["contract_graph_travel_ghosts"])

    def test_app_lock_manifest_and_physical_travel_client_are_blocked(self) -> None:
        self._write(
            "quwoquan_app/tool/cloud_codegen/contract_graph.lock.json",
            json.dumps(
                {
                    "appExposedOperations": [
                        {
                            "canonicalOperationId": (
                                "travel.trip_plan.GetTripPlan"
                            ),
                            "domain": "travel",
                            "objectId": "travel.trip_plan",
                            "sourcePath": "travel/travel/trip_plan/operations.yaml",
                        }
                    ]
                }
            ),
        )
        self._write(
            "quwoquan_app/tool/cloud_codegen/generated_manifest.json",
            json.dumps(
                {
                    "outputs": [
                        {
                            "path": (
                                "packages/quwoquan_cloud_contracts/lib/src/"
                                "travel/travel_operation_contracts.g.dart"
                            )
                        }
                    ]
                }
            ),
        )
        self._write(
            "quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/travel/"
            "travel_operation_contracts.g.dart",
            "// retired\n",
        )

        failures, report = self._evaluate()

        self.assertTrue(
            any("app_travel_contract_ghost" in failure for failure in failures),
            failures,
        )
        self.assertEqual(3, report["app_travel_contract_ghosts"])

    def test_baseline_rejects_retired_service_allowance_section(self) -> None:
        document = yaml.safe_load(self.baseline_path.read_text(encoding="utf-8"))
        document["legacy_vertical_service_allowance"] = {
            "path": self.module.RETIRED_TRAVEL_SERVICE.as_posix(),
            "domain_owner": "travel",
            "migration_owner": "travel-journey",
            "expires_on_require_complete_cutover": True,
        }
        self.baseline_path.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "不再接受.*迁移期 section"):
            self.module.load_baseline(self.baseline_path)

    def test_matching_dependency_digest_cannot_restore_old_baseline_section(self) -> None:
        self._write(
            "quwoquan_app/lib/runtime/restored_travel_client.dart",
            "import 'runtime/transport/generated/travel/client.dart';\n",
        )
        snapshot, issues = self.module.build_snapshot(self.root)
        self.assertEqual([], issues)
        document = yaml.safe_load(self.baseline_path.read_text(encoding="utf-8"))
        document["travel_service_dependencies"] = {
            area: {
                "owner": area,
                "retirement_condition": "restored migration allowance",
                "entries": self._entries(snapshot.travel_service_dependencies[area]),
            }
            for area in self.module.TRAVEL_DEPENDENCY_AREAS
        }
        self.baseline_path.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "不再接受.*迁移期 section"):
            self.module.load_baseline(self.baseline_path)

    def test_canonical_baseline_has_no_retired_travel_sections(self) -> None:
        document = yaml.safe_load(BASELINE_PATH.read_text(encoding="utf-8"))

        self.assertNotIn("legacy_vertical_service_allowance", document)
        self.assertNotIn("travel_service_dependencies", document)

    def test_canonical_make_target_uses_the_shared_pytest_runtime(self) -> None:
        source = MAKEFILE_PATH.read_text(encoding="utf-8")
        target_start = source.index(f"\n{LOCAL_CONTRACT_TARGET}:")
        target_end = source.index("\n\n", target_start)
        target = source[target_start:target_end]

        self.assertIn(f"{LOCAL_CONTRACT_TARGET}: prepare-test-python", target)
        self.assertIn(
            "$(DATA_PYTHON) $(PYTEST_INTERPRETER_FLAGS) -c 'import pytest'",
            target,
        )
        self.assertIn(
            "$(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest "
            "$(PYTEST_FLAGS)",
            target,
        )
        self.assertIn(MIGRATION_TEST, target)
        self.assertIn(RATCHET_TEST, target)
        self.assertIn(CAMPUS_REUSE_TEST, target)
        self.assertIn("PYTEST_INTERPRETER_FLAGS ?= -B", source)
        self.assertIn(
            "PYTEST_FLAGS ?= -o cache_dir=$(QWQ_OUTPUT_ROOT)"
            "/env/repo/local/tests/cache/pytest",
            source,
        )

    def test_make_verification_targets_share_permanent_zero_gap_semantics(self) -> None:
        source = MAKEFILE_PATH.read_text(encoding="utf-8")
        canonical_start = source.index("\nverify-vertical-architecture-ratchet:")
        canonical_end = source.index("\n\n", canonical_start)
        canonical_target = source[canonical_start:canonical_end]
        # 实现单轨在 vertical_architecture_ratchet/ 包内；文本断言同时覆盖
        # 薄入口与包内全部模块。
        verifier_source = "\n".join(
            [VERIFIER_PATH.read_text(encoding="utf-8")]
            + [
                module_path.read_text(encoding="utf-8")
                for module_path in sorted(VERIFIER_PACKAGE_PATH.glob("*.py"))
            ]
        )

        self.assertIn("verify_vertical_architecture_ratchet.py", canonical_target)
        self.assertNotIn("--require-complete-cutover", canonical_target)
        self.assertNotIn("--require-complete-cutover", verifier_source)
        self.assertNotIn(
            "verify-require-complete-cutover-vertical-architecture",
            source,
        )

    def test_gate_scopes_run_static_and_heavy_checks_once(self) -> None:
        gate = GATE_REPO_PATH.read_text(encoding="utf-8")
        makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
        service_start = gate.index("\nrun_service()")
        app_start = gate.index("\nrun_app()", service_start)
        portal_start = gate.index("\nrun_portal()", app_start)
        service_block = gate[service_start:app_start]
        app_block = gate[app_start:portal_start]
        gate_target_start = makefile.index("\ngate:\n")
        gate_target_end = makefile.index("\ngate-local-gamma:", gate_target_start)
        top_gate = makefile[gate_target_start:gate_target_end]

        self.assertIn("all|service|app)", gate)
        self.assertIn('run_vertical_architecture_ratchet "$scope"', gate)
        self.assertEqual(
            gate.count("make test-vertical-architecture-ratchet-local-contract"),
            1,
        )
        self.assertIn("run_vertical_architecture_local_contract", service_block)
        self.assertNotIn("run_vertical_architecture_local_contract", app_block)
        self.assertIn("gate_repo.sh", top_gate)
        self.assertNotIn(LOCAL_CONTRACT_TARGET, top_gate)
        self.assertNotIn("verify-vertical-architecture-ratchet", top_gate)

    def test_canonical_make_target_dry_run_resolves_real_commands(self) -> None:
        completed = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-n",
                LOCAL_CONTRACT_TARGET,
                f"DATA_PYTHON={sys.executable}",
                f"PYTEST_RUNNER={sys.executable}",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn(f"{sys.executable} -B -c 'import pytest'", completed.stdout)
        self.assertIn(f"{sys.executable} -B -m pytest", completed.stdout)
        self.assertIn(
            f"cache_dir={ROOT}/.qwq_output/env/repo/local/tests/cache/pytest",
            completed.stdout,
        )
        self.assertIn(MIGRATION_TEST, completed.stdout)
        self.assertIn(RATCHET_TEST, completed.stdout)
        self.assertIn(CAMPUS_REUSE_TEST, completed.stdout)


if __name__ == "__main__":
    unittest.main()
