"""无类别 Data readiness 与独立显式 Exit 的精确证据契约。"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-034
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import output_paths
from quwoquan_ops.cli.commands.app_preflight_readiness import _validate_data_schema
from quwoquan_ops.tests.support.app_content_preflight_test_support import write_release_readiness


def _write_data_readiness_fixture(*, output_root: Path, environment="gamma", release_id="pilot-002", verify_run_id="verify-001"):
    return write_release_readiness(output_root, environment=environment, release_id=release_id, verify_run_id=verify_run_id)


def _load(path: Path, digest: str):
    value = json.loads(path.read_text())
    return stackctl._load_data_release_readiness(environment=value["environment"], release_id=value["releaseId"], verify_run_id=value["verifyRunId"], manifest_digest=digest)


def _resign(path: Path, value: dict):
    value.pop("verificationChecksum", None)
    value["verificationChecksum"] = stackctl._canonical_document_checksum(value)
    path.write_text(json.dumps(value))


def test_release_closes_guest_media_avatar_and_prepared_apply(monkeypatch, tmp_path):
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    path, digest = _write_data_readiness_fixture(output_root=tmp_path)
    value, loaded = _load(path, digest)
    assert loaded == path
    assert value["importRunId"] == "activate-001"
    assert "/apply-001/import.json" in value["contentImportReportRef"]
    assert value["counts"]["premiumPlayableVideos"] == 1
    assert value["acceptedCount"] == 3
    assert "researchAcceptedCount" not in value
    assert "commercialAcceptedCount" not in value
    assert stackctl._release_feed_post_expectations(value) == {
        "content_feed": {"post-article", "post-image", "post-video"},
        "video_book_feed": {"post-video"},
        "premium_feed": {"post-video"},
    }


@pytest.mark.parametrize("explicit_root", [False, True])
def test_data_readiness_uses_writer_root_not_host_runtime(monkeypatch, tmp_path, explicit_root):
    # spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
    data_root, host_root = tmp_path / "repo/.qwq_output", tmp_path / "host-runtime"
    monkeypatch.setattr(output_paths, "DEFAULT_OUTPUT_ROOT", data_root)
    monkeypatch.setattr(output_paths, "DEFAULT_LOCAL_RUNTIME_OUTPUT_ROOT", host_root)
    monkeypatch.delenv("QWQ_OUTPUT_ROOT", raising=False)
    if explicit_root:
        data_root = tmp_path / "explicit-output"
        monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(data_root))
    path, digest = _write_data_readiness_fixture(output_root=data_root, environment="alpha")
    original = path.read_bytes()
    assert _load(path, digest)[1] == path
    assert stackctl.env_runs_root("alpha") == (data_root if explicit_root else host_root) / "env/alpha/runs"
    # host 上的同名副本永远不能替代 writer 原件。
    shadow = host_root / path.relative_to(data_root)
    shadow.parent.mkdir(parents=True)
    shadow.write_bytes(original)
    path.unlink()
    with pytest.raises(ValueError, match="missing"):
        stackctl._load_data_release_readiness(environment="alpha", release_id="pilot-002", verify_run_id="verify-001", manifest_digest=digest)


@pytest.mark.parametrize("mutation", ["environment", "release", "run", "escape", "symlink_file", "symlink_parent"])
def test_data_readiness_path_and_identity_fail_closed(monkeypatch, tmp_path, mutation):
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    path, digest = _write_data_readiness_fixture(output_root=tmp_path, environment="alpha")
    params = dict(environment="alpha", release_id="pilot-002", verify_run_id="verify-001", manifest_digest=digest)
    if mutation in {"symlink_file", "symlink_parent"}:
        selected = path if mutation == "symlink_file" else path.parent
        saved = selected.with_name("original")
        selected.rename(saved)
        selected.symlink_to(saved, target_is_directory=mutation == "symlink_parent")
    elif mutation == "escape":
        params["release_id"] = "../pilot-002"
    else:
        value = json.loads(path.read_bytes())
        value[{"environment": "environment", "release": "releaseId", "run": "verifyRunId"}[mutation]] = "other"
        _resign(path, value)
    with pytest.raises(ValueError):
        stackctl._load_data_release_readiness(**params)


def test_unverified_rights_are_preserved_without_blocking_public_readiness(monkeypatch, tmp_path):
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    path, digest = write_release_readiness(tmp_path, unverified=True)
    value, _ = _load(path, digest)
    assert value["containsUnverifiedAssets"] is True
    assert value["authorizationRequiredAssetIds"] == ["image-asset"]
    assert value["rightsStatusCounts"]["unverified"] == 1
    assert stackctl._load_test_data_release_readiness(environment="gamma", release_id="pilot-002", verify_run_id="verify-001", manifest_digest=digest)[0] == value


@pytest.mark.parametrize("retired", ["research", "consumer", "commercial", "production", "import", "default"])
def test_retired_release_categories_are_rejected(monkeypatch, tmp_path, retired):
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    path, digest = _write_data_readiness_fixture(output_root=tmp_path)
    value = json.loads(path.read_text())
    for field in ("releaseClass", "productLifecycleState", "readinessPhase"):
        value[field] = retired
        value["activationEnvelope"][field] = retired
    value["activationEnvelopeDigest"] = stackctl._canonical_document_checksum(value["activationEnvelope"])
    _resign(path, value)
    with pytest.raises(ValueError, match="schema"):
        _load(path, digest)
    with pytest.raises(ValueError, match="schema"):
        stackctl._load_test_data_release_readiness(environment="gamma", release_id="pilot-002", verify_run_id="verify-001", manifest_digest=digest)


@pytest.mark.parametrize("mutation", ["checksum", "guest", "media", "avatar", "premium", "prepared", "activation_report", "unknown_field"])
def test_required_evidence_fails_closed(monkeypatch, tmp_path, mutation):
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    path, digest = _write_data_readiness_fixture(output_root=tmp_path)
    value = json.loads(path.read_text())
    if mutation == "checksum":
        value["verificationChecksum"] = "sha256:" + "0" * 64
        path.write_text(json.dumps(value))
    elif mutation == "media":
        (tmp_path / value["mediaManifestRef"]).write_text("{}")
    elif mutation == "avatar":
        post_path = tmp_path / value["postApiVerificationRef"]
        post = json.loads(post_path.read_text())
        post["creators"][0]["avatarProbe"]["hashVerified"] = False
        post_path.write_text(json.dumps(post))
    elif mutation == "prepared":
        result_path = tmp_path / "env/gamma/runs/data-release/pilot-002/activate-001/result.json"
        result = json.loads(result_path.read_text())
        result["importRunId"] = "different-apply"
        result_path.write_text(json.dumps(result))
    else:
        if mutation == "guest":
            value.pop("guestLogin")
        elif mutation == "premium":
            value["feedQueries"][-1]["matchedPostIds"] = []
        elif mutation == "activation_report":
            value["activationEnvelope"]["importReportRef"] = "env/gamma/runs/data-release/pilot-002/activate-001/import.json"
        else:
            value["retiredIsolationProof"] = "unexpected"
        _resign(path, value)
    with pytest.raises(ValueError):
        _load(path, digest)


def _write_lifecycle_exit_fixture(output_root: Path, *, readiness: dict):
    env, release, digest = readiness["environment"], readiness["releaseId"], readiness["manifestDigest"]
    runs = {"originalImportRunId": "activate-original", "originalVerifyRunId": "verify-original", "rollbackRunId": "rollback-001", "rollbackVerifyRunId": "verify-rollback", "replayImportRunId": readiness["importRunId"], "replayVerifyRunId": readiness["verifyRunId"]}
    value = {"schema": "quwoquan_data.environment_release_lifecycle_exit", "environment": env, "sourceOwner": "qwq_data", "exitRunId": "exit-001", "originalReleaseId": release, "originalManifestDigest": digest, "rollbackToReleaseId": "rollback-baseline", "rollbackToManifestDigest": "sha256:" + "8" * 64, "replayManifestDigest": digest, **runs, "recordedAt": "2026-09-09T00:00:00Z", "passed": True}
    for ref_field, run_field in (("originalImportResultRef", "originalImportRunId"), ("originalVerifyResultRef", "originalVerifyRunId"), ("rollbackResultRef", "rollbackRunId"), ("rollbackVerifyResultRef", "rollbackVerifyRunId"), ("replayImportResultRef", "replayImportRunId"), ("replayVerifyResultRef", "replayVerifyRunId")):
        bound_release = "rollback-baseline" if ref_field.startswith("rollback") else release
        ref = f"env/{env}/runs/data-release/{bound_release}/{runs[run_field]}/result.json"
        value[ref_field] = ref
        path = output_root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("{}")
    attestation = output_root / "data/releases/rollback-baseline/attestations/release.json"
    attestation.parent.mkdir(parents=True, exist_ok=True)
    attestation.write_text(json.dumps({"releaseId": "rollback-baseline", "sourceOwner": "qwq_data", "payloadSha256": value["rollbackToManifestDigest"]}))
    ref = f"env/{env}/runs/release-lifecycle-exit/{release}/exit-001/lifecycle-exit.json"
    path = output_root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    _resign(path, value)
    _validate_data_schema(json.loads(path.read_text()), "environment_release_lifecycle_exit")
    return ref, path


@pytest.mark.parametrize("pair", ["original", "replay"])
def test_lifecycle_exit_accepts_exact_original_or_replay_pair(monkeypatch, tmp_path, pair):
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    path, digest = _write_data_readiness_fixture(output_root=tmp_path)
    value = json.loads(path.read_text())
    ref, exit_path = _write_lifecycle_exit_fixture(tmp_path, readiness=value)
    exit_receipt = json.loads(exit_path.read_text())
    value["importRunId"] = exit_receipt[f"{pair}ImportRunId"]
    value["verifyRunId"] = exit_receipt[f"{pair}VerifyRunId"]
    assert stackctl._load_data_release_lifecycle_exit(environment="gamma", release_id="pilot-002", manifest_digest=digest, readiness=value, lifecycle_exit_ref=ref)[1] == exit_path


def test_lifecycle_exit_rejects_replay_verify_misbinding(monkeypatch, tmp_path):
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    path, digest = _write_data_readiness_fixture(output_root=tmp_path)
    value = json.loads(path.read_text())
    ref, _ = _write_lifecycle_exit_fixture(tmp_path, readiness=value)
    value["verifyRunId"] = "later-unrelated-verify"
    with pytest.raises(ValueError, match="exact readiness import/verify pair"):
        stackctl._load_data_release_lifecycle_exit(environment="gamma", release_id="pilot-002", manifest_digest=digest, readiness=value, lifecycle_exit_ref=ref)
