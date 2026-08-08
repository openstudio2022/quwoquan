"""Lock nonprod Provider Patrol to one running full immutable candidate.

spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#req-002
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.ci.provider_conformance import run_provider_patrol_uat as subject
from quwoquan_ops.ci.provider_conformance.protected_otp_broker import (
    ProtectedOTPBrokerBinding,
)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _runtime_fixture(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    runtime = {
        "schema": "environment-runtime-package",
        "environment": "alpha",
        "target": "alpha-local",
        "publicBases": {"api": "https://api.alpha.example"},
    }
    runtime_path = root / "packages/app/environment_runtime.yaml"
    runtime_path.parent.mkdir(parents=True)
    runtime_raw = (json.dumps(runtime) + "\n").encode("utf-8")
    runtime_path.write_bytes(runtime_raw)
    manifest: dict[str, object] = {
        "baselineId": _digest("baseline"),
        "sourceRevision": "a" * 40,
        "packageDigest": _digest("package"),
        "imageDigest": _digest("image"),
        "configurationDigest": _digest("service-configuration"),
        "runtimeConfigDigest": _digest("runtime"),
        "environmentRuntimeDigest": _digest_bytes(runtime_raw),
        "providerRuntime": {
            "composition": {
                "runtimeCompositionDigest": _digest("provider"),
                "bindings": [
                    {
                        "capabilityId": "identity.sms.otp",
                        "state": "enabled",
                        "adapterId": "ext.sms.local_capture",
                        "endpointRef": "local_topology:sms-provider-substitute",
                    }
                ],
            }
        },
        "observabilityLogSink": {
            "adapterId": "ext.obs.elasticsearch",
            "deploymentMode": "package-bound-local",
            "bindingDigest": _digest("es-binding"),
            "imageDigest": _digest("es-image"),
            "composeDigest": _digest("es-compose"),
            "clusterRef": "target:alpha-local/product-ops/elasticsearch",
        },
        "release": {
            "candidate": {
                "releaseId": "release-candidate",
                "releaseDigest": _digest("release"),
            }
        },
    }
    startup: dict[str, object] = {
        "attemptId": "attempt-alpha-1",
        "status": "running",
        "workload": "full",
        "env": "alpha",
        "target": "alpha-local",
        "candidateDigest": manifest["baselineId"],
        "configurationDigest": manifest["configurationDigest"],
        "providerRuntimeDigest": _digest("provider"),
        "observabilityLogSinkDigest": _digest("es-compose"),
        "composeProject": "quwoquan-alpha",
        "failure": None,
        "cleanupFailure": None,
    }
    return manifest, startup


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


class ProviderPatrolRuntimeIdentityContractTest(unittest.TestCase):
    def _load(
        self,
        candidate_root: Path,
        manifest: dict[str, object],
        startup: dict[str, object],
    ) -> subject.ProviderPatrolRuntimeIdentity:
        active = {
            "baselineId": manifest["baselineId"],
            "candidateDir": str(candidate_root),
        }
        with (
            mock.patch.object(
                subject,
                "active_deployment_candidate",
                return_value=active,
            ),
            mock.patch.object(
                subject,
                "load_candidate_manifest",
                return_value=manifest,
            ) as load_manifest,
            mock.patch.object(
                subject,
                "load_startup_attempt",
                return_value=startup,
            ),
        ):
            identity = subject._load_nonprod_runtime_identity(
                "alpha", "alpha-local"
            )
        load_manifest.assert_called_once_with(
            "alpha",
            "alpha-local",
            manifest["baselineId"],
            require_full=True,
        )
        return identity

    def test_loads_package_provider_es_release_and_running_attempt_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-provider-patrol-") as temporary:
            candidate_root = Path(temporary)
            manifest, startup = _runtime_fixture(candidate_root)
            identity = self._load(candidate_root, manifest, startup)

        self.assertEqual(identity.baseline_id, manifest["baselineId"])
        self.assertEqual(identity.package_digest, manifest["packageDigest"])
        self.assertEqual(
            identity.runtime_config_digest,
            manifest["runtimeConfigDigest"],
        )
        self.assertNotEqual(
            startup["configurationDigest"],
            identity.runtime_config_digest,
        )
        self.assertEqual(identity.attempt_id, "attempt-alpha-1")
        self.assertEqual(
            identity.elasticsearch_compose_digest,
            _digest("es-compose"),
        )
        self.assertTrue(identity.local_capture_sms_enabled)

    def test_rejects_any_runtime_or_startup_identity_drift(self) -> None:
        changes = {
            "stopped": {"status": "stopped"},
            "bounded workload": {"workload": "content-commercial"},
            "candidate": {"candidateDigest": _digest("other-baseline")},
            "startup service configuration": {
                "configurationDigest": _digest("other-service-configuration")
            },
            "Provider": {"providerRuntimeDigest": _digest("other-provider")},
            "Elasticsearch": {
                "observabilityLogSinkDigest": _digest("other-es")
            },
            "unknown attempt": {"attemptId": "unknown"},
        }
        for label, change in changes.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory(
                    prefix="qwq-provider-patrol-"
                ) as temporary:
                    candidate_root = Path(temporary)
                    manifest, startup = _runtime_fixture(candidate_root)
                    startup.update(change)
                    with self.assertRaisesRegex(
                        ValueError,
                        "running full startup receipt",
                    ):
                        self._load(candidate_root, manifest, startup)

    def test_rejects_provider_elasticsearch_and_runtime_package_drift(self) -> None:
        mutations = {
            "Provider bindings": lambda manifest: manifest["providerRuntime"][
                "composition"
            ].update({"bindings": []}),
            "Elasticsearch adapter": lambda manifest: manifest[
                "observabilityLogSink"
            ].update({"adapterId": "ext.obs.other"}),
            "environment runtime digest": lambda manifest: manifest.update(
                {"environmentRuntimeDigest": _digest("other-runtime-bytes")}
            ),
            "service configuration": lambda manifest: manifest.update(
                {"configurationDigest": _digest("other-service-configuration")}
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory(
                    prefix="qwq-provider-patrol-"
                ) as temporary:
                    candidate_root = Path(temporary)
                    manifest, startup = _runtime_fixture(candidate_root)
                    mutated = deepcopy(manifest)
                    mutate(mutated)
                    with self.assertRaises(ValueError):
                        self._load(candidate_root, mutated, startup)

    def test_atomically_appends_only_nonsecret_runtime_and_broker_tls_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-provider-report-") as temporary:
            root = Path(temporary)
            manifest, startup = _runtime_fixture(root)
            identity = self._load(root, manifest, startup)
            report_path = root / "provider.patrol-report.json"
            report = {
                "suiteId": "environment_page_smoke",
                "status": "passed",
                "runtimeEnv": "alpha",
                "apiContractEnv": "alpha",
                "candidateDigest": identity.baseline_id,
                "caseResults": [{"caseId": "unchanged"}],
            }
            report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
            report_path.chmod(0o640)
            binding = ProtectedOTPBrokerBinding(
                url="https://127.0.0.1:49152/v1/otp",
                token="must-never-appear-in-evidence",
                ca_digest=_digest("ca"),
                certificate_digest=_digest("certificate"),
            )

            subject._bind_runtime_evidence_to_patrol_report(
                report_path,
                identity=identity,
                binding=binding,
            )
            rendered = report_path.read_text(encoding="utf-8")
            updated = json.loads(rendered)

            self.assertEqual(updated["caseResults"], report["caseResults"])
            evidence = updated["runtimeIdentityEvidence"]
            self.assertEqual(evidence["startup"]["attemptId"], "attempt-alpha-1")
            self.assertEqual(
                evidence["elasticsearch"]["composeDigest"],
                _digest("es-compose"),
            )
            self.assertEqual(
                evidence["protectedOtpBrokerTls"]["caDigest"],
                binding.ca_digest,
            )
            self.assertNotIn(binding.token, rendered)
            self.assertNotIn(binding.url, rendered)
            self.assertEqual(report_path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(list(root.glob(f".{report_path.name}.*.tmp")), [])
            with self.assertRaisesRegex(ValueError, "runtime identity mismatch"):
                subject._bind_runtime_evidence_to_patrol_report(
                    report_path,
                    identity=identity,
                    binding=binding,
                )

    def test_report_candidate_identity_cannot_use_package_digest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-provider-report-") as temporary:
            root = Path(temporary)
            manifest, startup = _runtime_fixture(root)
            identity = self._load(root, manifest, startup)
            report_path = root / "provider.patrol-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "suiteId": "environment_page_smoke",
                        "runtimeEnv": "alpha",
                        "apiContractEnv": "alpha",
                        "candidateDigest": identity.package_digest,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            before = report_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "runtime identity mismatch"):
                subject._bind_runtime_evidence_to_patrol_report(
                    report_path,
                    identity=identity,
                    binding=None,
                )
            self.assertEqual(report_path.read_bytes(), before)

    def test_report_with_broker_token_is_rejected_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-provider-report-") as temporary:
            root = Path(temporary)
            manifest, startup = _runtime_fixture(root)
            identity = self._load(root, manifest, startup)
            binding = ProtectedOTPBrokerBinding(
                url="https://127.0.0.1:49152/v1/otp",
                token="must-never-appear-in-evidence",
                ca_digest=_digest("ca"),
                certificate_digest=_digest("certificate"),
            )
            report_path = root / "provider.patrol-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "suiteId": "environment_page_smoke",
                        "runtimeEnv": "alpha",
                        "apiContractEnv": "alpha",
                        "candidateDigest": identity.baseline_id,
                        "unsafe": binding.token,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            before = report_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "exposed"):
                subject._bind_runtime_evidence_to_patrol_report(
                    report_path,
                    identity=identity,
                    binding=binding,
                )
            self.assertEqual(report_path.read_bytes(), before)

    def test_broker_url_validation_forbids_cleartext_and_url_smuggling(self) -> None:
        valid = ProtectedOTPBrokerBinding(
            url="https://127.0.0.1:49152/v1/otp",
            token="secret",
            ca_digest=_digest("ca"),
            certificate_digest=_digest("certificate"),
        )
        self.assertEqual(subject._validated_broker_port(valid), 49152)
        for url in (
            "http://127.0.0.1:49152/v1/otp",
            "https://localhost:49152/v1/otp",
            "https://user@127.0.0.1:49152/v1/otp",
            "https://127.0.0.1:49152/v1/otp?token=x",
            "https://127.0.0.1:49152/v1/otp#fragment",
            "https://127.0.0.1:49152/other",
        ):
            with self.subTest(url=url):
                invalid = ProtectedOTPBrokerBinding(
                    url=url,
                    token="secret",
                    ca_digest=valid.ca_digest,
                    certificate_digest=valid.certificate_digest,
                )
                with self.assertRaisesRegex(ValueError, "exact HTTPS loopback"):
                    subject._validated_broker_port(invalid)


if __name__ == "__main__":
    unittest.main()
