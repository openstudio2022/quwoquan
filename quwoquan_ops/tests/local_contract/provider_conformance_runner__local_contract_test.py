from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import argparse
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import provider_conformance_runner
from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance


def test_runner_emits_evidence_only_from_test_owned_case_results() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        output_root = Path(temporary) / ".qwq_output"
        harness = Path(temporary) / "real_provider_harness.py"
        previous_output_root = os.environ.get("QWQ_OUTPUT_ROOT")
        previous_attestation_key = os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"
        )
        previous_expected_image_digest = os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"
        )
        compiled, _ = governance.load_and_compile()
        registry = governance.load_registry()
        capability = next(
            item
            for item in registry["capabilities"]
            if item["capability_id"] == "assistant.model.generation"
        )
        assertion_ids = sorted(
            provider_conformance.PUBLIC_ASSERTION_IDS
            | {"provider.model_generation"}
        )
        harness.write_text(
            "\n".join(
                (
                    "import json",
                    "import os",
                    "from pathlib import Path",
                    "assertion_ids = json.loads(os.environ['QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS'])",
                    "Path(os.environ['QWQ_PROVIDER_CONFORMANCE_RESULT_PATH']).with_suffix('.runner-env.json').write_text(json.dumps({",
                    "  'contractGraphDigest': os.environ['QWQ_PROVIDER_CONFORMANCE_CONTRACT_GRAPH_DIGEST'],",
                    "  'adapterDigest': os.environ['QWQ_PROVIDER_CONFORMANCE_ADAPTER_DIGEST'],",
                    "}), encoding='utf-8')",
                    "payload = {",
                    "  'schema': 'provider-conformance-case-results',",
                    "  'version': 1,",
                    "  'status': 'passed',",
                    "  'adapterId': os.environ['QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID'],",
                    "  'capabilityId': os.environ['QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID'],",
                    "  'environment': os.environ['QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT'],",
                    "  'testLayer': os.environ['QWQ_PROVIDER_CONFORMANCE_LAYER'],",
                    "  'typedPort': os.environ['QWQ_PROVIDER_CONFORMANCE_TYPED_PORT'],",
                    "  'contractRef': os.environ['QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF'],",
                    "  'networkBoundary': 'offline_harness',",
                    "  'testTarget': 'assistant-model-real-adapter-harness',",
                    "  'configDigest': os.environ['QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST'],",
                    "  'assertionIds': assertion_ids,",
                    "  'caseResults': [{'assertionId': item, 'status': 'passed', 'logRef': 'log:provider-test', 'traceRef': 'trace:provider-test', 'metricRefs': ['metric:provider-test']} for item in assertion_ids],",
                    "  'dataDigest': 'sha256:' + '2' * 64,",
                    "  'cleanupReceipt': 'receipt:cleanup.alpha.1',",
                    "  'observabilityRefs': {'logs': ['log:provider-test'], 'traces': ['trace:provider-test'], 'metrics': ['metric:provider-test']},",
                    "}",
                    "with open(os.environ['QWQ_PROVIDER_CONFORMANCE_RESULT_PATH'], 'w', encoding='utf-8') as output:",
                    "  json.dump(payload, output, sort_keys=True)",
                )
            ),
            encoding="utf-8",
        )
        source = {
            "adapterId": "ext.llm.protocol_fixture",
            "capabilityId": "assistant.model.generation",
            "testLayer": "local_contract",
            "typedPort": capability["canonical_port"],
            "contractRef": capability["source"],
            "assertionIds": assertion_ids,
            "command": [sys.executable, str(harness)],
            "target": "assistant-model-real-adapter-harness",
            "networkBoundary": "offline_harness",
            "testSource": "quwoquan_ops/tests/local_contract/assistant_model_conformance.py",
            "testSourceDigest": f"sha256:{'3' * 64}",
            "acceptanceRefs": [
                "specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002"
            ],
        }
        os.environ["QWQ_OUTPUT_ROOT"] = str(output_root)
        os.environ["QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"] = (
            "provider-conformance-runner-local-contract-key"
        )
        os.environ["QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"] = (
            f"sha256:{'1' * 64}"
        )
        try:
            evidence_path = provider_conformance_runner._execute_cell(
                argparse.Namespace(
                    adapter_id="ext.llm.protocol_fixture",
                    environment="alpha",
                    layer="local_contract",
                    execute=True,
                    data_digest="",
                    image_digest=f"sha256:{'1' * 64}",
                    adapter_health_receipt_ref="",
                    switch_compatibility_receipt_ref="",
                    callback_drain_receipt_ref="",
                    last_good_receipt_ref="",
                    rollback_receipt_ref="",
                    prod_binding_preflight_receipt_ref="",
                    prod_adapter_health_receipt_ref="",
                ),
                registry=registry,
                compiled=compiled,
                sources={
                    (
                        "assistant.model.generation",
                        "ext.llm.protocol_fixture",
                        "local_contract",
                    ): source
                },
            )
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            issues = provider_conformance.validate_evidence(
                [evidence],
                registry=registry,
                root=output_root,
                current_commit=provider_conformance._current_commit(),
                compiled=compiled,
                source_catalog={
                    (
                        "assistant.model.generation",
                        "ext.llm.protocol_fixture",
                        "local_contract",
                    ): source
                },
                expected_image_digest=f"sha256:{'1' * 64}",
            )
            execution_report = json.loads(
                (
                    output_root
                    / Path(*Path(evidence["artifactRef"]).parts[1:])
                ).read_text(encoding="utf-8")
            )
            case_result_path = output_root / Path(
                *Path(execution_report["testArtifactRef"]).parts[1:]
            )
            runner_environment = json.loads(
                case_result_path.with_suffix(".runner-env.json").read_text(
                    encoding="utf-8"
                )
            )
        finally:
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
            if previous_expected_image_digest is None:
                os.environ.pop("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST", None)
            else:
                os.environ[
                    "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"
                ] = previous_expected_image_digest

    assert issues == []
    binding = compiled["selectedBindings"]["alpha"]["assistant.model.generation"]
    binding_root_records = provider_conformance.compiled_capability_binding_roots(
        compiled,
        capability_id="assistant.model.generation",
    )
    binding_roots = [root["root_id"] for root in binding_root_records]
    assert evidence["bindingRoots"] == binding_roots
    assert execution_report["bindingRoots"] == binding_roots
    assert evidence["configDigest"] == provider_conformance.binding_config_digest(
        binding,
        binding_root_records,
    )
    assert execution_report["configDigest"] == evidence["configDigest"]
    assert runner_environment["contractGraphDigest"] == evidence["contractGraphDigest"]
    assert runner_environment["adapterDigest"] == evidence["adapterDigest"]
    assert evidence["testTarget"] == "assistant-model-real-adapter-harness"
    assert evidence["observabilityRefs"]["metrics"] == ["metric:provider-test"]


def test_runner_rejects_static_derived_source_without_emitting_evidence() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        output_root = Path(temporary) / ".qwq_output"
        previous_output_root = os.environ.get("QWQ_OUTPUT_ROOT")
        previous_attestation_key = os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"
        )
        previous_expected_image_digest = os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"
        )
        os.environ["QWQ_OUTPUT_ROOT"] = str(output_root)
        os.environ["QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY"] = "test-key"
        os.environ["QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"] = (
            f"sha256:{'1' * 64}"
        )
        try:
            with mock.patch.object(
                provider_conformance_runner.provider_conformance,
                "discover_test_sources",
                return_value=({}, []),
            ):
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
        finally:
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
            if previous_expected_image_digest is None:
                os.environ.pop("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST", None)
            else:
                os.environ[
                    "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"
                ] = previous_expected_image_digest

    assert result == 1
    assert not list(output_root.rglob("*.evidence.json"))


def test_matrix_executes_every_actual_binding_cell() -> None:
    compiled, _ = governance.load_and_compile()
    calls: list[tuple[str, str, str]] = []

    def execute_cell(
        args: argparse.Namespace,
        **_kwargs: object,
    ) -> Path:
        calls.append((args.adapter_id, args.environment, args.layer))
        return Path(f"/tmp/{args.environment}-{args.layer}.evidence.json")

    with (
        mock.patch.object(
            provider_conformance_runner.provider_conformance,
            "discover_test_sources",
            return_value=({}, []),
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_execute_cell",
            side_effect=execute_cell,
        ),
    ):
        result = provider_conformance_runner.main(
            [
                "--matrix",
                "--capability-id",
                "assistant.model.generation",
                "--execute",
                "--image-digest",
                f"sha256:{'1' * 64}",
            ]
        )

    expected = [
        (
            compiled["selectedBindings"][environment]["assistant.model.generation"][
                "adapter_id"
            ],
            environment,
            layer,
        )
        for environment in provider_conformance.ENVIRONMENTS
        for layer in provider_conformance.LAYERS
    ]
    assert result == 0
    assert calls == expected


def test_runner_rejects_stale_image_digest_before_emitting_evidence() -> None:
    previous_expected_image_digest = os.environ.get(
        "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"
    )
    os.environ["QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"] = f"sha256:{'2' * 64}"
    try:
        try:
            provider_conformance_runner._execute_cell(
                argparse.Namespace(
                    adapter_id="ext.llm.protocol_fixture",
                    environment="alpha",
                    layer="local_contract",
                    execute=True,
                    data_digest="",
                    image_digest=f"sha256:{'1' * 64}",
                ),
                registry={},
                compiled={},
                sources={},
            )
        except ValueError as exc:
            assert "does not match the active immutable image" in str(exc)
        else:
            raise AssertionError("stale image digest was accepted")
    finally:
        if previous_expected_image_digest is None:
            os.environ.pop("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST", None)
        else:
            os.environ[
                "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"
            ] = previous_expected_image_digest


if __name__ == "__main__":
    test_runner_emits_evidence_only_from_test_owned_case_results()
    test_runner_rejects_static_derived_source_without_emitting_evidence()
    test_matrix_executes_every_actual_binding_cell()
    test_runner_rejects_stale_image_digest_before_emitting_evidence()
