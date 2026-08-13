# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""active candidate 身份绑定的本地契约。

由 test_provider_conformance_evidence__contract__local_contract_test.py
（Python 1000 行硬顶治理）按场景拆出：nonprod startup receipt 与 prod
native readback 必须与当前候选的 image/config/contract-graph 摘要一致，
过期候选一律拒绝。测试逐字搬移。
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.cli.lib import provider_conformance


class ProviderConformanceEvidenceContractTest(unittest.TestCase):
    def test_nonprod_active_candidate_requires_current_startup_identity(self) -> None:
        baseline = "sha256:" + "1" * 64
        runtime_image = "sha256:" + "2" * 64
        runtime_config = "sha256:" + "3" * 64
        service_configuration = "sha256:" + "8" * 64
        package_image = "sha256:" + "4" * 64
        build_input = "sha256:" + "5" * 64
        provider_image = "sha256:" + "6" * 64
        contract_graph = "sha256:" + "7" * 64
        commit = "a" * 40
        startup = {
            "target": "alpha-local",
            "env": "alpha",
            "status": "running",
            "workload": "full",
            "candidateDigest": baseline,
            "configurationDigest": service_configuration,
            "imageTransportTag": provider_conformance.immutable_image_digest(
                {"assistant-service": runtime_image}
            ),
            "imageComposition": {
                "images": {"assistant-service": {"ref": runtime_image}}
            },
        }
        active = {"baselineId": baseline}
        manifest = {
            "baselineId": baseline,
            "sourceRevision": commit,
            "configurationDigest": service_configuration,
            "runtimeConfigDigest": runtime_config,
            "imageDigest": package_image,
            "buildInputDigest": build_input,
        }
        oci = {
            "schema": "stackctl-package-oci-images",
            "environment": "alpha",
            "target": "alpha-local",
            "configurationDigest": service_configuration,
            "imageDigest": package_image,
            "buildInputDigest": build_input,
            "images": {
                "assistant-service": {
                    "ref": "qwq/assistant-service:build",
                    "imageDigest": runtime_image,
                }
            },
        }

        def issues(
            receipt: dict[str, object],
            *,
            oci_payload: dict[str, object] = oci,
        ) -> list[str]:
            return provider_conformance._nonprod_active_candidate_issues(
                environment="alpha",
                target="alpha-local",
                startup=receipt,
                active=active,
                manifest=manifest,
                oci=oci_payload,
                commit=commit,
                image_digest=provider_image,
                contract_graph_digest=contract_graph,
                expected_image_digest=provider_image,
                expected_contract_graph_digest=contract_graph,
            )

        self.assertEqual(issues(startup), [])
        stopped = {**startup, "status": "stopped"}
        self.assertTrue(any("not running" in issue for issue in issues(stopped)))
        missing_candidate = {**startup, "candidateDigest": None}
        self.assertTrue(
            any("candidateDigest" in issue for issue in issues(missing_candidate))
        )
        stale_config = {
            **startup,
            "configurationDigest": "sha256:" + "9" * 64,
        }
        self.assertTrue(
            any("configuration digest is stale" in issue for issue in issues(stale_config))
        )
        stale_oci = {**oci, "configurationDigest": "sha256:" + "a" * 64}
        self.assertTrue(
            any(
                "configuration digest is stale" in issue
                for issue in issues(startup, oci_payload=stale_oci)
            )
        )
        stale_image = deepcopy(startup)
        stale_image["imageComposition"]["images"]["assistant-service"]["ref"] = (
            "sha256:" + "9" * 64
        )
        self.assertTrue(
            any("runtime image is stale" in issue for issue in issues(stale_image))
        )

        with mock.patch.object(
            provider_conformance,
            "load_startup_attempt",
            return_value=None,
        ):
            resolved = provider_conformance.resolve_nonprod_active_candidate(
                environment="alpha",
                registry={},
                commit=commit,
                image_digest=provider_image,
                contract_graph_digest=contract_graph,
            )
        self.assertFalse(resolved["active"])
        self.assertIn("missing", str(resolved["reason"]))
        with (
            mock.patch.object(
                provider_conformance,
                "load_startup_attempt",
                return_value=startup,
            ),
            mock.patch.object(
                provider_conformance,
                "can_reuse_package",
                return_value=(False, "package content digest mismatch"),
            ) as package_reuse,
        ):
            stale_package = provider_conformance.resolve_nonprod_active_candidate(
                environment="alpha",
                registry={},
                commit=commit,
                image_digest=provider_image,
                contract_graph_digest=contract_graph,
            )
        self.assertFalse(stale_package["active"])
        self.assertIn("package content digest mismatch", str(stale_package["reason"]))
        package_reuse.assert_called_once_with("alpha", "alpha-local")
        claimed_active = {
            "candidateStatus": "active_immutable",
            "candidateReceiptRef": ".qwq_output/env/alpha/process/startup_attempt.json",
            "candidateReceiptDigest": "sha256:" + "9" * 64,
            "environment": "alpha",
            "commit": commit,
            "imageDigest": provider_image,
            "contractGraphDigest": contract_graph,
        }
        with mock.patch.object(
            provider_conformance,
            "resolve_nonprod_active_candidate",
            return_value={
                "active": False,
                "receiptRef": "",
                "receiptDigest": "",
                "reason": "startup receipt status is not running",
            },
        ):
            receipt_issues = provider_conformance.active_candidate_receipt_issues(
                claimed_active,
                registry={},
                root=Path("/tmp"),
            )
        self.assertTrue(
            any("not backed by the current canonical startup receipt" in issue for issue in receipt_issues)
        )

    def test_prod_active_candidate_requires_matching_native_readback(self) -> None:
        digest = "sha256:" + "a" * 64
        readiness = {"bindingPreflightReceiptRef": "receipt:preflight"}
        case_result = {"releaseReadiness": readiness}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".qwq_output"
            run_root = root / "env/prod/runs/provider"
            run_root.mkdir(parents=True)
            case_path = run_root / "case-results.json"
            readback_path = run_root / "provider.native-device-readback.json"
            payload = {
                "schema": provider_conformance.REMOTE_READBACK_SCHEMA,
                "status": "passed",
                "capabilityId": "rtc.room.transport",
                "adapterId": "infra.livekit_sfu",
                "imageDigest": digest,
                "configDigest": digest,
                "contractGraphDigest": digest,
                "adapterDigest": digest,
                "releaseReadiness": readiness,
            }
            raw = json.dumps(payload, sort_keys=True).encode("utf-8")
            readback_path.write_bytes(raw)
            case_result["nativeReadback"] = {
                "artifactName": readback_path.name,
                "artifactDigest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            }
            with mock.patch.dict(
                os.environ,
                {"QWQ_OUTPUT_ROOT": str(root)},
                clear=False,
            ):
                valid = provider_conformance.resolve_prod_active_candidate(
                    case_result_path=case_path,
                    case_result=case_result,
                    capability_id="rtc.room.transport",
                    adapter_id="infra.livekit_sfu",
                    image_digest=digest,
                    config_digest=digest,
                    contract_graph_digest=digest,
                    adapter_digest=digest,
                )
                missing = provider_conformance.resolve_prod_active_candidate(
                    case_result_path=case_path,
                    case_result={"releaseReadiness": readiness},
                    capability_id="rtc.room.transport",
                    adapter_id="infra.livekit_sfu",
                    image_digest=digest,
                    config_digest=digest,
                    contract_graph_digest=digest,
                    adapter_digest=digest,
                )
                stale = provider_conformance.resolve_prod_active_candidate(
                    case_result_path=case_path,
                    case_result=case_result,
                    capability_id="rtc.room.transport",
                    adapter_id="infra.livekit_sfu",
                    image_digest="sha256:" + "b" * 64,
                    config_digest=digest,
                    contract_graph_digest=digest,
                    adapter_digest=digest,
                )
        self.assertTrue(valid["active"])
        self.assertRegex(str(valid["receiptDigest"]), r"^sha256:[a-f0-9]{64}$")
        self.assertFalse(missing["active"])
        self.assertFalse(stale["active"])


if __name__ == "__main__":
    unittest.main()
