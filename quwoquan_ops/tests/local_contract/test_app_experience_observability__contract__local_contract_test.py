from __future__ import annotations

import copy
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = (
    REPO_ROOT
    / "quwoquan_app/scripts/runtime/observability/verify_ops_event_schema_completeness.py"
)
GOLDEN_CATALOG_PATH = (
    REPO_ROOT
    / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/"
    "golden_metric_catalog.yaml"
)


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_ops_event_schema_completeness",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载体验观测门禁")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AppExperienceObservabilityContractLocalContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()
        cls.catalog = yaml.safe_load(GOLDEN_CATALOG_PATH.read_text(encoding="utf-8"))

    def _verify(self, catalog: dict) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "golden_metric_catalog.yaml"
            path.write_text(
                yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            original = self.verifier.GOLDEN_METRIC_CATALOG
            self.verifier.GOLDEN_METRIC_CATALOG = path
            try:
                errors: list[str] = []
                self.verifier.verify_golden_metrics(errors)
                return errors
            finally:
                self.verifier.GOLDEN_METRIC_CATALOG = original

    def test_repository_catalog_satisfies_the_frozen_contract(self) -> None:
        self.assertEqual(self._verify(copy.deepcopy(self.catalog)), [])

    def test_required_h1_metric_cannot_be_silently_removed(self) -> None:
        candidate = copy.deepcopy(self.catalog)
        candidate["metrics"] = [
            metric
            for metric in candidate["metrics"]
            if metric["metric_id"] != "app_anr_rate"
        ]

        errors = self._verify(candidate)

        self.assertTrue(
            any(
                "app experience golden metrics are incomplete" in error
                and "app_anr_rate" in error
                for error in errors
            ),
            errors,
        )

    def test_primary_metric_budget_is_enforced_per_business(self) -> None:
        candidate = copy.deepcopy(self.catalog)
        extra = copy.deepcopy(candidate["metrics"][0])
        extra["metric_id"] = "app_anr_count"
        candidate["metrics"].append(extra)

        errors = self._verify(candidate)

        self.assertIn(
            "app_experience registers 4 primary metrics, maximum is 3",
            errors,
        )

    def test_value_field_must_belong_to_the_source_event(self) -> None:
        candidate = copy.deepcopy(self.catalog)
        metric = next(
            row
            for row in candidate["metrics"]
            if row["metric_id"] == "page_first_usable_p95_ms"
        )
        metric["source"]["value_field"] = "errorCode"

        errors = self._verify(candidate)

        self.assertTrue(
            any(
                "value_field errorCode is not emitted by page_first_usable"
                in error
                for error in errors
            ),
            errors,
        )

    def test_high_cardinality_dimensions_remain_forbidden(self) -> None:
        candidate = copy.deepcopy(self.catalog)
        candidate["metrics"][0]["dimensions"].append("sessionId")

        errors = self._verify(candidate)

        self.assertTrue(
            any("uses high-cardinality dimensions ['sessionId']" in error for error in errors),
            errors,
        )

    def test_storage_contract_key_drift_is_rejected_by_canonical_view(self) -> None:
        storage = self.verifier.load_storage_contract_view(
            self.verifier.EVENT_STORAGE
        )
        raw = storage["logstores"]["raw"]
        raw["retention_days"] = raw.pop("ttl_days")

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "storage.yaml"
            path.write_text(
                yaml.safe_dump(storage, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "storage-contract-view failed"):
                self.verifier.event_storage_logstore_retentions(path)

    def test_storage_contract_bridge_exit_is_fail_closed(self) -> None:
        def failed(*_args, **_kwargs):
            return subprocess.CompletedProcess(
                args=[], returncode=2, stdout="", stderr="decode failed"
            )

        with self.assertRaisesRegex(ValueError, "failed with exit 2"):
            self.verifier.load_storage_contract_view(
                self.verifier.EVENT_STORAGE,
                _run=failed,
            )

    def test_storage_contract_bridge_timeout_is_fail_closed(self) -> None:
        def timed_out(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        with self.assertRaisesRegex(ValueError, "timed out"):
            self.verifier.load_storage_contract_view(
                self.verifier.EVENT_STORAGE,
                _run=timed_out,
            )

    def test_storage_contract_bridge_non_json_is_fail_closed(self) -> None:
        def non_json(*_args, **_kwargs):
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="not-json", stderr=""
            )

        with self.assertRaisesRegex(ValueError, "non-JSON"):
            self.verifier.load_storage_contract_view(
                self.verifier.EVENT_STORAGE,
                _run=non_json,
            )


if __name__ == "__main__":
    unittest.main()
