"""Five-domain generated Remote API integration gate and stackctl contract."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import stackctl  # noqa: E402
from quwoquan_ops.cli.lib import domain_remote_api_integration as evidence  # noqa: E402


SCRIPT = (
    ROOT
    / "quwoquan_ops/gate/verify_app_domain_remote_api_integration.py"
)
MAKEFILE_PATH = ROOT / "Makefile"
GATE_REPO_PATH = ROOT / "quwoquan_ops/gate/gate_repo.sh"
MAKE_TARGET = "verify-app-domain-remote-api-integration"

SPEC = importlib.util.spec_from_file_location(
    "verify_app_domain_remote_api_integration",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
ratchet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ratchet
SPEC.loader.exec_module(ratchet)


class AppDomainRemoteApiIntegrationContractTest(unittest.TestCase):
    def test_contract_graph_derives_one_valid_object_case_per_domain(self) -> None:
        cases, discovery_issues = evidence.discover_cases(ROOT)
        validated, validation_issues = evidence.validate_cases(ROOT, cases)

        self.assertEqual(discovery_issues, [])
        self.assertEqual(validation_issues, [])
        self.assertEqual(
            {case.domain for case in validated},
            set(evidence.GOVERNED_DOMAINS),
        )
        self.assertGreaterEqual(len(validated), len(evidence.GOVERNED_DOMAINS))
        for case in validated:
            self.assertGreaterEqual(case.service_api_test_count, 1)
            self.assertTrue(
                case.harness_path.endswith(
                    f"/{case.domain}_api_contract_harness.dart"
                )
            )

    def test_baseline_matches_derived_object_and_test_counts(self) -> None:
        counts, issues = ratchet.current_evidence()
        baseline = ratchet.load_baseline()
        self.assertEqual(issues, [])
        self.assertEqual(ratchet.evaluate(counts, baseline), [])

    def test_service_test_count_deduplicates_shared_object_evidence(self) -> None:
        shared = (
            "quwoquan_service/services/entity-service/tests/api_integration/"
            "entity_homepage/homepage/example__api_integration_test.go"
        )
        cases = [
            evidence.DomainRemoteApiCase(
                domain="entity",
                object_id=f"entity.homepage.{index}",
                test_path=f"case-{index}.dart",
                test_sha256=str(index),
                service_test_paths=(shared,),
            )
            for index in range(2)
        ]
        self.assertEqual(
            evidence.evidence_counts(cases)["entity"]["serviceTestFileCount"],
            1,
        )

    def test_every_count_dimension_is_monotonic(self) -> None:
        counts, _ = ratchet.current_evidence()
        baseline = ratchet.load_baseline()
        for domain in evidence.GOVERNED_DOMAINS:
            for field in ratchet.COUNT_FIELDS:
                mutated = json.loads(json.dumps(baseline))
                mutated["domains"][domain][field] = counts[domain][field] + 1
                failures = ratchet.evaluate(counts, mutated)
                self.assertTrue(
                    any(domain in failure and field in failure for failure in failures)
                )

    def test_update_baseline_rejects_evidence_decrease(self) -> None:
        counts, _ = ratchet.current_evidence()
        domain = "entity"
        with tempfile.TemporaryDirectory() as temporary_dir:
            baseline_path = Path(temporary_dir) / "baseline.json"
            payload = {
                "_governance": {},
                "schema": ratchet.BASELINE_SCHEMA,
                "ruleId": ratchet.RULE_ID,
                "domains": json.loads(json.dumps(counts)),
            }
            payload["domains"][domain]["serviceTestFileCount"] += 1
            baseline_path.write_text(json.dumps(payload), encoding="utf-8")
            original = ratchet.BASELINE_PATH
            ratchet.BASELINE_PATH = baseline_path
            try:
                self.assertEqual(ratchet.main(["--update-baseline"]), 2)
            finally:
                ratchet.BASELINE_PATH = original

    def test_update_baseline_accepts_evidence_increase(self) -> None:
        counts, _ = ratchet.current_evidence()
        domain = "entity"
        self.assertGreater(counts[domain]["serviceTestFileCount"], 1)
        with tempfile.TemporaryDirectory() as temporary_dir:
            baseline_path = Path(temporary_dir) / "baseline.json"
            payload = {
                "_governance": {},
                "schema": ratchet.BASELINE_SCHEMA,
                "ruleId": ratchet.RULE_ID,
                "domains": json.loads(json.dumps(counts)),
            }
            payload["domains"][domain]["serviceTestFileCount"] -= 1
            baseline_path.write_text(json.dumps(payload), encoding="utf-8")
            original = ratchet.BASELINE_PATH
            ratchet.BASELINE_PATH = baseline_path
            try:
                self.assertEqual(ratchet.main(["--update-baseline"]), 0)
                updated = json.loads(baseline_path.read_text(encoding="utf-8"))
                self.assertEqual(updated["domains"], counts)
            finally:
                ratchet.BASELINE_PATH = original

    def test_make_and_app_static_gate_use_semantic_target_once(self) -> None:
        source = MAKEFILE_PATH.read_text(encoding="utf-8")
        target_start = source.index(f"\n{MAKE_TARGET}:")
        target_end = source.index("\n\n", target_start)
        target = source[target_start:target_end]
        self.assertIn(SCRIPT.relative_to(ROOT).as_posix(), target)
        self.assertIn(Path(__file__).relative_to(ROOT).as_posix(), target)

        completed = subprocess.run(
            ["make", "--no-print-directory", "-n", MAKE_TARGET],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        gate = GATE_REPO_PATH.read_text(encoding="utf-8")
        app_start = gate.index("\nrun_app()")
        portal_start = gate.index("\nrun_portal()", app_start)
        self.assertEqual(gate[app_start:portal_start].count(f"make {MAKE_TARGET}"), 1)
        self.assertNotIn("verify-t7-domain-api-integration-ratchet", gate)

    def test_gamma_profiles_run_remote_cases_after_health(self) -> None:
        for profile in (
            stackctl.VerificationProfile.INTEGRATION,
            stackctl.VerificationProfile.RELEASE,
        ):
            commands = stackctl._selected_profile_commands(
                "gamma",
                "gamma-local",
                profile,
                Path("/tmp/domain-remote-api-report"),
            )
            names = [command["name"] for command in commands]
            self.assertEqual(names[0], "gamma-local-health-preflight")
            self.assertEqual(names[1], "gamma-local-app-domain-api-integration")
            remote = commands[1]
            self.assertTrue(remote["stopOnFailure"])
            self.assertIn("app-domain-api-integration", remote["argv"])

    def test_stackctl_executes_derived_cases_without_skip(self) -> None:
        cases, _ = evidence.discover_cases(ROOT)
        validated, validation_issues = evidence.validate_cases(ROOT, cases)
        self.assertEqual(validation_issues, [])
        with tempfile.TemporaryDirectory() as temporary_dir:
            result = mock.Mock(returncode=0, stdout="all passed", stderr="")
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={"targets": {}},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={
                        "env": "gamma",
                        "publicBases": {"api": "https://api.gamma.test"},
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value={
                        "status": "running",
                        "target": "gamma-local",
                        "env": "gamma",
                        "workload": "full",
                        "candidateDigest": f"sha256:{'1' * 64}",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": f"sha256:{'1' * 64}"},
                ),
                mock.patch.object(stackctl, "run", return_value=result) as runner,
            ):
                payload = stackctl.command_app_domain_api_integration(
                    mock.Mock(
                        target="gamma-local",
                        command="app-domain-api-integration",
                        report_dir=temporary_dir,
                    )
                )

            self.assertEqual(payload["exitCode"], 0)
            argv = runner.call_args.args[0]
            self.assertIn("--dart-define=API_CONTRACT_ENV=gamma", argv)
            self.assertIn(
                "--dart-define=API_CONTRACT_BASE_URL=https://api.gamma.test",
                argv,
            )
            self.assertEqual(
                len(
                    [
                        item
                        for item in argv
                        if item.endswith("__api_integration_test.dart")
                    ]
                ),
                len(validated),
            )
            report = json.loads(
                (Path(temporary_dir) / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["executed"], len(validated))
            self.assertEqual(report["skipped"], 0)

    def test_stackctl_blocks_invalid_active_candidate_without_remote_execution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={"targets": {}},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={
                        "env": "gamma",
                        "publicBases": {"api": "https://api.gamma.test"},
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    side_effect=ValueError(
                        "deployment candidate manifest fields mismatch"
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value={
                        "status": "running",
                        "target": "gamma-local",
                        "env": "gamma",
                        "workload": "full",
                        "candidateDigest": f"sha256:{'1' * 64}",
                    },
                ),
                mock.patch.object(stackctl, "run") as runner,
            ):
                payload = stackctl.command_app_domain_api_integration(
                    mock.Mock(
                        target="gamma-local",
                        command="app-domain-api-integration",
                        report_dir=temporary_dir,
                    )
                )

            self.assertEqual(payload["exitCode"], 2)
            runner.assert_not_called()
            self.assertTrue(
                any(
                    "active candidate is invalid: deployment candidate manifest fields mismatch"
                    in item
                    for item in payload["details"]
                )
            )
            report = json.loads(
                (Path(temporary_dir) / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["executed"], 0)
            self.assertEqual(report["skipped"], 0)

    def test_inspect_reports_invalid_candidate_instead_of_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            args = mock.Mock(
                target="gamma-local",
                scope="network",
                command="inspect",
                report_dir=temporary_dir,
            )
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={"targets": {}},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "gamma", "portProfile": "gamma"},
                ),
                mock.patch.object(
                    stackctl,
                    "_network_report",
                    side_effect=ValueError(
                        "deployment candidate manifest fields mismatch"
                    ),
                ),
            ):
                payload = stackctl.command_inspect(args)

            self.assertEqual(payload["exitCode"], 1)
            report = json.loads(
                (Path(temporary_dir) / "report.json").read_text(encoding="utf-8")
            )
            issues = report["inspection"]["network"]["issues"]
            self.assertTrue(
                any("deployment candidate manifest fields mismatch" in item for item in issues)
            )

    def test_inspect_data_reports_invalid_candidate_instead_of_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            args = mock.Mock(
                target="gamma-local",
                scope="data",
                command="inspect",
                report_dir=temporary_dir,
            )
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={"targets": {}},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "gamma", "portProfile": "gamma"},
                ),
                mock.patch.object(
                    stackctl,
                    "_candidate_workspace_report",
                    return_value={"status": "gate_block", "issues": []},
                ),
                mock.patch.object(
                    stackctl,
                    "_data_report",
                    side_effect=ValueError(
                        "deployment candidate manifest fields mismatch"
                    ),
                ),
            ):
                payload = stackctl.command_inspect(args)

            self.assertEqual(payload["exitCode"], 1)
            report = json.loads(
                (Path(temporary_dir) / "report.json").read_text(encoding="utf-8")
            )
            issues = report["inspection"]["data"]["issues"]
            self.assertTrue(
                any("deployment candidate manifest fields mismatch" in item for item in issues)
            )

    def test_inspect_metrics_reports_invalid_candidate_instead_of_crashing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            args = mock.Mock(
                target="gamma-local",
                scope="metrics",
                command="inspect",
                report_dir=temporary_dir,
            )
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={"targets": {}},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "gamma", "portProfile": "gamma"},
                ),
                mock.patch.object(
                    stackctl,
                    "_metrics_report",
                    side_effect=ValueError(
                        "deployment candidate manifest fields mismatch"
                    ),
                ),
            ):
                payload = stackctl.command_inspect(args)

            self.assertEqual(payload["exitCode"], 1)
            report = json.loads(
                (Path(temporary_dir) / "report.json").read_text(encoding="utf-8")
            )
            issues = report["inspection"]["metrics"]["issues"]
            self.assertTrue(
                any("deployment candidate manifest fields mismatch" in item for item in issues)
            )

    def test_doctor_reports_invalid_candidate_instead_of_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            args = mock.Mock(
                target="gamma-local",
                command="doctor",
                report_dir=temporary_dir,
            )
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={"targets": {}},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "gamma", "portProfile": "gamma"},
                ),
                mock.patch.object(
                    stackctl,
                    "_load_active_product_telemetry_log_sink",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "command_health",
                    return_value={"exitCode": 1},
                ),
                mock.patch.object(
                    stackctl,
                    "_network_report",
                    side_effect=ValueError(
                        "deployment candidate manifest fields mismatch"
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "app_deployment_package_dir",
                    side_effect=ValueError(
                        "deployment candidate manifest fields mismatch"
                    ),
                ),
            ):
                payload = stackctl.command_doctor(args)

            self.assertEqual(payload["exitCode"], 1)
            self.assertTrue(
                any(
                    "network inspection blocked: deployment candidate manifest fields mismatch"
                    in item
                    for item in payload["details"]
                )
            )
            self.assertTrue(
                any(
                    "package inspection blocked: deployment candidate manifest fields mismatch"
                    in item
                    for item in payload["details"]
                )
            )
            self.assertTrue((Path(temporary_dir) / "report.json").is_file())


if __name__ == "__main__":
    unittest.main()
