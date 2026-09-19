# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""Contracts for target-bound, non-promotable prod-sim Provider rehearsal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from subprocess import CompletedProcess
import subprocess
import sys
import tempfile
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import provider_conformance_domain as subject

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64
_DIGEST_D = "sha256:" + "d" * 64


def _composition(*, bindings: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "runtimeCompositionDigest": _DIGEST_C,
        "bindings": bindings
        or [
            {
                "capabilityId": "integration.push.delivery",
                "adapterId": "ext.push.protocol_substitute",
                "state": "enabled",
            }
        ],
    }


def _identity_inputs(*, receipt_overrides: dict[str, object] | None = None):
    composition = _composition()
    candidate = {
        "environment": "prod",
        "target": "prod-sim",
        "baselineId": _DIGEST_A,
        "configurationDigest": _DIGEST_D,
        "providerRuntime": {
            "composition": composition,
            "rehearsal": {
                "kind": "local-provider-substitute",
                "nonPromotable": True,
            },
        },
    }
    receipt = {
        "status": "running",
        "env": "prod",
        "target": "prod-sim",
        "workload": "full",
        "candidateDigest": _DIGEST_A,
        "attemptId": "attempt-prod-sim",
        "providerRuntimeDigest": _DIGEST_C,
        "configurationDigest": _DIGEST_D,
        "failure": None,
        "cleanupFailure": None,
    }
    receipt.update(receipt_overrides or {})
    return composition, candidate, receipt


def _args(**overrides: object) -> argparse.Namespace:
    values = {
        "command": "provider-conformance",
        "prod_sim_rehearsal": True,
        "execute": True,
        "matrix": False,
        "environment_matrix": False,
        "env": "",
        "target": "prod-sim",
        "adapter_id": "",
        "capability_id": "",
        "layer": "",
        "image_digest": "",
        "data_digest": "",
        "report_dir": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _source(*, first_party: bool = True) -> dict[str, object]:
    return {
        "command": ["python3", "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/integration-service/ci/push_live_provider_conformance.py"],
        "target": "integration-service-provider-blackbox",
        "testSource": "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/integration-service/ci/push_live_provider_conformance.py",
        "testSourceDigest": _DIGEST_B,
        **({"prodSimFirstParty": {"service": "integration-service"}} if first_party else {}),
    }


def _case(identity: dict[str, str]) -> dict[str, object]:
    return {
        "schema": "provider-conformance-prod-sim-first-party-case-results",
        "status": "passed",
        "capabilityId": "integration.push.delivery",
        "adapterId": "ext.push.protocol_substitute",
        **identity,
        "invocations": [
            {
                "firstPartyService": "integration-service",
                "operation": "deliver",
                "invocationRef": "receipt:integration-provider-invocation",
                "effectReadbackRef": "receipt:integration-provider-effect",
                "cleanupReceipt": "receipt:integration-provider-cleanup",
                "observabilityRefs": {
                    "logs": ["log:integration-provider"],
                    "traces": ["trace:integration-provider"],
                    "metrics": ["metric:integration-provider"],
                },
            }
        ],
    }


def test_prod_sim_rehearsal_identity_rejects_candidate_startup_runtime_and_config_drift() -> None:
    for field, value in (
        ("candidateDigest", _DIGEST_B),
        ("providerRuntimeDigest", _DIGEST_B),
        ("configurationDigest", _DIGEST_B),
        ("workload", "partial"),
    ):
        composition, candidate, receipt = _identity_inputs(receipt_overrides={field: value})
        with (
            mock.patch.object(
                stackctl,
                "_active_provider_runtime",
                return_value={"baselineId": _DIGEST_A, "composition": composition},
            ),
            mock.patch.object(stackctl, "load_candidate_manifest", return_value=candidate),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=receipt),
            pytest.raises(ValueError, match="candidate/startup/provider runtime/config identity mismatch"),
        ):
            subject._prod_sim_rehearsal_identity()


def test_prod_sim_rehearsal_enumerates_required_capabilities_from_composition() -> None:
    composition = _composition(
        bindings=[
            {"capabilityId": "one.external", "adapterId": "ext.one.protocol_fixture", "state": "enabled"},
            {"capabilityId": "two.first_party", "adapterId": "ext.first_party.http_authority", "state": "enabled"},
            {"capabilityId": "three.external", "adapterId": "ext.three.protocol_fixture", "state": "enabled"},
        ]
    )
    governance = mock.Mock()
    governance.requires_provider_conformance.side_effect = (
        lambda binding: binding["adapter_id"] != "ext.first_party.http_authority"
    )
    with mock.patch.object(stackctl, "_external_provider_governance", return_value=governance):
        required = subject._prod_sim_rehearsal_required_capabilities(composition)

    assert required == [
        {"capabilityId": "one.external", "adapterId": "ext.one.protocol_fixture"},
        {"capabilityId": "three.external", "adapterId": "ext.three.protocol_fixture"},
    ]


@pytest.mark.parametrize(
    "source, message",
    [
        (None, "no source-declared"),
        (_source(first_party=False), "lacks a first-party"),
        ({**_source(), "command": ["python3", "run_generic_protocol_substitute_conformance.py"]}, "lacks a first-party"),
    ],
)
def test_prod_sim_rehearsal_rejects_missing_or_substitute_only_source(
    source: dict[str, object] | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        subject._prod_sim_first_party_source(
            source,
            capability_id="integration.push.delivery",
        )


def test_prod_sim_rehearsal_case_rejects_zero_invocation_and_missing_readback() -> None:
    identity = {
        "candidateDigest": _DIGEST_A,
        "startupAttemptId": "attempt-prod-sim",
        "providerRuntimeDigest": _DIGEST_C,
        "configDigest": _DIGEST_D,
    }
    capability = {"capabilityId": "integration.push.delivery", "adapterId": "ext.push.protocol_substitute"}
    zero = _case(identity)
    zero["invocations"] = []
    with pytest.raises(ValueError, match="zero Provider invocations"):
        subject._validate_prod_sim_first_party_case(
            zero, capability=capability, identity=identity, source=_source()
        )
    invalid = _case(identity)
    del invalid["invocations"][0]["effectReadbackRef"]
    with pytest.raises(ValueError, match="invocation/effect/readback/cleanup/observability"):
        subject._validate_prod_sim_first_party_case(
            invalid, capability=capability, identity=identity, source=_source()
        )


def test_prod_hosted_rejects_rehearsal_target() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        with (
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary) / "env/prod/runs/provider-conformance/prod-sim/run",
            ),
            mock.patch.object(
                stackctl,
                "validate_env_run_evidence_dir",
                side_effect=lambda path, **_kwargs: Path(path),
            ),
        ):
            result = subject._command_prod_sim_provider_rehearsal(
                _args(target="prod-hosted")
            )
    assert result["exitCode"] == 2
    assert result["nonPromotable"] is True
    assert result["readinessScope"] == "local_rehearsal"
    assert "only the prod-sim target" in result["details"][0]


def test_prod_sim_rehearsal_writes_fixed_non_promotable_report_without_formal_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = {
        "candidateDigest": _DIGEST_A,
        "startupAttemptId": "attempt-prod-sim",
        "providerRuntimeDigest": _DIGEST_C,
        "configDigest": _DIGEST_D,
    }
    source = _source()
    conformance = mock.Mock()
    conformance.discover_test_sources.return_value = ({}, [])
    conformance.source_for_cell.return_value = source

    def execute(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == source["command"]
        environment = kwargs["env"]
        assert environment["QWQ_PROVIDER_CONFORMANCE_PROD_SIM_IDENTITY"] == json.dumps(
            identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        case_path = Path(environment["QWQ_PROVIDER_CONFORMANCE_PROD_SIM_RESULT_PATH"])
        case_path.write_text(json.dumps(_case(identity)), encoding="utf-8")
        return CompletedProcess(command, 0, "", "")

    with tempfile.TemporaryDirectory() as temporary:
        output_root = Path(temporary) / ".qwq_output"
        report_dir = output_root / "env/prod/runs/provider-conformance/prod-sim/run"
        monkeypatch.setattr(
            stackctl,
            "validate_env_run_evidence_dir",
            lambda path, **_kwargs: Path(path),
        )
        with (
            mock.patch.object(stackctl, "resolve_report_dir", return_value=report_dir),
            mock.patch.object(stackctl, "_prod_sim_provider_rehearsal_environment", return_value={"BOUND": "true"}),
            mock.patch.object(stackctl, "_provider_conformance", return_value=conformance),
            mock.patch.object(subject, "_prod_sim_rehearsal_identity", return_value=(identity, _composition())),
            mock.patch.object(subject, "subprocess") as subprocess_module,
        ):
            subprocess_module.run.side_effect = execute
            result = subject._command_prod_sim_provider_rehearsal(_args())

        report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
        findings = json.loads((report_dir / "findings.json").read_text(encoding="utf-8"))

    assert result["exitCode"] == 0
    assert report["readinessScope"] == "local_rehearsal"
    assert report["releasePromotionClaimed"] is False
    assert report["nonPromotable"] is True
    assert report["identity"] == identity
    assert report["completedCapabilities"][0]["invocationCount"] == 1
    assert findings["nonPromotable"] is True
    assert [call[0] for call in conformance.method_calls] == [
        "discover_test_sources",
        "source_for_cell",
    ]
    assert conformance.source_for_cell.call_args.kwargs["layer"] == "prod-sim-rehearsal"


def test_stackctl_parser_keeps_rehearsal_separate_from_environment_matrix() -> None:
    args = stackctl.build_parser().parse_args(
        ["provider-conformance", "--prod-sim-rehearsal", "--execute", "--target", "prod-sim"]
    )
    assert args.prod_sim_rehearsal is True
    assert args.environment_matrix is False
    assert args.target == "prod-sim"
