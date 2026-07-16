from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = (
    ROOT / "quwoquan_ops/gate/verify_cloud_commercial_directory_governance.py"
)


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_cloud_commercial_directory_governance",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier: {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CloudCommercialDirectoryGovernanceContractTest(unittest.TestCase):
    def test_repository_architecture_freeze_is_complete(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VERIFIER_PATH)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_mock_inventory_rejects_undocumented_and_stale_entries(self) -> None:
        verifier = _load_verifier()

        failures = verifier.validate_mock_inventory(
            {"MockCurrentRepository", "MockUndocumentedRepository"},
            {"MockCurrentRepository", "MockStaleRepository"},
            max_mock_classes=2,
        )

        self.assertTrue(
            any("MockUndocumentedRepository" in failure for failure in failures)
        )
        self.assertTrue(any("MockStaleRepository" in failure for failure in failures))

    def test_mock_inventory_budget_is_monotonic(self) -> None:
        verifier = _load_verifier()

        failures = verifier.validate_mock_inventory(
            {"MockOne", "MockTwo", "MockThree"},
            {"MockOne", "MockTwo", "MockThree"},
            max_mock_classes=2,
        )

        self.assertEqual(
            failures,
            ["Mock class budget increased: 3 > 2"],
        )

    def test_completed_mock_checklist_rows_are_historical_only(self) -> None:
        verifier = _load_verifier()

        documented = verifier.checklist_mock_classes(
            "| Realtime | `MockRealtime` | [x] | deleted |\n"
            "| Chat | `MockChatRepository` | [ ] | pending |\n"
        )

        self.assertEqual(documented, {"MockChatRepository"})

    def test_report_zero_compat_rejects_alias_context_and_reverse_imports(
        self,
    ) -> None:
        verifier = _load_verifier()

        failures = verifier.validate_report_zero_compat(
            app_sources={
                "lib/retired.dart": "typedef ReportRepository = Object;\n"
                "final reportRepositoryProvider = Object();\n",
            },
            mock_sources={
                "lib/mock.dart": "import 'package:quwoquan_app/app.dart';\n",
            },
            mock_pubspec=(
                "dependencies:\n"
                "  flutter:\n"
                "    sdk: flutter\n"
                "  flutter_riverpod: any\n"
                "  quwoquan_app: any\n"
            ),
            contract_source=(
                "abstract interface class ContentReportCommandWriter {}\n"
                "final String surfaceId = '';\n"
            ),
            runner_source="void main() {}\n",
        )

        self.assertTrue(any("ReportRepository" in failure for failure in failures))
        self.assertTrue(
            any("reportRepositoryProvider" in failure for failure in failures)
        )
        self.assertTrue(
            any("package:quwoquan_app/" in failure for failure in failures)
        )
        self.assertTrue(any("invocation metadata" in failure for failure in failures))
        self.assertTrue(any("override composition" in failure for failure in failures))

    def test_p0_containment_rejects_optional_secret_and_prod_routes(self) -> None:
        verifier = _load_verifier()

        failures = verifier.validate_p0_fail_closed(
            service_sources={
                "user": "",
                "content": "",
                "chat": "",
                "assistant": "",
            },
            runtime_auth_source="",
            seed_box_deployment=(
                "key: AUTH_JWT_SECRET\n"
                "                  optional: true\n"
            ),
            gamma_compose=(
                "services:\n"
                "  content-service:\n"
                "    environment:\n"
                "      AUTH_JWT_SECRET: weak-default\n"
            ),
            prod_roots={
                "aliyun-prod": (
                    "resources:\n"
                    "  - ../../rtc-service/deploy/kustomize/overlays/prod\n"
                    "  - ../../product-ops-service/deploy/kustomize/overlays/prod\n"
                )
            },
        )

        self.assertTrue(
            any("LoadAccessTokenConfig" in failure for failure in failures)
        )
        self.assertTrue(any("trusted-header guard" in failure for failure in failures))
        self.assertTrue(any("remains optional" in failure for failure in failures))
        self.assertTrue(
            any("must be required host configuration" in failure for failure in failures)
        )
        self.assertTrue(any("rtc-service" in failure for failure in failures))
        self.assertTrue(any("product-ops-service" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
