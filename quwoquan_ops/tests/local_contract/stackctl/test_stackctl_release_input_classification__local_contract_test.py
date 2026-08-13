# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-003
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from quwoquan_ops.cli import stackctl


CONTRACT_GRAPH_DIGEST = "sha256:" + "8" * 64
GRAPHQL_READ_REGISTRY = {
    "schema": "stackctl-graphql-read-registry-package",
    "candidateDigest": "sha256:" + "6" * 64,
}


def test_full_nonformal_log_sink_gate_reports_research_inputs_without_claim() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        report_dir = Path(temporary)
        result = stackctl._write_full_workload_log_sink_gate_block(
            report_dir=report_dir,
            report_target="alpha",
            resolved_target="alpha-local",
            formal_release=False,
            release_input_classification="research_inputs",
            contract_graph_digest=CONTRACT_GRAPH_DIGEST,
            timing={"startedAt": "2026-08-11T00:00:00Z"},
        )
        report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))

    assert report["workload"] == "full"
    assert report["formalRelease"] is False
    assert report["releaseInputClassification"] == "research_inputs"
    assert report["contractGraphDigest"] == CONTRACT_GRAPH_DIGEST
    assert result["releaseInputClassification"] == "research_inputs"
    assert result["contractGraphDigest"] == CONTRACT_GRAPH_DIGEST
    assert "commercialClaim" not in report
    assert "commercialClaim" not in result


def test_log_sink_control_uses_workload_without_release_claim() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        report_dir = Path(temporary)
        result = stackctl._write_product_telemetry_log_sink_control_report(
            report_dir=report_dir,
            target_name="alpha-local",
            action="health",
            receipt={
                "adapterId": "ext.obs.elasticsearch",
                "source": "service-config-postgres-telemetry",
                "status": "ready",
                "redactedDigest": "sha256:" + "1" * 64,
            },
            action_statuses=[{"action": "health", "status": "passed"}],
            gate_blocked=False,
            timing={"startedAt": "2026-08-11T00:00:00Z"},
        )
        report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))

    assert report["workload"] == "full"
    assert "releaseInputClassification" not in report
    assert "commercialClaim" not in report
    assert "commercialClaim" not in result


def test_stackctl_has_no_commercial_claim_second_truth() -> None:
    source = Path(stackctl.__file__).read_text(encoding="utf-8")
    assert "commercialClaim" not in source
    assert "commercial_claim" not in source


def test_package_identity_readback_is_exact_and_has_no_formal_release_claim() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        paths = {
            name: root / f"{name}.json"
            for name in ("report", "fingerprint", "manifest")
        }
        identity = {
            "releaseInputClassification": "commercial_inputs",
            "contractGraphDigest": CONTRACT_GRAPH_DIGEST,
            "graphqlReadRegistry": GRAPHQL_READ_REGISTRY,
        }
        for path in paths.values():
            path.write_text(json.dumps(identity) + "\n", encoding="utf-8")

        assert stackctl._validate_runtime_package_identity_readback(
            report_path=paths["report"],
            fingerprint_path=paths["fingerprint"],
            manifest_path=paths["manifest"],
        ) == identity

        for _label, field, value in (
            ("missing", "releaseInputClassification", None),
            ("unknown", "releaseInputClassification", "preview_inputs"),
            ("classification drift", "releaseInputClassification", "research_inputs"),
            ("Graph drift", "contractGraphDigest", "sha256:" + "7" * 64),
            (
                "GraphQL registry drift",
                "graphqlReadRegistry",
                {**GRAPHQL_READ_REGISTRY, "candidateDigest": "sha256:" + "5" * 64},
            ),
            ("formal claim", "formalRelease", False),
        ):
            with pytest.raises(ValueError):
                payload = dict(identity)
                if value is None:
                    payload.pop(field, None)
                else:
                    payload[field] = value
                paths["report"].write_text(
                    json.dumps(payload) + "\n",
                    encoding="utf-8",
                )
                stackctl._validate_runtime_package_identity_readback(
                    report_path=paths["report"],
                    fingerprint_path=paths["fingerprint"],
                    manifest_path=paths["manifest"],
                )
            paths["report"].write_text(
                json.dumps(identity) + "\n",
                encoding="utf-8",
            )


def test_runtime_package_outer_readback_resolves_report_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        monkeypatch.setattr(stackctl, "ROOT", root)
        report_ref = Path(".qwq_output/env/alpha/runs/package-alpha-local")
        report_dir = root / report_ref
        report_dir.mkdir(parents=True)
        identity = {
            "releaseInputClassification": "research_inputs",
            "contractGraphDigest": CONTRACT_GRAPH_DIGEST,
            "graphqlReadRegistry": GRAPHQL_READ_REGISTRY,
        }
        (report_dir / "report.json").write_text(
            json.dumps(identity) + "\n",
            encoding="utf-8",
        )
        fingerprint = root / "package-fingerprint.json"
        manifest = root / "manifest.json"
        for path in (fingerprint, manifest):
            path.write_text(json.dumps(identity) + "\n", encoding="utf-8")

        report_path = stackctl._runtime_package_report_path(str(report_ref))

        assert report_path == report_dir / "report.json"
        assert stackctl._validate_runtime_package_identity_readback(
            report_path=report_path,
            fingerprint_path=fingerprint,
            manifest_path=manifest,
        ) == identity
