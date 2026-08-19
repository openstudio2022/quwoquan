"""Lock nonprod Provider Patrol to its current running runtime identity.

spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#req-002
"""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import os
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


def _mutable_fixture(
    root: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    media_root = root / "target-local/cache/media"
    media_root.mkdir(parents=True)
    compose_root = root / "mutable-runtime/compose"
    compose_root.mkdir(parents=True)
    provider_path = compose_root / "00-provider.json"
    provider_path.write_text(
        json.dumps(
            {
                "services": {
                    "provider-protocol-substitute": {
                        "build": {"context": "/safe/provider"},
                        "environment": {
                            "PROVIDER_SUBSTITUTE_OPERATOR_TOKEN": "${TOKEN:?required}",
                            "QWQ_PROVIDER_RUNTIME_DIGEST": "${DIGEST:?required}",
                            "PROVIDER_SUBSTITUTE_TLS_CERT_FILE": "/run/server.crt",
                            "PROVIDER_SUBSTITUTE_TLS_KEY_FILE": "/run/server.key",
                        },
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sms_path = compose_root / "01-sms.json"
    sms_path.write_text(
        json.dumps(
            {
                "services": {
                    "sms-provider-substitute": {
                        "build": {"context": "/safe/sms"},
                        "environment": {
                            "SMS_SUBSTITUTE_OPERATOR_TOKEN": "${OPERATOR:?required}",
                            "SMS_SUBSTITUTE_PROVIDER_TOKEN": "${PROVIDER:?required}",
                            "SMS_SUBSTITUTE_CAPTURE_KEY_B64": "${CAPTURE:?required}",
                            "SMS_SUBSTITUTE_TLS_CERT_FILE": "/run/server.crt",
                            "SMS_SUBSTITUTE_TLS_KEY_FILE": "/run/server.key",
                        },
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    provider_digest = _digest("mutable-provider-runtime")
    receipt: dict[str, object] = {
        "schema": "stackctl.mutable_test_live_startup_attempt",
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "unbound",
        "attemptId": "alpha-test-live-1234567890abcdef",
        "environment": "alpha",
        "target": "alpha-local",
        "status": "running",
        "workload": "full",
        "composeProject": "quwoquan_alpha_test_live",
        "composeDigest": _digest("mutable-compose"),
        "configurationDigest": _digest("mutable-config"),
        "providerRuntimeDigest": provider_digest,
        "portProfile": "alpha-local",
        "portBlock": {"start": 17000, "end": 17999},
        "publishedPorts": {
            "provider-protocol-substitute": 17360,
            "sms-provider-substitute": 17330,
        },
        "tlsProfile": "local-managed",
        "resolverHandoffDigest": _digest("resolver"),
        "publicWebPackage": {
            "environment": "alpha",
            "packageVersion": "web-release-alpha",
            "manifestDigest": _digest("web-manifest"),
            "contentDigest": _digest("web-content"),
            "publicOrigin": "https://alpha.quwoquan.com:17000",
        },
        "sourceRevision": "a" * 40,
        "workspaceStatusDigest": _digest("workspace-status"),
        "mutableStateDigest": _digest("mutable-state"),
        "runRoot": str(root.resolve()),
        "failure": None,
    }
    relative_provider = provider_path.relative_to(subject.ROOT).as_posix()
    relative_sms = sms_path.relative_to(subject.ROOT).as_posix()
    plan = {
        "schema": "stackctl.mutable_test_live_runtime",
        "environment": "alpha",
        "target": "alpha-local",
        "composeProject": receipt["composeProject"],
        "portProfile": receipt["portProfile"],
        "portBlock": receipt["portBlock"],
        "publishedPorts": receipt["publishedPorts"],
        "composeFiles": [
            "quwoquan_ops/external/provider-protocol-substitute/deploy/compose.yaml",
            "quwoquan_ops/external/sms-provider-substitute/deploy/compose.yaml",
        ],
        "executionComposeFiles": [relative_provider, relative_sms],
        "composeProfiles": [
            "nonprod-provider-protocol-substitute",
            "nonprod-sms-provider-substitute",
        ],
        "composeDigest": receipt["composeDigest"],
        "configurationDigest": receipt["configurationDigest"],
        "providerRuntimeDigest": receipt["providerRuntimeDigest"],
        "mediaLocalRef": "cache/media",
        "mediaRoot": media_root.relative_to(subject.ROOT).as_posix(),
        "tlsProfile": receipt["tlsProfile"],
        "resolverHandoffDigest": receipt["resolverHandoffDigest"],
        "publicWebPackage": receipt["publicWebPackage"],
        "graphqlReadRegistry": {
            "schema": "gateway.graphql_read.runtime_registry",
            "configVersion": _digest("graphql-read-config"),
        },
        "serviceCoreModules": [],
        "workspaceIdentity": {
            "sourceRevision": receipt["sourceRevision"],
            "workspaceStatusDigest": receipt["workspaceStatusDigest"],
            "mutableStateDigest": receipt["mutableStateDigest"],
        },
    }
    (root / "mutable-runtime-plan.json").write_text(
        json.dumps(plan) + "\n",
        encoding="utf-8",
    )
    composition = {
        "runtimeCompositionDigest": provider_digest,
        "bindingDigest": _digest("bindings"),
        "bindings": [
            {
                "capabilityId": "identity.sms.otp",
                "state": "enabled",
                "adapterId": "ext.sms.local_capture",
                "endpointRef": "local_topology:sms-provider-substitute",
            }
        ],
        "workloads": [
            {
                "role": "provider-protocol-substitute",
                "adapterIds": ["ext.llm.protocol_fixture"],
                "capabilityIds": ["assistant.model.generation"],
                "contractDigest": _digest("provider-contract"),
                "composeDigest": _digest("provider-compose"),
            },
            {
                "role": "sms-provider-substitute",
                "adapterIds": ["ext.sms.local_capture"],
                "capabilityIds": ["identity.sms.otp"],
                "contractDigest": _digest("sms-contract"),
                "composeDigest": _digest("sms-compose"),
            },
        ],
    }
    return receipt, composition


def _mutable_target_contract() -> dict[str, object]:
    return {
        "publicBases": {
            "api": "https://api.alpha.quwoquan.com",
            "productOps": "https://product-ops.alpha.quwoquan.com",
        },
        "dataRelease": {"mode": "local-import", "mediaLocalRef": "cache/media"},
    }


class ProviderPatrolRuntimeIdentityContractTest(unittest.TestCase):
    def _mutable_root(self) -> tempfile.TemporaryDirectory[str]:
        parent = subject.ROOT / ".qwq_output/env/alpha/runs"
        parent.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(
            prefix="qwq-provider-patrol-mutable-",
            dir=parent,
        )

    def _load(
        self,
        candidate_root: Path,
        manifest: dict[str, object],
        startup: dict[str, object],
    ) -> subject.ProviderPatrolRuntimeIdentity:
        with (
            mock.patch.object(
                subject,
                "deployment_candidate_dir",
                return_value=candidate_root,
            ) as candidate_dir,
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
                "alpha",
                "alpha-local",
                candidate_digest=str(manifest["baselineId"]),
                startup_attempt_id=str(startup["attemptId"]),
                provider_runtime_digest=str(startup["providerRuntimeDigest"]),
            )
        candidate_dir.assert_called_once_with(
            "alpha-local",
            manifest["baselineId"],
        )
        load_manifest.assert_called_once_with(
            "alpha",
            "alpha-local",
            manifest["baselineId"],
            require_full=True,
        )
        return identity

    def test_loads_package_provider_es_release_and_running_attempt_identity(
        self,
    ) -> None:
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
                        "running full startup receipt|selected startup attempt",
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

    def test_running_mutable_test_live_binds_rendered_provider_and_sms_identity(
        self,
    ) -> None:
        with self._mutable_root() as temporary:
            root = Path(temporary)
            receipt, composition = _mutable_fixture(root)
            with (
                mock.patch.object(
                    subject,
                    "compile_provider_runtime_composition",
                    return_value=composition,
                ),
                mock.patch.object(
                    subject,
                    "validate_provider_runtime_composition",
                    side_effect=lambda value, **_kwargs: value,
                ),
                mock.patch.object(
                    subject,
                    "load_environment_topology",
                    return_value={"targets": {}},
                ),
                mock.patch.object(
                    subject,
                    "get_target",
                    return_value=_mutable_target_contract(),
                ),
                mock.patch.object(
                    subject,
                    "target_local_dir",
                    return_value=root / "target-local",
                ),
            ):
                identity = subject._load_mutable_test_live_runtime_identity(
                    "alpha",
                    "alpha-local",
                    receipt,
                )

        self.assertEqual(identity.launch_policy, "test_live")
        self.assertTrue(identity.non_promotable)
        self.assertEqual(identity.baseline_id, receipt["composeDigest"])
        self.assertEqual(
            identity.provider_runtime_digest,
            composition["runtimeCompositionDigest"],
        )
        self.assertEqual(identity.sms_published_port, 17330)
        self.assertEqual(
            [item["role"] for item in identity.provider_workloads],
            ["provider-protocol-substitute", "sms-provider-substitute"],
        )
        evidence = subject._runtime_evidence(identity, None)
        self.assertEqual(evidence["launchPolicy"], "test_live")
        self.assertTrue(evidence["nonPromotable"])
        self.assertNotIn("release", evidence)
        self.assertNotIn("packageDigest", evidence)
        self.assertEqual(
            evidence["smsProvider"],
            {
                "adapterId": "ext.sms.local_capture",
                "endpointRef": "local_topology:sms-provider-substitute",
                "publishedPort": 17330,
            },
        )
        self.assertNotIn("TOKEN", json.dumps(evidence))

    def test_mutable_receipt_or_rendered_provider_drift_is_fail_closed(self) -> None:
        cases = ("partial", "plan-drift", "sms-secret-shape", "binding-drift")
        for case in cases:
            with self.subTest(case=case), self._mutable_root() as temporary:
                root = Path(temporary)
                receipt, composition = _mutable_fixture(root)
                if case == "partial":
                    receipt["status"] = "partial"
                elif case == "plan-drift":
                    plan_path = root / "mutable-runtime-plan.json"
                    plan = json.loads(plan_path.read_text(encoding="utf-8"))
                    plan["configurationDigest"] = _digest("other-config")
                    plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
                elif case == "sms-secret-shape":
                    sms_path = root / "mutable-runtime/compose/01-sms.json"
                    payload = json.loads(sms_path.read_text(encoding="utf-8"))
                    del payload["services"]["sms-provider-substitute"]["environment"][
                        "SMS_SUBSTITUTE_CAPTURE_KEY_B64"
                    ]
                    sms_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
                else:
                    composition["runtimeCompositionDigest"] = _digest("drift")
                with (
                    mock.patch.object(
                        subject,
                        "compile_provider_runtime_composition",
                        return_value=composition,
                    ),
                    mock.patch.object(
                        subject,
                        "validate_provider_runtime_composition",
                        side_effect=lambda value, **_kwargs: value,
                    ),
                    mock.patch.object(
                        subject,
                        "load_environment_topology",
                        return_value={"targets": {}},
                    ),
                    mock.patch.object(
                        subject,
                        "get_target",
                        return_value=_mutable_target_contract(),
                    ),
                    mock.patch.object(
                        subject,
                        "target_local_dir",
                        return_value=root / "target-local",
                    ),
                ):
                    with self.assertRaises(ValueError):
                        subject._load_mutable_test_live_runtime_identity(
                            "alpha",
                            "alpha-local",
                            receipt,
                        )

    def test_mutable_media_binding_rejects_escape_symlink_and_drift(self) -> None:
        cases = ("topology-escape", "ref-drift", "root-drift", "symlink")
        for case in cases:
            with self.subTest(case=case), self._mutable_root() as temporary:
                root = Path(temporary)
                receipt, _ = _mutable_fixture(root)
                target = _mutable_target_contract()
                plan_path = root / "mutable-runtime-plan.json"
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                if case == "topology-escape":
                    target["dataRelease"]["mediaLocalRef"] = "../media"
                elif case == "ref-drift":
                    plan["mediaLocalRef"] = "cache/other"
                elif case == "root-drift":
                    plan["mediaRoot"] = (root / "target-local/cache/other").relative_to(
                        subject.ROOT
                    ).as_posix()
                else:
                    cache = root / "target-local/cache"
                    real_cache = root / "target-local/real-cache"
                    cache.rename(real_cache)
                    cache.symlink_to(real_cache, target_is_directory=True)
                plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
                with (
                    mock.patch.object(subject, "target_local_dir", return_value=root / "target-local"),
                    self.assertRaises(ValueError),
                ):
                    subject._load_mutable_runtime_plan(
                        receipt,
                        target_contract=target,
                    )

    def test_direct_selector_requires_explicit_runtime_identity_handoff(self) -> None:
        with (
            mock.patch.dict(
                os.environ,
                {
                    key: value
                    for key, value in os.environ.items()
                    if key != "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"
                },
                clear=True,
            ),
            mock.patch.object(
                subject,
                "load_test_live_startup_attempt",
                side_effect=AssertionError("missing handoff must not scan receipts"),
            ),
            self.assertRaisesRegex(ValueError, "runtime identity handoff is required"),
        ):
            subject._select_nonprod_runtime_identity("alpha", "alpha-local")

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
                ca_certificate_base64=base64.b64encode(b"ca").decode("ascii"),
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
                ca_certificate_base64=base64.b64encode(b"ca").decode("ascii"),
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
            ca_certificate_base64=base64.b64encode(b"ca").decode("ascii"),
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
                    ca_certificate_base64=valid.ca_certificate_base64,
                )
                with self.assertRaisesRegex(ValueError, "exact HTTPS loopback"):
                    subject._validated_broker_port(invalid)


if __name__ == "__main__":
    unittest.main()
