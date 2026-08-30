"""候选 currentness 超时与真实漂移必须保持可区分。

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import diagnostics_shared


def _candidate_report(*, currentness_detail: str) -> dict[str, object]:
    candidate_root = Path("/tmp/immutable-candidate")
    active = {
        "baselineId": "sha256:" + "a" * 64,
        "candidateDir": str(candidate_root),
    }
    candidate = {
        "baselineId": active["baselineId"],
        "sourceRevision": "b" * 40,
        "workspaceStatusDigest": "sha256:" + "c" * 64,
        "workspaceDigest": "sha256:" + "d" * 64,
    }

    def can_reuse_package(*_args, purpose: str, **_kwargs):
        if purpose == "self_verify":
            return True, "reuse ok"
        return False, currentness_detail

    with (
        mock.patch.object(
            stackctl,
            "load_environment_topology",
            return_value={"targets": {"alpha-local": {"env": "alpha"}}},
        ),
        mock.patch.object(
            stackctl,
            "get_target",
            return_value={"env": "alpha"},
        ),
        mock.patch.object(
            stackctl,
            "active_deployment_candidate",
            return_value=active,
        ),
        mock.patch.object(
            diagnostics_shared,
            "resolve_openssl3",
            return_value=object(),
        ),
        mock.patch.object(
            diagnostics_shared,
            "openssl3_identity_report",
            return_value={"status": "ready"},
        ),
        mock.patch.object(
            stackctl,
            "can_reuse_package",
            side_effect=can_reuse_package,
        ),
        mock.patch.object(
            stackctl,
            "load_candidate_manifest",
            return_value=candidate,
        ),
    ):
        return diagnostics_shared._candidate_workspace_report(
            "alpha-local",
            purpose="currentness",
        )


def test_timeout_is_indeterminate_not_drift_or_mismatch__local_contract() -> None:
    report = _candidate_report(
        currentness_detail=(
            "verification_timeout: fingerprint rejected: "
            "deployment input currentness check timed out"
        )
    )

    assert report["status"] == "currentness_unavailable"
    assert report["currentSourceClaim"] == "not_evaluated"
    assert report["drifted"] is None
    assert report["mismatchedFields"] == []
    assert report["firstBlockerClass"] == "verification_timeout"
    assert report["nonPromotable"] is True


def test_digest_mismatch_remains_drifted__local_contract() -> None:
    report = _candidate_report(
        currentness_detail=(
            "fingerprint rejected: deployment input digest mismatch"
        )
    )

    assert report["status"] == "drifted"
    assert report["currentSourceClaim"] == "drifted"
    assert report["drifted"] is True
    assert report["mismatchedFields"] == ["deploymentInputClosure"]
    assert report["firstBlockerClass"] == "none"
    assert report["nonPromotable"] is True
