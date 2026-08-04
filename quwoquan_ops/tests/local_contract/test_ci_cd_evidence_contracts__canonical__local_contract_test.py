"""local_contract: CI/CD evidence contracts remain canonical and single-track."""

from __future__ import annotations

from pathlib import Path

import pytest

from quwoquan_ops.ci import render_environment_chain_timing_diagnostics as diagnostics
from quwoquan_ops.gate import verify_ci_cd_evidence_contracts as gate

REPO_ROOT = Path(__file__).resolve().parents[3]


def timing_summary(
    *,
    status: str = "within_budget",
    seconds: int = 600,
    missing_evidence: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema": "ci-timing-summary",
        "generatedAt": "2026-07-28T00:00:00Z",
        "workflow": {"gateKey": "release", "name": "release", "title": "release"},
        "workflowRunId": "42",
        "sourceGitSha": "a" * 40,
        "candidateDigest": "sha256:" + "b" * 64,
        "status": status,
        "timestamps": {},
        "durations": {
            "machineCriticalPathSeconds": max(0, seconds - 20),
            "calendarLeadTimeSeconds": seconds,
        },
        "budget": {"softSeconds": 600, "hardSeconds": 1800, "phaseSeconds": {}},
        "criticalPath": {"source": "github_run_calendar", "seconds": seconds},
        "phases": [
            {
                "name": "candidate",
                "durationSeconds": 120,
                "budgetSeconds": 120,
                "status": "within_budget",
            }
        ],
        "missingEvidence": missing_evidence or [],
        "notes": [],
    }


def test_repository_evidence_chain_has_no_contract_drift() -> None:
    assert gate.evidence_contract_findings(REPO_ROOT) == []


def test_gate_repo_invokes_the_canonical_evidence_gate() -> None:
    gate_source = (REPO_ROOT / "quwoquan_ops/gate/gate_repo.sh").read_text(
        encoding="utf-8"
    )

    assert gate.CANONICAL_SCHEMAS == {
        "ci-timing-summary",
        "release-evidence-manifest",
        "ai-ci-advisory",
    }
    assert "python3 quwoquan_ops/gate/verify_ci_cd_evidence_contracts.py" in gate_source


def test_release_collector_registry_requires_real_provider_conformance() -> None:
    _, registry = gate.SCHEMA_REGISTRIES[
        "quwoquan_ops/cli/prod/collect_release_artifact_descriptors.py"
    ]

    assert registry["providerEvidence"] == "provider-conformance-readiness"
    assert "providerBindings" not in registry
    assert "compiled-external-provider-bindings" not in registry.values()


def test_scanner_rejects_legacy_envelopes_and_compatibility_escapes() -> None:
    def invalid_sha256_fixture(value: str) -> str:
        return "sha256:" + value

    source = "\n".join(
        (
            "schema: ci-timing-summary-v2",
            "type: CiTimingSummary v2",
            "type: ReleaseEvidenceManifest-v1",
            "type: AiCiAdvisory2",
            "schema: qwq.foo.v1",
            "schemaVersion: 2",
            "contractVersion: 2",
            "registryRevision: 2",
            "versions: {imageVersion: old}",
            "schema: mainline-release-artifact",
            "manifestDigest: " + invalid_sha256_fixture("old"),
            "mode=compat",
            "compatibility-alias",
            "dual-read",
            "dual_write",
            "legacy-alias",
            "--warn-only",
        )
    )

    findings = gate.scan_text("quwoquan_ops/ci/example.py", source)
    details = "\n".join(finding.detail for finding in findings)

    assert "versioned evidence identity is forbidden" in details
    assert "versioned schema identity is forbidden: qwq.foo.v1" in details
    assert "legacy release schema identity is forbidden" in details
    assert "versions envelope is forbidden" in details
    for escape in (
        "mode=compat",
        "compatibility-alias",
        "dual-read",
        "dual_write",
        "legacy-alias",
        "--warn-only",
    ):
        assert f"compatibility escape is forbidden: {escape}" in details
    for field in (
        "schemaVersion",
        "contractVersion",
        "registryRevision",
        "manifestDigest",
    ):
        assert f"legacy field is forbidden: {field}" in details


def test_schema_suffix_detector_does_not_treat_product_versions_as_schema() -> None:
    source = "\n".join(
        (
            'versionName: "product.v1"',
            'appVersion: "release.v2"',
            'schema: "qwq.foo"',
        )
    )

    assert gate.scan_text("quwoquan_ops/ci/example.yaml", source) == []


def test_rollout_policy_rejects_only_a_top_level_contract_version_envelope() -> None:
    relative_path = "quwoquan_ops/policies/config-release/slo_thresholds.yaml"

    findings = gate.top_level_envelope_findings(
        relative_path,
        "version: 1\nthresholds: {}\n",
    )
    assert [finding.detail for finding in findings] == [
        "top-level contract version envelope is forbidden"
    ]
    assert (
        gate.top_level_envelope_findings(
            relative_path,
            "thresholds:\n  version: 1\n",
        )
        == []
    )


def test_scanner_allows_validator_declarations_and_explicit_negative_fixtures() -> None:
    negative_fixture = "schemaVersion mainline-release-artifact mode=compat"

    assert (
        gate.scan_text(
            "quwoquan_ops/tests/local_contract/"
            "test_ci_cd_evidence_contracts__canonical__local_contract_test.py",
            negative_fixture,
        )
        == []
    )
    assert gate.scan_text("spec.md", "禁止 --warn-only 和 dual-read") == []
    assert (
        gate.scan_text(
            "validator.py",
            "FORBIDDEN_FIELDS = {'schema': 'qwq.foo.v1', "
            "'schemaVersion': True, 'versions': True}",
            allowed_validator_lines={1},
        )
        == []
    )


def test_shared_stackctl_scan_is_limited_to_release_evidence_functions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "stackctl.py"
    source.write_text(
        "\n".join(
            (
                "def release_evidence():",
                "    return {'schema': 'release-evidence-manifest'}",
                "",
                "def data_readiness():",
                "    return {'manifestDigest': 'data-domain-digest'}",
            )
        ),
        encoding="utf-8",
    )

    assert (
        gate._scoped_source_findings(
            source,
            "quwoquan_ops/cli/stackctl.py",
            frozenset({"release_evidence"}),
        )
        == []
    )
    findings = gate._scoped_source_findings(
        source,
        "quwoquan_ops/cli/stackctl.py",
        frozenset({"data_readiness"}),
    )
    assert [finding.detail for finding in findings] == [
        "legacy field is forbidden: manifestDigest"
    ]


def test_timing_diagnostics_reads_nested_canonical_fields() -> None:
    summary = timing_summary(seconds=601)

    item = diagnostics.summary_item(summary, key="release", label="release")
    phases = diagnostics.phase_index(summary)

    assert item["durationSeconds"] == 601
    assert item["softBudgetSeconds"] == 600
    assert item["hardBudgetSeconds"] == 1800
    assert item["status"] == "released_over_soft_budget"
    assert item["sloEligible"] is True
    assert phases["candidate"]["durationSeconds"] == 120
    assert phases["candidate"]["budgetSeconds"] == 120


def test_historical_incomplete_timing_is_excluded_from_slo() -> None:
    summary = timing_summary(
        status="historical_incomplete",
        seconds=0,
        missing_evidence=["durations.queueSeconds"],
    )

    item = diagnostics.summary_item(summary, key="historical", label="historical")
    phases = diagnostics.phase_index(summary)

    assert item["status"] == "historical_incomplete"
    assert item["sloEligible"] is False
    assert item["deltaFromSoftSeconds"] is None
    assert phases["candidate"]["sloEligible"] is False


def test_timing_diagnostics_rejects_retired_flat_shape() -> None:
    with pytest.raises(ValueError, match="canonical ci-timing-summary"):
        diagnostics.require_timing_summary(
            {
                "schema": "ci-timing-summary-v2",
                "criticalPathSeconds": 600,
                "budgetStatus": "within_budget",
                "phaseBudgetsSeconds": {},
                "criticalPathDefinition": "legacy",
            },
            label="legacy",
        )
