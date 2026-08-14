from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import argparse
from unittest import mock

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import provider_conformance_runner, stackctl
from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance


_RUNTIME_IDENTITY_ENV = "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"
_CANDIDATE_A = "sha256:" + "1" * 64
_CANDIDATE_B = "sha256:" + "2" * 64
_PROVIDER_RUNTIME_DIGEST = "sha256:" + "3" * 64


def _immutable_runtime_handoff(
    *,
    candidate_digest: str = _CANDIDATE_A,
) -> str:
    return json.dumps(
        {
            "schema": "stackctl.provider_conformance_runtime_identity",
            "runtimeMode": "immutable_candidate",
            "environment": "alpha",
            "target": "alpha-local",
            "workload": "full",
            "startupAttemptId": "attempt-immutable-alpha",
            "providerRuntimeDigest": _PROVIDER_RUNTIME_DIGEST,
            "failureFree": True,
            "nonPromotable": False,
            "candidateDigest": candidate_digest,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _mutable_runtime_handoff() -> str:
    return json.dumps(
        {
            "schema": "stackctl.provider_conformance_runtime_identity",
            "runtimeMode": "test_live",
            "environment": "alpha",
            "target": "alpha-local",
            "workload": "full",
            "startupAttemptId": "attempt-test-live-alpha",
            "providerRuntimeDigest": _PROVIDER_RUNTIME_DIGEST,
            "failureFree": True,
            "nonPromotable": True,
            "mutableComposeDigest": "sha256:" + "4" * 64,
            "mutableConfigurationDigest": "sha256:" + "5" * 64,
            "mutableStateDigest": "sha256:" + "6" * 64,
            "mutableWorkspaceStatusDigest": "sha256:" + "7" * 64,
            "mutableResolverHandoffDigest": "sha256:" + "8" * 64,
            "mutableSourceRevision": "a" * 40,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def test_runner_has_no_hardcoded_active_candidate_escape() -> None:
    source = (
        ROOT / "quwoquan_ops/cli/provider_conformance_runner.py"
    ).read_text(encoding="utf-8")
    assert "candidate_active=True" not in source
    assert "_evidence_identity_for_runtime(" in source
    assert "runtime_identity.runtime_mode == \"immutable_candidate\"" in source
    assert "resolve_nonprod_active_candidate(" in source
    assert "resolve_prod_active_candidate(" in source


def test_formal_producer_rejects_local_or_receiptless_identity() -> None:
    with mock.patch.dict(
        os.environ,
        {"QWQ_PROVIDER_CONFORMANCE_REQUIRE_PROMOTABLE": "true"},
        clear=False,
    ):
        with pytest.raises(ValueError, match="formal Provider producer"):
            provider_conformance_runner._require_formal_promotability(
                {
                    "nonPromotable": True,
                    "attestationAuthority": "local",
                    "candidateStatus": "unverified",
                }
            )
        provider_conformance_runner._require_formal_promotability(
            {
                "nonPromotable": False,
                "attestationAuthority": "ci",
                "candidateStatus": "active_immutable",
            }
        )


def test_mutable_handoff_cannot_borrow_active_candidate_under_ci_authority() -> None:
    commit = "a" * 40
    with (
        mock.patch.dict(
            os.environ,
            {
                _RUNTIME_IDENTITY_ENV: _mutable_runtime_handoff(),
                "GITHUB_ACTIONS": "true",
                "QWQ_PROVIDER_CONFORMANCE_REVIEWED_COMMIT": commit,
                "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_AUTHORITY": "ci",
                "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY": "test-only-key",
            },
            clear=False,
        ),
        mock.patch.object(
            provider_conformance,
            "current_source_tree_state",
            return_value="clean",
        ),
        mock.patch.object(
            provider_conformance,
            "ci_attestation_authority_available",
            return_value=True,
        ),
    ):
        runtime_identity = (
            provider_conformance_runner._freeze_nonprod_runtime_identity("alpha")
        )
        identity = provider_conformance_runner._evidence_identity_for_runtime(
            runtime_identity,
            commit=commit,
            candidate={
                "active": True,
                "receiptRef": "receipt:must-not-be-borrowed",
                "receiptDigest": "sha256:" + "9" * 64,
            },
        )

    assert identity["attestationAuthority"] == "ci"
    assert identity["candidateStatus"] == "unverified"
    assert identity["candidateReceiptRef"] == ""
    assert identity["candidateReceiptDigest"] == ""
    assert identity["nonPromotable"] is True


@pytest.mark.parametrize(
    ("field", "drifted"),
    (
        ("candidateDigest", _CANDIDATE_B),
        ("attemptId", "attempt-immutable-beta"),
        ("providerRuntimeDigest", "sha256:" + "9" * 64),
    ),
)
def test_immutable_evidence_resolver_requires_exact_frozen_identity(
    field: str,
    drifted: str,
) -> None:
    receipt = {
        "status": "running",
        "env": "alpha",
        "target": "alpha-local",
        "workload": "full",
        "candidateDigest": _CANDIDATE_A,
        "attemptId": "attempt-immutable-alpha",
        "providerRuntimeDigest": _PROVIDER_RUNTIME_DIGEST,
        "failure": None,
        "cleanupFailure": None,
    }
    receipt[field] = drifted
    with tempfile.TemporaryDirectory() as temporary:
        receipt_path = Path(temporary) / "startup_attempt.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        receipt_digest = provider_conformance_runner._digest_bytes(
            receipt_path.read_bytes()
        )
        with (
            mock.patch.dict(
                os.environ,
                {_RUNTIME_IDENTITY_ENV: _immutable_runtime_handoff()},
                clear=False,
            ),
            mock.patch.object(
                provider_conformance_runner,
                "startup_attempt_path",
                return_value=receipt_path,
            ),
            mock.patch.object(
                provider_conformance,
                "resolve_nonprod_active_candidate",
                return_value={
                    "active": True,
                    "receiptRef": "receipt:canonical-startup",
                    "receiptDigest": receipt_digest,
                    "reason": "",
                },
            ),
            pytest.raises(ValueError, match="frozen candidate/startup/provider"),
        ):
            provider_conformance_runner._resolve_immutable_execution_candidate(
                provider_conformance_runner._freeze_nonprod_runtime_identity(
                    "alpha"
                ),
                registry={},
                commit="a" * 40,
                image_digest="sha256:" + "a" * 64,
                contract_graph_digest="sha256:" + "b" * 64,
            )


def test_postrun_active_candidate_drift_removes_case_result() -> None:
    pre_run_candidate = {
        "active": True,
        "receiptRef": "receipt:candidate-a",
        "receiptDigest": "sha256:" + "a" * 64,
        "reason": "",
    }
    post_run_candidate = {
        "active": True,
        "receiptRef": "receipt:candidate-b",
        "receiptDigest": "sha256:" + "b" * 64,
        "reason": "",
    }
    with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
        os.environ,
        {_RUNTIME_IDENTITY_ENV: _immutable_runtime_handoff()},
        clear=False,
    ):
        case_result_path = Path(temporary) / "case-results.json"
        case_result_path.write_text('{"status":"passed"}', encoding="utf-8")
        with (
            mock.patch.object(
                provider_conformance_runner,
                "_resolve_immutable_execution_candidate",
                return_value=post_run_candidate,
            ),
            pytest.raises(ValueError, match="changed during execution"),
        ):
            provider_conformance_runner._postrun_nonprod_candidate(
                provider_conformance_runner._freeze_nonprod_runtime_identity(
                    "alpha"
                ),
                pre_run_candidate=pre_run_candidate,
                case_result_path=case_result_path,
                registry={},
                commit="a" * 40,
                image_digest="sha256:" + "a" * 64,
                contract_graph_digest="sha256:" + "b" * 64,
            )

        assert not case_result_path.exists()


def test_environment_matrix_preflight_requires_active_startup_receipt() -> None:
    with (
        mock.patch.object(
            provider_conformance_runner.provider_conformance,
            "candidate_image_digest",
            return_value="sha256:" + "1" * 64,
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_resolve_immutable_execution_candidate",
            side_effect=ValueError("canonical startup receipt is missing"),
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_current_commit",
            return_value="a" * 40,
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_contract_graph_digest",
            return_value="sha256:" + "2" * 64,
        ),
        pytest.raises(ValueError, match="canonical startup receipt is missing"),
    ):
        provider_conformance_runner.preflight_environment_matrix(
            environment="alpha",
            registry={"capabilities": []},
            compiled={"selectedBindings": {"alpha": {}}},
            sources={},
            runtime_environment={
                _RUNTIME_IDENTITY_ENV: _immutable_runtime_handoff()
            },
        )


def test_environment_matrix_mutable_preflight_does_not_read_active_candidate() -> None:
    with (
        mock.patch.object(
            provider_conformance_runner.provider_conformance,
            "candidate_image_digest",
            return_value="sha256:" + "1" * 64,
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_resolve_immutable_execution_candidate",
            side_effect=AssertionError("mutable preflight must not read active"),
        ) as resolve_immutable,
        mock.patch.object(
            provider_conformance_runner,
            "_current_commit",
            return_value="a" * 40,
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_contract_graph_digest",
            return_value="sha256:" + "2" * 64,
        ),
    ):
        image_digest = provider_conformance_runner.preflight_environment_matrix(
            environment="alpha",
            registry={"capabilities": []},
            compiled={"selectedBindings": {"alpha": {}}},
            sources={},
            runtime_environment={
                _RUNTIME_IDENTITY_ENV: _mutable_runtime_handoff()
            },
        )

    assert image_digest == "sha256:" + "1" * 64
    resolve_immutable.assert_not_called()


def test_environment_matrix_preflight_reads_injected_keys_from_runtime_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "ASSISTANT_MODEL_COMPLETION_URL",
        "ASSISTANT_PUBLIC_SEARCH_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    binding = {
        "adapter_id": "ext.model.protocol_fixture",
        "state": "enabled",
        "endpoint_envs": {
            "completion": "ASSISTANT_MODEL_COMPLETION_URL",
            "search": "ASSISTANT_PUBLIC_SEARCH_URL",
        },
        "secret_refs": [],
    }
    with (
        mock.patch.object(
            provider_conformance_runner.provider_conformance,
            "candidate_image_digest",
            return_value="sha256:" + "1" * 64,
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_resolve_immutable_execution_candidate",
            return_value={"candidateDigest": _CANDIDATE_A},
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_current_commit",
            return_value="a" * 40,
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_contract_graph_digest",
            return_value="sha256:" + "2" * 64,
        ),
        mock.patch.object(
            provider_conformance_runner.provider_conformance,
            "source_for_cell",
            return_value={"typedPort": "assistant.model.complete"},
        ),
    ):
        image_digest = provider_conformance_runner.preflight_environment_matrix(
            environment="alpha",
            registry={"capabilities": []},
            compiled={
                "selectedBindings": {
                    "alpha": {"assistant.model.complete": binding}
                }
            },
            sources={},
            runtime_environment={
                _RUNTIME_IDENTITY_ENV: _immutable_runtime_handoff(),
                "ASSISTANT_MODEL_COMPLETION_URL": (
                    "https://provider-protocol-substitute:18089/v1/chat/completions"
                ),
                "ASSISTANT_PUBLIC_SEARCH_URL": (
                    "https://provider-protocol-substitute:18089/search/html"
                ),
            },
        )

    assert image_digest == "sha256:" + "1" * 64
    assert "ASSISTANT_MODEL_COMPLETION_URL" not in os.environ


def test_environment_matrix_preflight_still_blocks_when_runtime_keys_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASSISTANT_MODEL_COMPLETION_URL", raising=False)
    binding = {
        "adapter_id": "ext.model.protocol_fixture",
        "state": "enabled",
        "endpoint_envs": {"completion": "ASSISTANT_MODEL_COMPLETION_URL"},
        "secret_refs": [],
    }
    with (
        mock.patch.object(
            provider_conformance_runner.provider_conformance,
            "candidate_image_digest",
            return_value="sha256:" + "1" * 64,
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_resolve_immutable_execution_candidate",
            return_value={"candidateDigest": _CANDIDATE_A},
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_current_commit",
            return_value="a" * 40,
        ),
        mock.patch.object(
            provider_conformance_runner,
            "_contract_graph_digest",
            return_value="sha256:" + "2" * 64,
        ),
        mock.patch.object(
            provider_conformance_runner.provider_conformance,
            "source_for_cell",
            return_value={"typedPort": "assistant.model.complete"},
        ),
        pytest.raises(
            ValueError,
            match="missing injected runtime keys: ASSISTANT_MODEL_COMPLETION_URL",
        ),
    ):
        provider_conformance_runner.preflight_environment_matrix(
            environment="alpha",
            registry={"capabilities": []},
            compiled={
                "selectedBindings": {
                    "alpha": {"assistant.model.complete": binding}
                }
            },
            sources={},
            runtime_environment={
                _RUNTIME_IDENTITY_ENV: _immutable_runtime_handoff(),
            },
        )


def test_candidate_image_digest_is_derived_from_environment_packages() -> None:
    commit = "a" * 40
    service_digest = f"sha256:{'b' * 64}"
    registry = {"capabilities": [{"service_id": "assistant-service"}]}

    with tempfile.TemporaryDirectory() as temporary:
        package_root = Path(temporary)

        def package_dir(
            environment: str,
            service: str,
            *,
            target: str,
        ) -> Path:
            assert target == f"{environment}-local"
            package = package_root / environment / service
            package.mkdir(parents=True, exist_ok=True)
            (package / "image.lock").write_text(
                yaml.safe_dump(
                    {
                        "service": service,
                        "digest": service_digest,
                        "digestSource": "build-input",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            (package / "provenance.json").write_text(
                json.dumps(
                    {
                        "service": service,
                        "environment": environment,
                        "gitRevision": commit,
                        "digests": {"sourceTree": service_digest},
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            return package

        with (
            mock.patch.object(
                provider_conformance,
                "service_deployment_package_dir",
                side_effect=package_dir,
            ),
            mock.patch.object(
                provider_conformance,
                "_current_commit",
                return_value=commit,
            ),
        ):
            alpha_digest = provider_conformance.candidate_image_digest(
                "alpha",
                registry=registry,
            )
            beta_digest = provider_conformance.candidate_image_digest(
                "beta",
                registry=registry,
            )

    assert provider_conformance.SHA256_PATTERN.fullmatch(alpha_digest)
    assert beta_digest == alpha_digest


def test_candidate_image_digest_rejects_inconsistent_provenance() -> None:
    registry = {"capabilities": [{"service_id": "assistant-service"}]}
    with tempfile.TemporaryDirectory() as temporary:
        package = Path(temporary)
        (package / "image.lock").write_text(
            yaml.safe_dump(
                {
                    "service": "assistant-service",
                    "digest": f"sha256:{'b' * 64}",
                    "digestSource": "build-input",
                }
            ),
            encoding="utf-8",
        )
        (package / "provenance.json").write_text(
            json.dumps(
                {
                    "service": "assistant-service",
                    "environment": "alpha",
                    "gitRevision": "a" * 40,
                    "digests": "not-a-digest-map",
                }
            ),
            encoding="utf-8",
        )
        with (
            mock.patch.object(
                provider_conformance,
                "service_deployment_package_dir",
                return_value=package,
            ),
            mock.patch.object(
                provider_conformance,
                "_current_commit",
                return_value="a" * 40,
            ),
        ):
            try:
                provider_conformance.candidate_image_digest(
                    "alpha",
                    registry=registry,
                )
            except ValueError as exc:
                assert "provenance has no digests" in str(exc)
            else:
                raise AssertionError("inconsistent Provider provenance was accepted")


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
                    "  'runtimeIdentity': os.environ['QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY'],",
                    "}), encoding='utf-8')",
                    "payload = {",
                    "  'schema': 'provider-conformance-case-results',",
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
        os.environ.pop("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY", None)
        os.environ["QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"] = (
            f"sha256:{'1' * 64}"
        )
        runtime_environment = {
            _RUNTIME_IDENTITY_ENV: _immutable_runtime_handoff()
        }
        try:
            with mock.patch.object(
                provider_conformance_runner.provider_conformance,
                "candidate_image_digest",
                return_value=f"sha256:{'1' * 64}",
            ), mock.patch.object(
                provider_conformance_runner,
                "_resolve_immutable_execution_candidate",
                return_value={
                    "active": True,
                    "receiptRef": (
                        ".qwq_output/env/alpha/local/alpha-local/process/"
                        "startup_attempt.json"
                    ),
                    "receiptDigest": f"sha256:{'4' * 64}",
                    "reason": "",
                },
            ), mock.patch.object(
                provider_conformance_runner.governance,
                "load_registry",
                return_value=registry,
            ), mock.patch.object(
                provider_conformance_runner.governance,
                "load_and_compile",
                return_value=(compiled, []),
            ), mock.patch.object(
                provider_conformance_runner.provider_conformance,
                "discover_test_sources",
                return_value=(
                    {
                        (
                            "assistant.model.generation",
                            "ext.llm.protocol_fixture",
                            "local_contract",
                        ): source
                    },
                    [],
                ),
            ), mock.patch.object(
                stackctl,
                "_provider_conformance_runtime_environment",
                return_value=runtime_environment,
            ) as select_runtime, mock.patch.object(
                stackctl,
                "_provider_conformance_runner",
                return_value=provider_conformance_runner,
            ):
                command_result = stackctl.command_provider_conformance(
                    argparse.Namespace(
                        matrix=False,
                        environment_matrix=False,
                        adapter_id="ext.llm.protocol_fixture",
                        capability_id="assistant.model.generation",
                        env="alpha",
                        layer="local_contract",
                        execute=True,
                        data_digest="",
                        image_digest="",
                    )
                )
            assert command_result["exitCode"] == 0
            select_runtime.assert_called_once_with("alpha")
            evidence_paths = list(output_root.rglob("*.evidence.json"))
            assert len(evidence_paths) == 1
            evidence_path = evidence_paths[0]
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            with mock.patch.object(
                provider_conformance,
                "resolve_nonprod_active_candidate",
                return_value={
                    "active": True,
                    "receiptRef": (
                        ".qwq_output/env/alpha/local/alpha-local/process/"
                        "startup_attempt.json"
                    ),
                    "receiptDigest": f"sha256:{'4' * 64}",
                    "reason": "",
                },
            ):
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
    assert runner_environment["runtimeIdentity"] == _immutable_runtime_handoff()
    assert evidence["testTarget"] == "assistant-model-real-adapter-harness"
    assert evidence["observabilityRefs"]["metrics"] == ["metric:provider-test"]
    assert evidence["nonPromotable"] is True
    assert evidence["attestationAuthority"] == "local"
    assert evidence["candidateStatus"] == "active_immutable"
    assert evidence["candidateReceiptRef"].endswith("startup_attempt.json")
    assert evidence["candidateReceiptDigest"] == f"sha256:{'4' * 64}"
    assert evidence["artifactAttestation"].startswith("local-sha256:")
    assert "version" not in evidence
    assert "version" not in execution_report


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
    calls: list[tuple[str, str, str, str]] = []
    evidence_paths: list[Path] = []

    def execute_cell(
        args: argparse.Namespace,
        **_kwargs: object,
    ) -> Path:
        calls.append(
            (
                args.adapter_id,
                args.environment,
                args.layer,
                os.environ["QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"],
            )
        )
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
            ],
            evidence_paths_out=evidence_paths,
            runtime_environments={
                environment: {
                    "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY": (
                        f"explicit-{environment}-runtime-identity"
                    )
                }
                for environment in provider_conformance.ENVIRONMENTS
            },
        )

    expected = [
        (
            compiled["selectedBindings"][environment]["assistant.model.generation"][
                "adapter_id"
            ],
            environment,
            layer,
            f"explicit-{environment}-runtime-identity",
        )
        for environment in provider_conformance.ENVIRONMENTS
        for layer in provider_conformance.LAYERS
    ]
    assert result == 0
    assert calls == expected
    assert evidence_paths == [
        Path(f"/tmp/{environment}-{layer}.evidence.json")
        for environment in provider_conformance.ENVIRONMENTS
        for layer in provider_conformance.LAYERS
    ]


def test_runner_rejects_stale_image_digest_before_emitting_evidence() -> None:
    previous_expected_image_digest = os.environ.get(
        "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"
    )
    os.environ["QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"] = f"sha256:{'2' * 64}"
    try:
        try:
            with mock.patch.object(
                provider_conformance_runner.provider_conformance,
                "candidate_image_digest",
                return_value=f"sha256:{'2' * 64}",
            ), mock.patch.dict(
                os.environ,
                {_RUNTIME_IDENTITY_ENV: _immutable_runtime_handoff()},
                clear=False,
            ):
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
            assert "does not match the packaged immutable candidate" in str(exc)
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
