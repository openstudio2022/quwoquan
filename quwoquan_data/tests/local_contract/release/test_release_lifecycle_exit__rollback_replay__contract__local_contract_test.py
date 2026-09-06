"""Rollback/replay Exit evidence is create-once and recomputed from run bindings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical.lifecycle_exit import (
    ReleaseLifecycleExitError,
    write_lifecycle_exit_receipt,
)
from core.source_digest import SourceDefinitionSnapshot, content_source_revision
from verify import release_lifecycle_exit as exit_verify
from verify import verify_release_lifecycle as lifecycle_verify

ORIGINAL = "20260728--android-homepage--pilot-002"
ROLLBACK = "20260728--android-homepage--empty-baseline-001"
DIGEST = "sha256:" + "a" * 64
ROLLBACK_DIGEST = "sha256:" + "b" * 64
SOURCE_DIGEST = "sha256:" + "d" * 64
ENTITY_CATALOG_DIGEST = "sha256:" + "e" * 64


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _attestation(path: Path, release_id: str, digest: str, *, baseline: bool) -> None:
    lifecycle = {
        "releaseClass": "research",
        "productLifecycleState": "research",
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 0 if baseline else 1,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "researchAcceptedCount": 0 if baseline else 1,
        "commercialAcceptedCount": 0,
    }
    source_identity = (
        {}
        if baseline
        else {
            "sourceRevision": content_source_revision(
                source_digest=SOURCE_DIGEST,
                entity_catalog_digest=ENTITY_CATALOG_DIGEST,
            ),
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
        }
    )
    _write_json(
        path / release_id / "attestations/release.json",
        {
            "schema": "quwoquan_data.release_attestation",
            "releaseId": release_id,
            "sourceOwner": "qwq_data",
            "releaseKind": "empty_baseline" if baseline else "content",
            **lifecycle,
            **source_identity,
            "executionIds": [] if baseline else ["execution-001"],
            "carrierCounts": {
                "homepage": 0 if baseline else 1,
                "article": 0,
                "image": 0,
                "video": 0,
                "total": 0 if baseline else 1,
            },
            "entityCount": 0 if baseline else 1,
            "postCount": 0,
            "creatorCount": 0,
            "tagCount": 0,
            "canonicalMerkle": "sha256:" + "c" * 64,
            "sourceDigests": [SourceDefinitionSnapshot(SOURCE_DIGEST).to_document()],
            "payloadSha256": digest,
            "recordedAt": "2026-07-28T00:00:00Z",
        },
    )


def _run(output: Path, release_id: str, run_id: str, kind: str) -> None:
    root = output / "env/gamma/runs/data-release" / release_id / run_id
    _write_json(root / "run.json", {"kind": kind})
    _write_json(root / "result.json", {"runId": run_id})


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    releases = tmp_path / "releases"
    output = tmp_path / "output"
    _attestation(releases, ORIGINAL, DIGEST, baseline=False)
    _attestation(releases, ROLLBACK, ROLLBACK_DIGEST, baseline=True)
    for release_id, run_id, kind in (
        (ORIGINAL, "apply-original", "apply"),
        (ORIGINAL, "verify-original", "verify"),
        (ROLLBACK, "rollback-baseline", "rollback"),
        (ROLLBACK, "verify-baseline", "verify"),
        (ORIGINAL, "apply-replay", "apply"),
        (ORIGINAL, "verify-replay", "verify"),
    ):
        _run(output, release_id, run_id, kind)
    return releases, output


def _write(
    releases: Path,
    output: Path,
) -> tuple[dict, Path]:
    return write_lifecycle_exit_receipt(
        environment="gamma",
        original_release_id=ORIGINAL,
        original_import_run_id="apply-original",
        original_verify_run_id="verify-original",
        rollback_to_release_id=ROLLBACK,
        rollback_run_id="rollback-baseline",
        rollback_verify_run_id="verify-baseline",
        replay_import_run_id="apply-replay",
        replay_verify_run_id="verify-replay",
        exit_run_id="exit-001",
        release_root=releases,
        output_root=output,
    )


def test_lifecycle_exit__binds_original_rollback_and_same_digest_replay__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    releases, output = _fixture(tmp_path)
    calls: list[tuple[str, str, str, str | None]] = []

    def valid_lifecycle(
        release_id: str,
        *,
        import_run_id: str,
        verify_run_id: str,
        rollback_from_release_id: str | None,
        **_kwargs: object,
    ) -> list[str]:
        calls.append(
            (release_id, import_run_id, verify_run_id, rollback_from_release_id)
        )
        return []

    monkeypatch.setattr(exit_verify, "environment_lifecycle_issues", valid_lifecycle)

    receipt, path = _write(releases, output)

    assert receipt["originalManifestDigest"] == DIGEST
    assert receipt["replayManifestDigest"] == DIGEST
    assert receipt["rollbackToManifestDigest"] == ROLLBACK_DIGEST
    assert receipt["passed"] is True
    assert exit_verify.lifecycle_exit_issues(
        receipt,
        path=path,
        release_root=releases,
        output_root=output,
    ) == []
    assert calls[:3] == [
        (ORIGINAL, "apply-original", "verify-original", None),
        (ROLLBACK, "rollback-baseline", "verify-baseline", ORIGINAL),
        (ORIGINAL, "apply-replay", "verify-replay", None),
    ]


def test_lifecycle_exit__rejects_replay_digest_drift_and_overwrite__local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    releases, output = _fixture(tmp_path)
    monkeypatch.setattr(
        exit_verify,
        "environment_lifecycle_issues",
        lambda *_args, **_kwargs: [],
    )
    receipt, path = _write(releases, output)
    drifted = dict(receipt)
    drifted["replayManifestDigest"] = "sha256:" + "0" * 64
    drifted["verificationChecksum"] = exit_verify.checksum(drifted)

    assert any(
        "replayManifestDigest must equal original payload digest" in issue
        for issue in exit_verify.lifecycle_exit_issues(
            drifted,
            path=path,
            release_root=releases,
            output_root=output,
        )
    )
    with pytest.raises(ReleaseLifecycleExitError, match="append-only Exit run"):
        _write(releases, output)


def test_environment_lifecycle__activation_uses_prepared_apply_receipts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release_id = "release-a"
    output = tmp_path / "output"
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        lifecycle_verify,
        "release_lifecycle_issues",
        lambda *_args, **_kwargs: [],
    )

    def _read_object(path: Path, **_kwargs: object) -> dict:
        if path.name == "desired_state.json":
            return {
                "desiredRefs": {
                    "entities": [],
                    "posts": [],
                    "creators": [],
                    "tags": [],
                }
            }
        if path.parent.name == "attestations":
            return {"payloadSha256": DIGEST}
        return {"releaseKind": "content"}

    def _run_document(
        run: Path, name: str, _schema: str, **_kwargs: object
    ) -> dict:
        run_id = run.name
        if name == "applied_ref.json":
            return {"environment": "gamma", "releaseId": release_id}
        if run_id == "activate-001":
            if name == "run.json":
                return {
                    "environment": "gamma",
                    "releaseId": release_id,
                    "runId": run_id,
                    "kind": "activate",
                }
            return {
                "environment": "gamma",
                "releaseId": release_id,
                "runId": run_id,
                "importRunId": "apply-001",
                "status": "completed",
            }
        if run_id == "apply-001":
            if name == "run.json":
                return {
                    "environment": "gamma",
                    "releaseId": release_id,
                    "runId": run_id,
                    "kind": "apply",
                }
            return {
                "environment": "gamma",
                "releaseId": release_id,
                "runId": run_id,
                "status": "prepared",
            }
        if name == "run.json":
            return {
                "environment": "gamma",
                "releaseId": release_id,
                "runId": run_id,
                "kind": "verify",
            }
        return {
            "environment": "gamma",
            "releaseId": release_id,
            "runId": run_id,
            "importRunId": "activate-001",
            "status": "completed",
        }

    def _import_issues(**kwargs: object) -> list[str]:
        captured["run"] = kwargs["run"]
        captured["result"] = kwargs["result"]
        return []

    monkeypatch.setattr(lifecycle_verify, "_read_object", _read_object)
    monkeypatch.setattr(lifecycle_verify, "_run_document", _run_document)
    monkeypatch.setattr(lifecycle_verify, "_rollback_issues", lambda **_kwargs: [])
    monkeypatch.setattr(lifecycle_verify, "_import_receipt_issues", _import_issues)
    monkeypatch.setattr(
        lifecycle_verify,
        "_bound_report",
        lambda **_kwargs: {"environment": "gamma", "releaseId": release_id},
    )

    issues = lifecycle_verify.environment_lifecycle_issues(
        release_id,
        environment="gamma",
        import_run_id="activate-001",
        verify_run_id="verify-001",
        release_root=tmp_path / "releases",
        output_root=output,
    )

    assert issues == []
    assert Path(captured["run"]).name == "apply-001"
    assert captured["result"]["status"] == "prepared"
