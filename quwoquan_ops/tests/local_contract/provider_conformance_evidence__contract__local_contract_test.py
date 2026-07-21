from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance


os.environ.setdefault(
    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY",
    "provider-conformance-local-contract-key",
)


CAPABILITY_ID = "identity.sms.otp"
ALPHA_ADAPTER_ID = "ext.sms.mock"
PRODUCTION_ADAPTER_ID = "ext.sms.aliyun"


def _digest(seed: str) -> str:
    return f"sha256:{seed * 64}"[:71]


def _assertion_ids(profile: str) -> list[str]:
    manifest = governance.load_conformance_manifest()
    return [
        *manifest["common_assertion_ids"],
        *manifest["profile_assertion_ids"][profile],
    ]


def _binding_roots(capability_id: str = CAPABILITY_ID) -> list[str]:
    capability = next(
        item
        for item in governance.load_registry()["capabilities"]
        if item["capability_id"] == capability_id
    )
    return [root["root_id"] for root in capability["binding_roots"]]


def _release_readiness() -> dict[str, str]:
    return {
        "switchCompatibilityReceiptRef": "receipt:gamma:switch-compatible",
        "callbackDrainReceiptRef": "receipt:gamma:callback-drained",
        "lastGoodReceiptRef": "receipt:gamma:last-good",
        "rollbackReceiptRef": "receipt:gamma:rollback-verified",
        "prodBindingPreflightReceiptRef": "receipt:prod:binding-preflight",
    }


def _compiled_with_mixed_sms_bindings() -> tuple[dict[str, object], dict[str, object]]:
    registry = deepcopy(governance.load_registry())
    bindings = deepcopy(governance.load_bindings())
    bindings["environments"]["alpha"]["capabilities"].append(
        {
            "capability_id": CAPABILITY_ID,
            "state": "enabled",
            "adapter_id": ALPHA_ADAPTER_ID,
            "endpoint_ref": "not_configured",
            "secret_refs": [],
        }
    )
    for environment in ("beta", "gamma", "prod"):
        binding = next(
            binding
            for binding in bindings["environments"][environment]["capabilities"]
            if binding["capability_id"] == CAPABILITY_ID
        )
        binding["state"] = "enabled"
    compiled, issues = governance.compile_governance(
        registry,
        bindings,
        governance.load_conformance_manifest(),
    )
    assert not any(issue.location.startswith("bindings.") for issue in issues)
    return registry, compiled


def _evidence(
    *,
    root: Path,
    environment: str,
    layer: str,
    adapter_id: str,
    assertion_count: int | None = None,
    config_digest: str | None = None,
    image_digest: str | None = None,
) -> dict[str, object]:
    artifact = root / (
        f"env/{environment}/runs/provider/"
        f"provider-conformance-{CAPABILITY_ID.replace('.', '-')}-{layer}.report.json"
    )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    assertion_ids = _assertion_ids("message_transport")
    executed_at = datetime.now(timezone.utc).isoformat()
    evidence = {
        "schema": "provider-conformance-evidence",
        "version": 1,
        "adapterId": adapter_id,
        "capabilityId": CAPABILITY_ID,
        "bindingRoots": _binding_roots(),
        "environment": environment,
        "testLayer": layer,
        "executionProfile": provider_conformance.CELL_PROFILES[(environment, layer)],
        "status": "passed",
        "executedAt": executed_at,
        "artifactRef": (
            f".qwq_output/env/{environment}/runs/provider/"
            f"provider-conformance-{CAPABILITY_ID.replace('.', '-')}-{layer}.report.json"
        ),
        "artifactDigest": "",
        "artifactAttestation": "",
        "commit": "a" * 40,
        "imageDigest": image_digest or _digest("a"),
        "configDigest": config_digest or _digest("b"),
        "contractGraphDigest": _digest("c"),
        "adapterDigest": _digest("d"),
        "assertionCount": len(assertion_ids) if assertion_count is None else assertion_count,
        "assertionIds": assertion_ids,
        "networkBoundary": {
            "local_contract": "offline_harness",
            "api_integration": "remote_protocol",
            "user_acceptance": "user_journey",
        }[layer],
        "dataDigest": _digest("e"),
        "cleanupReceipt": f"cleanup-{environment}-{layer}",
        "acceptanceRefs": [
            "specs/feature-tree/runtime/runtime-external-integration/acceptance.yaml#SIT3_provider_conformance_3x3"
        ],
        "observabilityRefs": {
            "logs": [f"log://{environment}/{layer}"],
            "traces": [f"trace://{environment}/{layer}"],
            "metrics": [f"metric://{environment}/{layer}"],
        },
    }
    if environment == "gamma" and layer == "user_acceptance":
        evidence["releaseReadiness"] = _release_readiness()
    test_source = governance.load_conformance_manifest()["profiles"]["message_transport"][
        layer
    ]
    report = {
        "schema": provider_conformance.EXECUTION_REPORT_SCHEMA,
        "version": provider_conformance.EXECUTION_REPORT_VERSION,
        "adapterId": adapter_id,
        "capabilityId": CAPABILITY_ID,
        "bindingRoots": evidence["bindingRoots"],
        "environment": environment,
        "testLayer": layer,
        "executionProfile": evidence["executionProfile"],
        "status": evidence["status"],
        "executedAt": executed_at,
        "commit": evidence["commit"],
        "imageDigest": evidence["imageDigest"],
        "configDigest": evidence["configDigest"],
        "contractGraphDigest": evidence["contractGraphDigest"],
        "adapterDigest": evidence["adapterDigest"],
        "assertionIds": assertion_ids,
        "networkBoundary": evidence["networkBoundary"],
        "dataDigest": evidence["dataDigest"],
        "testSource": test_source,
        "testCommand": "fixture provider conformance command",
        "exitCode": 0,
    }
    artifact_bytes = json.dumps(
        report,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    artifact.write_bytes(artifact_bytes)
    evidence["artifactDigest"] = f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}"
    evidence["artifactAttestation"] = provider_conformance.sign_execution_report(
        artifact_bytes
    )
    return evidence


def _rewrite_report_for_evidence(*, root: Path, evidence: dict[str, object]) -> None:
    artifact = root / Path(*Path(str(evidence["artifactRef"])).parts[1:])
    report = json.loads(artifact.read_text(encoding="utf-8"))
    for field in (
        "adapterId",
        "capabilityId",
        "bindingRoots",
        "environment",
        "testLayer",
        "executionProfile",
        "status",
        "executedAt",
        "commit",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
    ):
        report[field] = evidence[field]
    artifact_bytes = json.dumps(
        report,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    artifact.write_bytes(artifact_bytes)
    evidence["artifactDigest"] = f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}"
    evidence["artifactAttestation"] = provider_conformance.sign_execution_report(
        artifact_bytes
    )


def _matrix_evidence(
    *,
    root: Path,
    config_digests: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    adapter_by_environment = {
        "alpha": ALPHA_ADAPTER_ID,
        "beta": PRODUCTION_ADAPTER_ID,
        "gamma": PRODUCTION_ADAPTER_ID,
    }
    return [
        _evidence(
            root=root,
            environment=environment,
            layer=layer,
            adapter_id=adapter_by_environment[environment],
            config_digest=(config_digests or {}).get(environment),
        )
        for environment in provider_conformance.ENVIRONMENTS
        for layer in provider_conformance.LAYERS
    ]


def test_conformance_evidence_rejects_zero_assertion_pass() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
            assertion_count=0,
        )
        issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any("assertionCount must be greater than zero" in issue for issue in issues)


def test_conformance_evidence_rejects_empty_or_unlinked_execution_artifact() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
        )
        artifact = root / Path(*Path(str(evidence["artifactRef"])).parts[1:])
        artifact.write_text("{}\n", encoding="utf-8")
        issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any("execution report missing fields" in issue for issue in issues)


def test_conformance_evidence_requires_adapter_profile_test_source() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
        )
        artifact = root / Path(*Path(str(evidence["artifactRef"])).parts[1:])
        report = json.loads(artifact.read_text(encoding="utf-8"))
        report["testSource"] = "unrelated/test.py"
        artifact_bytes = json.dumps(
            report,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        artifact.write_bytes(artifact_bytes)
        evidence["artifactDigest"] = (
            f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}"
        )
        issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any("testSource does not match" in issue for issue in issues)


def test_conformance_evidence_requires_execution_report_digest_match() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
        )
        evidence["artifactDigest"] = _digest("f")
        issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any("artifactDigest does not match" in issue for issue in issues)


def test_conformance_evidence_rejects_untrusted_execution_attestation() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
        )
        evidence["artifactAttestation"] = f"hmac-sha256:{'0' * 64}"
        issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any("artifactAttestation is not trusted" in issue for issue in issues)


def test_execution_attestation_covers_binding_roots() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
        )
        artifact = root / Path(*Path(str(evidence["artifactRef"])).parts[1:])
        report = json.loads(artifact.read_text(encoding="utf-8"))
        report["bindingRoots"] = ["attestation-tampered-root"]
        artifact_bytes = json.dumps(
            report,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        artifact.write_bytes(artifact_bytes)
        evidence["artifactDigest"] = (
            f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}"
        )
        issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any("artifactAttestation is not trusted" in issue for issue in issues)


def test_conformance_evidence_rejects_fabricated_or_omitted_binding_roots() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
        )
        evidence["bindingRoots"] = []
        _rewrite_report_for_evidence(root=root, evidence=evidence)
        omitted_issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )
        evidence["bindingRoots"] = ["fabricated-root"]
        _rewrite_report_for_evidence(root=root, evidence=evidence)
        fabricated_issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any("bindingRoots must be a non-empty" in issue for issue in omitted_issues)
    assert any(
        "bindingRoots must strictly match registry/compiled capability roots" in issue
        for issue in fabricated_issues
    )


def test_shared_message_transport_evidence_requires_all_compiled_roots() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id="infra.redis.message_transport_fixture",
        )
        capability_id = provider_conformance.MESSAGE_TRANSPORT_CAPABILITY_ID
        message_transport_roots = [
            root["root_id"]
            for root in provider_conformance.compiled_capability_binding_roots(
                compiled,
                capability_id=capability_id,
            )
        ]
        assert len(message_transport_roots) > 1
        evidence["adapterId"] = "infra.redis.message_transport_fixture"
        evidence["capabilityId"] = capability_id
        evidence["bindingRoots"] = message_transport_roots[:-1]
        evidence["observabilityRefs"]["metrics"].extend(
            provider_conformance.required_metric_refs(capability_id)
        )
        _rewrite_report_for_evidence(root=root, evidence=evidence)
        omitted_issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )
        evidence["bindingRoots"] = list(reversed(message_transport_roots))
        _rewrite_report_for_evidence(root=root, evidence=evidence)
        reordered_issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any(
        "bindingRoots must strictly match registry/compiled capability roots" in issue
        for issue in omitted_issues
    )
    assert any(
        "bindingRoots must strictly match registry/compiled capability roots" in issue
        for issue in reordered_issues
    )


def test_conformance_evidence_rejects_registry_compiled_root_drift() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
        )
        compiled["capabilityBindingRoots"][CAPABILITY_ID].append(
            {
                **compiled["capabilityBindingRoots"][CAPABILITY_ID][0],
                "root_id": "compiler-only-root",
            }
        )
        issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any(
        "registry and compiled capability binding roots diverge" in issue
        for issue in issues
    )


def test_conformance_evidence_fails_closed_without_ci_attestation_key() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
        )
        signing_key = os.environ.pop("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY")
        try:
            issues = provider_conformance.validate_evidence(
                [evidence],
                registry=registry,
                root=root,
                compiled=compiled,
            )
        finally:
            os.environ["QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"] = signing_key

    assert any("ATTESTATION_KEY is required" in issue for issue in issues)


def test_mixed_selected_adapters_make_capability_ready_without_illegal_alpha_production_evidence() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _matrix_evidence(root=root)
        assert provider_conformance.validate_evidence(
            evidence,
            registry=registry,
            root=root,
            compiled=compiled,
        ) == []
        readiness = provider_conformance.derive_readiness(
            compiled=compiled,
            evidence=evidence,
        )

    assert readiness["gamma"][CAPABILITY_ID]["adapter_ready"] is True
    assert readiness["gamma"][CAPABILITY_ID]["capability_ready"] is True
    assert readiness["prod"][CAPABILITY_ID]["adapter_ready"] is True
    assert readiness["prod"][CAPABILITY_ID]["capability_ready"] is True


def test_environment_specific_config_digests_are_valid_when_each_cell_is_current() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        _, compiled = _compiled_with_mixed_sms_bindings()
        config_digests = {
            "alpha": _digest("a"),
            "beta": _digest("b"),
            "gamma": _digest("c"),
        }
        evidence = _matrix_evidence(root=root, config_digests=config_digests)
        readiness = provider_conformance.derive_readiness(
            compiled=compiled,
            evidence=evidence,
        )

    assert readiness["gamma"][CAPABILITY_ID]["capability_ready"] is True


def test_expired_or_release_digest_drift_evidence_prevents_readiness_promotion() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        stale = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
        )
        stale["executedAt"] = (
            datetime.now(timezone.utc) - provider_conformance.MAX_EVIDENCE_AGE
            - timedelta(seconds=1)
        ).isoformat()
        stale_issues = provider_conformance.validate_evidence(
            [stale],
            registry=registry,
            root=root,
            current_commit="a" * 40,
            compiled=compiled,
        )
        evidence = _matrix_evidence(root=root)
        gamma_release = next(
            item
            for item in evidence
            if item["environment"] == "gamma" and item["testLayer"] == "user_acceptance"
        )
        gamma_release["imageDigest"] = _digest("f")
        readiness = provider_conformance.derive_readiness(
            compiled=compiled,
            evidence=evidence,
        )

    assert any("exceeds the 24-hour readiness window" in issue for issue in stale_issues)
    assert readiness["gamma"][CAPABILITY_ID]["capability_ready"] is False


def test_illegal_alpha_adapter_is_rejected_even_when_its_evidence_looks_valid() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=PRODUCTION_ADAPTER_ID,
        )
        issues = provider_conformance.validate_evidence(
            [evidence],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any("does not match the environment-selected Binding adapter" in issue for issue in issues)
    assert any("is not allowed in this environment" in issue for issue in issues)


def test_zero_evidence_fails_the_prod_readiness_gate() -> None:
    _, compiled = _compiled_with_mixed_sms_bindings()
    readiness = provider_conformance.derive_readiness(compiled=compiled, evidence=[])
    issues = provider_conformance.readiness_issues(
        {
            "evidenceCount": 0,
            "readiness": readiness,
        },
        environment="prod",
    )

    assert readiness["prod"][CAPABILITY_ID]["capability_ready"] is False
    assert any("zero Provider Conformance evidence artifacts" in issue for issue in issues)


def test_release_make_gate_requires_provider_readiness() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    release_target = makefile.split("gate-release:", maxsplit=1)[1].split(
        "\n\n", maxsplit=1
    )[0]

    assert (
        'quwoquan_ops/gate/verify_provider_conformance_evidence.py --require-ready "$(ENV)"'
        in release_target
    )


def test_prod_requires_its_selected_binding_preflight_without_prod_smoke_evidence() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        _, compiled = _compiled_with_mixed_sms_bindings()
        compiled["readiness"]["prod"][CAPABILITY_ID]["adapter_preflight_ready"] = False
        readiness = provider_conformance.derive_readiness(
            compiled=compiled,
            evidence=_matrix_evidence(root=root),
        )

    assert readiness["gamma"][CAPABILITY_ID]["capability_ready"] is True
    assert readiness["prod"][CAPABILITY_ID]["capability_ready"] is False


def test_missing_rollback_receipt_blocks_gamma_and_prod_readiness() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _matrix_evidence(root=root)
        gamma_release = next(
            item
            for item in evidence
            if item["environment"] == "gamma" and item["testLayer"] == "user_acceptance"
        )
        del gamma_release["releaseReadiness"]["rollbackReceiptRef"]
        issues = provider_conformance.validate_evidence(
            evidence,
            registry=registry,
            root=root,
            compiled=compiled,
        )
        readiness = provider_conformance.derive_readiness(
            compiled=compiled,
            evidence=evidence,
        )

    assert any("requires complete non-sensitive releaseReadiness" in issue for issue in issues)
    assert readiness["gamma"][CAPABILITY_ID]["capability_ready"] is False
    assert readiness["prod"][CAPABILITY_ID]["capability_ready"] is False


def test_release_receipts_reject_endpoint_or_secret_material() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _matrix_evidence(root=root)
        gamma_release = next(
            item
            for item in evidence
            if item["environment"] == "gamma" and item["testLayer"] == "user_acceptance"
        )
        gamma_release["releaseReadiness"][
            "prodBindingPreflightReceiptRef"
        ] = "receipt:prod:secret-value"
        issues = provider_conformance.validate_evidence(
            evidence,
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any("requires complete non-sensitive releaseReadiness" in issue for issue in issues)


def test_layer_boundary_and_duplicate_artifact_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / ".qwq_output"
        registry, compiled = _compiled_with_mixed_sms_bindings()
        evidence = _evidence(
            root=root,
            environment="alpha",
            layer="local_contract",
            adapter_id=ALPHA_ADAPTER_ID,
        )
        evidence["networkBoundary"] = "remote_protocol"
        duplicate = dict(evidence)
        duplicate["testLayer"] = "api_integration"
        duplicate["executionProfile"] = "smoke"
        issues = provider_conformance.validate_evidence(
            [evidence, duplicate],
            registry=registry,
            root=root,
            compiled=compiled,
        )

    assert any("local_contract must use offline_harness" in issue for issue in issues)
    assert any("artifactRef must identify one conformance cell only" in issue for issue in issues)


if __name__ == "__main__":
    test_conformance_evidence_rejects_zero_assertion_pass()
    test_conformance_evidence_rejects_empty_or_unlinked_execution_artifact()
    test_conformance_evidence_requires_adapter_profile_test_source()
    test_conformance_evidence_requires_execution_report_digest_match()
    test_conformance_evidence_rejects_untrusted_execution_attestation()
    test_execution_attestation_covers_binding_roots()
    test_conformance_evidence_rejects_fabricated_or_omitted_binding_roots()
    test_shared_message_transport_evidence_requires_all_compiled_roots()
    test_conformance_evidence_rejects_registry_compiled_root_drift()
    test_conformance_evidence_fails_closed_without_ci_attestation_key()
    test_mixed_selected_adapters_make_capability_ready_without_illegal_alpha_production_evidence()
    test_environment_specific_config_digests_are_valid_when_each_cell_is_current()
    test_expired_or_release_digest_drift_evidence_prevents_readiness_promotion()
    test_illegal_alpha_adapter_is_rejected_even_when_its_evidence_looks_valid()
    test_zero_evidence_fails_the_prod_readiness_gate()
    test_release_make_gate_requires_provider_readiness()
    test_prod_requires_its_selected_binding_preflight_without_prod_smoke_evidence()
    test_missing_rollback_receipt_blocks_gamma_and_prod_readiness()
    test_release_receipts_reject_endpoint_or_secret_material()
    test_layer_boundary_and_duplicate_artifact_are_rejected()
