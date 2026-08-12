"""Lock SMS local-capture API evidence to the real package-bound boundary.

spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import ssl
import tempfile
import unittest
import urllib.error
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
API_SOURCE = (
    ROOT
    / "quwoquan_ops/tests/acceptance/api_integration/service_ops/"
    "integration-service/ci/ext_sms_local_capture_provider_conformance.py"
)
HARNESS_SOURCE = (
    ROOT
    / "quwoquan_ops/ci/provider_conformance/"
    "run_sms_local_capture_api_integration.py"
)
LIVE_JOURNEY_SOURCE = (
    ROOT
    / "quwoquan_ops/tests/acceptance/api_integration/service_ops/"
    "user-service/otp_local_capture_live_journey__api_integration_test.py"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _literal_command(path: Path) -> tuple[str, ...]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "COMMAND"
            for target in node.targets
        ):
            return tuple(str(item) for item in ast.literal_eval(node.value))
    raise AssertionError(f"COMMAND not found in {path}")


class SMSLocalCaptureAPIHarnessContractTest(unittest.TestCase):
    def test_api_integration_runs_the_ops_owned_https_workload(self) -> None:
        self.assertEqual(
            _literal_command(API_SOURCE),
            (
                "python3",
                "quwoquan_ops/ci/provider_conformance/"
                "run_sms_local_capture_api_integration.py",
            ),
        )
        source = HARNESS_SOURCE.read_text(encoding="utf-8")
        self.assertIn("./cmd/sms-provider-substitute", source)
        self.assertIn("ENDPOINT_CONTRACT", source)
        self.assertIn("PROTOCOL_TEST_PACKAGE", source)
        self.assertIn('"provider_conformance"', source)
        self.assertIn('"QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST"', source)
        self.assertIn("keyUsage=critical,keyCertSign,cRLSign", source)
        self.assertNotIn("go run", source)

    def test_harness_never_puts_provider_material_in_argv(self) -> None:
        source = HARNESS_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        sensitive_names = {
            "provider_token",
            "operator_token",
            "capture_key",
            "certificate_path",
            "private_key_path",
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            is_process = (
                isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "subprocess"
                and function.attr in {"Popen", "run"}
            )
            if not is_process or not node.args:
                continue
            argv_names = {
                child.id
                for child in ast.walk(node.args[0])
                if isinstance(child, ast.Name)
            }
            self.assertFalse(
                argv_names & sensitive_names,
                f"sensitive Provider material reached argv: {argv_names}",
            )

    def test_harness_rejects_prod_before_starting_a_process(self) -> None:
        module = _load_module(HARNESS_SOURCE, "sms_local_capture_api_harness")
        with mock.patch.dict(
            os.environ,
            {
                "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT": "prod",
                "QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID": "ext.sms.local_capture",
                "QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST": "sha256:" + "a" * 64,
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "Alpha/Beta/Gamma"):
                module.main()

    def test_harness_rejects_noncanonical_config_digest_before_process_start(
        self,
    ) -> None:
        module = _load_module(HARNESS_SOURCE, "sms_local_capture_bad_digest")
        with mock.patch.dict(
            os.environ,
            {
                "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT": "alpha",
                "QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID": "ext.sms.local_capture",
                "QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST": "sha256:" + "z" * 64,
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "config digest"):
                module.main()

    def test_live_journey_uses_selected_environment_and_active_package(self) -> None:
        source = LIVE_JOURNEY_SOURCE.read_text(encoding="utf-8")
        self.assertIn("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT", source)
        self.assertIn("active_deployment_candidate", source)
        self.assertIn("load_candidate_manifest", source)
        self.assertIn('manifest.get("providerRuntime")', source)
        self.assertNotIn('environment = "gamma"', source)
        self.assertNotIn('target_name = "gamma-local"', source)

    def test_live_journey_binds_target_ca_to_each_local_managed_tls_probe(
        self,
    ) -> None:
        module = _load_module(LIVE_JOURNEY_SOURCE, "otp_local_capture_tls_routes")
        target_tls = mock.sentinel.target_tls

        probes = module._runtime_probes(
            api_base="https://api.alpha.quwoquan.com",
            user_health="http://127.0.0.1:17240/healthz",
            integration_health="http://127.0.0.1:17320/healthz",
            substitute_health="https://127.0.0.1:17330/healthz",
            local_tls=target_tls,
        )

        self.assertEqual(
            probes,
            (
                (
                    "api-edge",
                    "https://api.alpha.quwoquan.com/healthz",
                    target_tls,
                ),
                ("user-service", "http://127.0.0.1:17240/healthz", None),
                (
                    "integration-service",
                    "http://127.0.0.1:17320/healthz",
                    None,
                ),
                (
                    "sms-provider-substitute",
                    "https://127.0.0.1:17330/healthz",
                    target_tls,
                ),
            ),
        )

    def test_live_probe_accepts_target_ca_and_fails_closed_for_unknown_ca(
        self,
    ) -> None:
        module = _load_module(LIVE_JOURNEY_SOURCE, "otp_local_capture_tls_probe")
        target_tls = mock.sentinel.target_tls

        class _Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        def open_url(
            _url: str,
            *,
            timeout: float,
            context: object,
        ) -> _Response:
            self.assertEqual(timeout, 2.0)
            if context is not target_tls:
                raise urllib.error.URLError(
                    ssl.SSLCertVerificationError(
                        1,
                        "certificate verify failed: unknown ca",
                    )
                )
            return _Response()

        with mock.patch.object(module.urllib.request, "urlopen", side_effect=open_url):
            self.assertFalse(
                module._probe("https://api.alpha.quwoquan.com/healthz")
            )
            self.assertTrue(
                module._probe(
                    "https://api.alpha.quwoquan.com/healthz",
                    context=target_tls,
                )
            )

    def test_live_journey_requires_candidate_bound_sms_composition(self) -> None:
        module = _load_module(LIVE_JOURNEY_SOURCE, "otp_local_capture_live_journey")
        baseline_id = "sha256:" + "b" * 64
        runtime_config_digest = "sha256:" + "c" * 64
        with tempfile.TemporaryDirectory() as temporary:
            candidate_root = Path(temporary) / "candidate"
            runtime_path = candidate_root / "packages/app/environment_runtime.yaml"
            runtime_path.parent.mkdir(parents=True)
            runtime_raw = json.dumps(
                {
                    "environment": "beta",
                    "target": "beta-local",
                    "portProfile": "beta-local",
                    "publicBases": {"api": "https://api.beta.example.test"},
                }
            ).encode("utf-8")
            runtime_path.write_bytes(runtime_raw)
            environment_runtime_digest = (
                "sha256:" + hashlib.sha256(runtime_raw).hexdigest()
            )
            manifest = {
                "runtimeConfigDigest": runtime_config_digest,
                "configurationDigest": runtime_config_digest,
                "environmentRuntimeDigest": environment_runtime_digest,
                "providerRuntime": {
                    "composition": {
                        "runtimeCompositionDigest": "sha256:" + "d" * 64,
                        "bindings": [
                            {
                                "capabilityId": "identity.sms.otp",
                                "state": "enabled",
                                "adapterId": "ext.sms.local_capture",
                                "endpointRef": (
                                    "local_topology:sms-provider-substitute"
                                ),
                            }
                        ],
                        "workloads": [
                            {
                                "role": "sms-provider-substitute",
                                "capabilityIds": ["identity.sms.otp"],
                                "adapterIds": ["ext.sms.local_capture"],
                            }
                        ],
                    }
                },
            }
            startup = {
                "status": "running",
                "workload": "full",
                "env": "beta",
                "target": "beta-local",
                "candidateDigest": baseline_id,
                "configurationDigest": runtime_config_digest,
                "providerRuntimeDigest": "sha256:" + "d" * 64,
                "attemptId": "attempt-beta-sms-live",
            }
            with (
                mock.patch.object(
                    module,
                    "active_deployment_candidate",
                    return_value={
                        "baselineId": baseline_id,
                        "candidateDir": str(candidate_root),
                    },
                ),
                mock.patch.object(
                    module,
                    "load_candidate_manifest",
                    return_value=manifest,
                ) as load_manifest,
                mock.patch.object(
                    module,
                    "load_startup_attempt",
                    return_value=startup,
                ),
            ):
                target, runtime, loaded_manifest, loaded_baseline, loaded_startup = (
                    module._load_package_bound_runtime("beta")
                )
        self.assertEqual(target, "beta-local")
        self.assertEqual(runtime["portProfile"], "beta-local")
        self.assertIs(loaded_manifest, manifest)
        self.assertEqual(loaded_baseline, baseline_id)
        self.assertIs(loaded_startup, startup)
        load_manifest.assert_called_once_with(
            "beta",
            "beta-local",
            baseline_id,
            require_full=True,
        )


if __name__ == "__main__":
    unittest.main()
