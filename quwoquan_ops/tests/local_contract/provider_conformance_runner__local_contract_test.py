from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import provider_conformance_runner
from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance


def test_runner_executes_declared_harness_and_emits_attested_evidence() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        output_root = Path(temporary) / ".qwq_output"
        previous_output_root = os.environ.get("QWQ_OUTPUT_ROOT")
        previous_attestation_key = os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"
        )
        compiled, _ = governance.load_and_compile()
        original_load_and_compile = provider_conformance_runner.governance.load_and_compile
        provider_conformance_runner.governance.load_and_compile = lambda: (compiled, [])
        os.environ["QWQ_OUTPUT_ROOT"] = str(output_root)
        os.environ["QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"] = (
            "provider-conformance-runner-local-contract-key"
        )
        try:
            result = provider_conformance_runner.main(
                [
                    "--adapter-id",
                    "ext.llm.protocol_fixture",
                    "--environment",
                    "alpha",
                    "--layer",
                    "local_contract",
                    "--execute",
                    "--image-digest",
                    f"sha256:{'1' * 64}",
                ]
            )
            report, issues = provider_conformance.load_validate_and_derive(
                root=output_root
            )
            evidence_path = next(
                output_root.rglob("provider-conformance-*.evidence.json")
            )
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            execution_report = json.loads(
                (
                    output_root
                    / Path(*Path(evidence["artifactRef"]).parts[1:])
                ).read_text(encoding="utf-8")
            )
        finally:
            provider_conformance_runner.governance.load_and_compile = (
                original_load_and_compile
            )
            if previous_output_root is None:
                os.environ.pop("QWQ_OUTPUT_ROOT", None)
            else:
                os.environ["QWQ_OUTPUT_ROOT"] = previous_output_root
            if previous_attestation_key is None:
                os.environ.pop("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY", None)
            else:
                os.environ[
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"
                ] = previous_attestation_key

    assert result == 0
    assert issues == []
    assert report["evidenceCount"] == 1
    binding = compiled["selectedBindings"]["alpha"]["assistant.model.generation"]
    binding_root_records = provider_conformance.compiled_capability_binding_roots(
        compiled,
        capability_id="assistant.model.generation",
    )
    binding_roots = [root["root_id"] for root in binding_root_records]
    assert evidence["bindingRoots"] == binding_roots
    assert execution_report["bindingRoots"] == binding_roots
    assert evidence["configDigest"] == provider_conformance_runner._digest_json(
        {
            "binding": binding,
            "bindingRoots": binding_root_records,
        }
    )
    assert execution_report["configDigest"] == evidence["configDigest"]
    assert evidence["observabilityRefs"]["metrics"] == [
        "provider-conformance://ext.llm.protocol_fixture/metrics"
    ]


def test_runner_emits_shared_message_transport_root_and_metric_coverage() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        output_root = Path(temporary) / ".qwq_output"
        previous_output_root = os.environ.get("QWQ_OUTPUT_ROOT")
        previous_attestation_key = os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"
        )
        compiled, _ = governance.load_and_compile()
        original_load_and_compile = provider_conformance_runner.governance.load_and_compile
        provider_conformance_runner.governance.load_and_compile = lambda: (compiled, [])
        os.environ["QWQ_OUTPUT_ROOT"] = str(output_root)
        os.environ["QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"] = (
            "provider-conformance-runner-local-contract-key"
        )
        try:
            result = provider_conformance_runner.main(
                [
                    "--adapter-id",
                    "infra.redis.message_transport_fixture",
                    "--environment",
                    "alpha",
                    "--layer",
                    "local_contract",
                ]
            )
            evidence_path = next(
                output_root.rglob("provider-conformance-*.evidence.json")
            )
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            issues = provider_conformance.validate_evidence(
                [evidence],
                registry=governance.load_registry(),
                root=output_root,
                compiled=compiled,
            )
        finally:
            provider_conformance_runner.governance.load_and_compile = (
                original_load_and_compile
            )
            if previous_output_root is None:
                os.environ.pop("QWQ_OUTPUT_ROOT", None)
            else:
                os.environ["QWQ_OUTPUT_ROOT"] = previous_output_root
            if previous_attestation_key is None:
                os.environ.pop("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY", None)
            else:
                os.environ[
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"
                ] = previous_attestation_key

    capability_id = provider_conformance.MESSAGE_TRANSPORT_CAPABILITY_ID
    assert result == 0
    assert issues == []
    assert evidence["bindingRoots"] == [
        root["root_id"]
        for root in provider_conformance.compiled_capability_binding_roots(
            compiled,
            capability_id=capability_id,
        )
    ]
    assert evidence["observabilityRefs"]["metrics"] == [
        "provider-conformance://infra.redis.message_transport_fixture/metrics",
        *provider_conformance.required_metric_refs(capability_id),
    ]


def test_runner_fails_closed_without_remote_chat_assistant_uat_harness() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        output_root = Path(temporary) / ".qwq_output"
        previous_output_root = os.environ.get("QWQ_OUTPUT_ROOT")
        previous_attestation_key = os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"
        )
        compiled, _ = governance.load_and_compile()
        original_load_and_compile = provider_conformance_runner.governance.load_and_compile
        provider_conformance_runner.governance.load_and_compile = lambda: (compiled, [])
        os.environ["QWQ_OUTPUT_ROOT"] = str(output_root)
        os.environ["QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"] = (
            "provider-conformance-runner-local-contract-key"
        )
        try:
            result = provider_conformance_runner.main(
                [
                    "--adapter-id",
                    "infra.redis.message_transport_fixture",
                    "--environment",
                    "alpha",
                    "--layer",
                    "user_acceptance",
                    "--execute",
                    "--image-digest",
                    f"sha256:{'2' * 64}",
                ]
            )
            evidence_path = next(
                output_root.rglob("provider-conformance-*.evidence.json")
            )
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            issues = provider_conformance.validate_evidence(
                [evidence],
                registry=governance.load_registry(),
                root=output_root,
                compiled=compiled,
            )
            report_path = output_root / Path(*Path(evidence["artifactRef"]).parts[1:])
            report = json.loads(report_path.read_text(encoding="utf-8"))
        finally:
            provider_conformance_runner.governance.load_and_compile = (
                original_load_and_compile
            )
            if previous_output_root is None:
                os.environ.pop("QWQ_OUTPUT_ROOT", None)
            else:
                os.environ["QWQ_OUTPUT_ROOT"] = previous_output_root
            if previous_attestation_key is None:
                os.environ.pop("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY", None)
            else:
                os.environ[
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"
                ] = previous_attestation_key

    assert result == 1
    assert issues == []
    assert evidence["status"] == "blocked"
    assert evidence["failure"] == {
        "code": "PROVIDER.CONFORMANCE.REMOTE_CHAT_ASSISTANT_UAT_HARNESS_REQUIRED",
        "recoveryAction": "configure",
    }
    assert report["status"] == "blocked"
    assert report["exitCode"] == 0
    assert report["testSource"].endswith(
        "provider_conformance_prerequisites/"
        "message_transport_chat_assistant_remote_uat.yaml"
    )
    assert report["testCommand"].startswith(
        "provider-conformance-prerequisite runtime.message.transport"
    )


if __name__ == "__main__":
    test_runner_executes_declared_harness_and_emits_attested_evidence()
    test_runner_emits_shared_message_transport_root_and_metric_coverage()
    test_runner_fails_closed_without_remote_chat_assistant_uat_harness()
