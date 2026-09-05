# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
"""Environment ship accepts only an exact sealed producer handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment import ship_dispatch  # noqa: E402
from content.release.environment.release_runtime import (  # noqa: E402
    ReleaseAdmission,
    admit_environment_release,
)
from core.io import write_json  # noqa: E402
from core.release_layout import payload_digest  # noqa: E402
from core.source_digest import (  # noqa: E402
    SourceDefinitionSnapshot,
    content_source_revision,
)


def _release_and_handoff(
    root: Path,
    release_id: str = "release-a",
) -> tuple[Path, Path, dict[str, object]]:
    release = root / "data/releases" / release_id
    write_json(
        release / "payload/release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": release_id,
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": {
                "verified": 0,
                "unverified": 0,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": [],
            "researchAcceptedCount": 0,
            "commercialAcceptedCount": 0,
            "canonicalMerkle": "sha256:" + "0" * 64,
            "executionIds": ["20260905--travel-homepage-admission--china--pilot-001"],
            "sourceRevision": content_source_revision(
                source_digest="sha256:" + "2" * 64,
                entity_catalog_digest="sha256:" + "3" * 64,
            ),
            "sourceDigest": "sha256:" + "2" * 64,
            "entityCatalogDigest": "sha256:" + "3" * 64,
            "sourceDigests": [
                SourceDefinitionSnapshot("sha256:" + "2" * 64).to_document()
            ],
        },
    )
    write_json(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": {"entities": [], "posts": [], "creators": [], "tags": []},
        },
    )
    write_json(
        release / "payload/index/objects.json",
        {
            "schema": "quwoquan_data.release_object_index",
            "releaseId": release_id,
            "posts": [],
            "entities": [],
        },
    )
    write_json(
        release / "payload/sample_bundle.json",
        {
            "schema": "quwoquan_data.release_sample",
            "releaseId": release_id,
            "posts": [],
            "entities": [],
        },
    )
    write_json(
        release / "payload/media_manifest.json",
        {
            "schema": "quwoquan_data.release_media_manifest",
            "releaseId": release_id,
            "sourceOwner": "qwq_data",
            "assets": [],
            "issues": [],
            "counts": {"assets": 0, "issues": 0},
        },
    )
    handoff = release / "producer_release_handoff.json"
    document: dict[str, object] = {
        "schema": "quwoquan_data.producer_release_handoff",
        "releaseId": release_id,
        "handoffId": release_id,
        "release": {
            "scope": "output",
            "ref": f"data/releases/{release_id}",
            "payloadDigest": payload_digest(release),
            "headerRef": f"data/releases/{release_id}/payload/release.json",
            "headerDigest": "sha256:" + "4" * 64,
        },
    }
    write_json(handoff, document)
    return release, handoff, document


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _authority_ref() -> str:
    return f"handoff-ref-v1:sha256:{'1' * 64}:sha256:{'2' * 64}"


def _args(_handoff: Path, _root: Path) -> argparse.Namespace:
    return argparse.Namespace(handoff_ref=_authority_ref())


def test_admission_consumes_current_authority_and_exact_portable_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, handoff, document = _release_and_handoff(tmp_path)
    authority = {
        "artifacts": [
            ".qwq_output/data/releases/release-a/producer_release_handoff.json"
        ]
    }
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        "content.release.environment.release_runtime.handoff_store.read",
        lambda ref, **_kwargs: observed.setdefault("authorityRef", ref) or b"authority",
    )
    monkeypatch.setattr(
        "content.release.environment.release_runtime.handoff_consumer.validate_published_bytes",
        lambda ref, raw, **kwargs: (
            observed.update(ref=ref, raw=raw, **kwargs) or authority
        ),
    )
    monkeypatch.setattr(
        "content.release.environment.release_runtime.handoff_store.resolve_unique_artifact",
        lambda *_args, **_kwargs: (
            ".qwq_output/data/releases/release-a/producer_release_handoff.json",
            handoff,
            handoff.read_bytes(),
            _sha(handoff),
        ),
    )
    monkeypatch.setattr(
        "content.release.environment.release_runtime.read_producer_release_handoff",
        lambda *_args, **_kwargs: document,
    )

    admission = admit_environment_release(
        _args(handoff, tmp_path),
        repo_root=ROOT,
        output_root=tmp_path,
        release_root=tmp_path / "data/releases",
    )

    assert admission.release == release
    assert admission.release_id == release.name
    assert admission.manifest_digest == payload_digest(release)
    assert admission.handoff_ref == _authority_ref()
    assert admission.handoff_artifact_ref.endswith("producer_release_handoff.json")
    assert admission.handoff_artifact_digest == _sha(handoff)
    assert observed["validate_current"] is True


def test_admission_rejects_old_output_relative_handoff_and_removed_digest_flag(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="HANDOFF_AUTHORITY_INVALID"):
        admit_environment_release(
            argparse.Namespace(
                handoff_ref="data/releases/release-a/producer_release_handoff.json",
                handoff_digest="sha256:" + "0" * 64,
            ),
            repo_root=ROOT,
            output_root=tmp_path,
            release_root=tmp_path / "data/releases",
        )
    parser = _ship_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "ship",
                "apply",
                "--handoff-ref",
                _authority_ref(),
                "--handoff-digest",
                "sha256:" + "0" * 64,
                "--env",
                "alpha",
            ]
        )


def test_authority_or_artifact_drift_fails_before_dispatch_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        ship_dispatch,
        "release_operation_guard",
        lambda **_kwargs: events.append("lock"),
    )
    monkeypatch.setattr(
        ship_dispatch,
        "admit_environment_release",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("DATA.RELEASE.HANDOFF_AUTHORITY_DRIFT")
        ),
    )
    with pytest.raises(SystemExit, match="HANDOFF_AUTHORITY_DRIFT"):
        ship_dispatch.dispatch_ship(
            argparse.Namespace(
                ship_command="apply",
                env="alpha",
                run_id="run-a",
                handoff_ref=_authority_ref(),
            ),
            release_root=tmp_path / "data/releases",
            output_root=tmp_path,
            repo_root=ROOT,
            apply=lambda _args: events.append("apply"),
            rollback=lambda _args: events.append("rollback"),
            verify=lambda _args: events.append("verify"),
        )
    assert events == []


def _ship_parser() -> argparse.ArgumentParser:
    from content.release.environment import cli as ship_cli

    parser = argparse.ArgumentParser()
    ship_cli.register_parser(parser.add_subparsers(dest="command", required=True))
    return parser


@pytest.mark.parametrize("command", ["apply", "activate", "verify", "rollback"])
def test_cli_accepts_authoritative_handoff_ref_only(command: str) -> None:
    parser = _ship_parser()
    argv = ["ship", command, "--handoff-ref", _authority_ref(), "--env", "alpha"]
    if command in {"activate", "verify"}:
        argv += ["--import-run-id", "apply-a"]
    if command == "rollback":
        argv += [
            "--from-release-id",
            "release-current",
            "--from-manifest-digest",
            "sha256:" + "2" * 64,
        ]
    parsed = parser.parse_args(argv)
    assert parsed.handoff_ref == _authority_ref()
    assert not hasattr(parsed, "handoff_digest")


def test_cli_activate_requires_sealed_admission_and_apply_predecessor() -> None:
    parser = _ship_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["ship", "activate", "--env", "alpha", "--import-run-id", "apply-a"]
        )
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["ship", "activate", "--env", "alpha", "--handoff-ref", _authority_ref()]
        )


def _empty_baseline_attestation(
    root: Path,
    release_id: str = "baseline-a",
) -> tuple[Path, Path, dict[str, object]]:
    release = root / "data/releases" / release_id
    source_digest = SourceDefinitionSnapshot("sha256:" + "2" * 64).to_document()
    header: dict[str, object] = {
        "schema": "quwoquan_data.release",
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "releaseKind": "empty_baseline",
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 0,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "researchAcceptedCount": 0,
        "commercialAcceptedCount": 0,
        "canonicalMerkle": "sha256:" + "0" * 64,
        "executionIds": [],
        "sourceDigests": [source_digest],
    }
    write_json(release / "payload/release.json", header)
    write_json(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": {
                "entities": [],
                "posts": [],
                "creators": [],
                "tags": [],
            },
        },
    )
    attestation: dict[str, object] = {
        **header,
        "carrierCounts": {
            "homepage": 0,
            "article": 0,
            "image": 0,
            "video": 0,
            "total": 0,
        },
        "entityCount": 0,
        "postCount": 0,
        "creatorCount": 0,
        "tagCount": 0,
        "payloadSha256": payload_digest(release),
        "recordedAt": "2026-09-05T00:00:00Z",
    }
    attestation["schema"] = "quwoquan_data.release_attestation"
    path = release / "attestations/release.json"
    write_json(path, attestation)
    return release, path, attestation


def _attestation_args(
    attestation: Path,
    root: Path,
    *,
    digest: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        system_attestation_ref=attestation.relative_to(root).as_posix(),
        system_attestation_digest=digest or _sha(attestation),
    )


def test_empty_baseline_admission_uses_independent_system_attestation_pair(
    tmp_path: Path,
) -> None:
    release, attestation, _ = _empty_baseline_attestation(tmp_path)

    admission = admit_environment_release(
        _attestation_args(attestation, tmp_path),
        repo_root=ROOT,
        output_root=tmp_path,
        release_root=tmp_path / "data/releases",
    )

    assert admission.release == release
    assert admission.release_id == release.name
    assert admission.manifest_digest == payload_digest(release)
    assert admission.admission_kind == "empty_baseline_attestation"
    assert admission.system_attestation_ref == (
        f"data/releases/{release.name}/attestations/release.json"
    )
    assert admission.system_attestation_digest == _sha(attestation)
    assert admission.result_envelope() == {
        "admissionKind": "empty_baseline_attestation",
        "systemAttestationRef": f"data/releases/{release.name}/attestations/release.json",
        "systemAttestationDigest": _sha(attestation),
    }


@pytest.mark.parametrize(
    "updates",
    [
        {
            "system_attestation_ref": "data/releases/baseline-a/attestations/release.json"
        },
        {"system_attestation_digest": "sha256:" + "0" * 64},
        {
            "handoff_ref": _authority_ref(),
            "system_attestation_ref": "data/releases/baseline-a/attestations/release.json",
            "system_attestation_digest": "sha256:" + "0" * 64,
        },
        {
            "handoff_ref": _authority_ref(),
            "system_attestation_digest": "sha256:" + "0" * 64,
        },
    ],
)
def test_admission_rejects_partial_mixed_or_multiple_pairs(
    updates: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="ADMISSION_PAIR_INVALID"):
        admit_environment_release(
            argparse.Namespace(**updates),
            repo_root=ROOT,
            output_root=Path("/unused"),
            release_root=Path("/unused/data/releases"),
        )


def test_empty_baseline_admission_rejects_noncanonical_ref_and_digest_drift(
    tmp_path: Path,
) -> None:
    _, attestation, _ = _empty_baseline_attestation(tmp_path)
    with pytest.raises(ValueError, match="SYSTEM_ATTESTATION_REF_INVALID"):
        admit_environment_release(
            argparse.Namespace(
                system_attestation_ref="data/releases/baseline-a/release.json",
                system_attestation_digest=_sha(attestation),
            ),
            repo_root=ROOT,
            output_root=tmp_path,
            release_root=tmp_path / "data/releases",
        )
    with pytest.raises(ValueError, match="SYSTEM_ATTESTATION_DIGEST_DRIFT"):
        admit_environment_release(
            _attestation_args(
                attestation,
                tmp_path,
                digest="sha256:" + "f" * 64,
            ),
            repo_root=ROOT,
            output_root=tmp_path,
            release_root=tmp_path / "data/releases",
        )


def test_empty_baseline_admission_rejects_symlink_ancestor(
    tmp_path: Path,
) -> None:
    real_root = tmp_path / "real"
    _, attestation, _ = _empty_baseline_attestation(real_root)
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)
    linked_attestation = linked_root / attestation.relative_to(real_root)

    with pytest.raises(ValueError, match="SYSTEM_ATTESTATION_SYMLINK_REJECTED"):
        admit_environment_release(
            _attestation_args(linked_attestation, linked_root),
            repo_root=ROOT,
            output_root=linked_root,
            release_root=linked_root / "data/releases",
        )


def test_empty_baseline_admission_rejects_schema_identity_and_payload_drift(
    tmp_path: Path,
) -> None:
    release, attestation, document = _empty_baseline_attestation(tmp_path)
    cases = [
        ({**document, "sourceOwner": "other"}, "SYSTEM_ATTESTATION_SCHEMA_INVALID"),
        ({**document, "releaseKind": "content"}, "SYSTEM_ATTESTATION"),
        ({**document, "releaseId": "other"}, "SYSTEM_ATTESTATION_IDENTITY_DRIFT"),
        ({**document, "payloadSha256": "sha256:" + "f" * 64}, "PAYLOAD_DIGEST_DRIFT"),
    ]
    for changed, error_code in cases:
        write_json(attestation, changed)
        with pytest.raises(ValueError, match=error_code):
            admit_environment_release(
                _attestation_args(attestation, tmp_path),
                repo_root=ROOT,
                output_root=tmp_path,
                release_root=tmp_path / "data/releases",
            )
    write_json(attestation, document)
    desired = release / "payload/desired_state.json"
    desired_document = json.loads(desired.read_text())
    desired_document["releaseId"] = "other"
    write_json(desired, desired_document)
    document["payloadSha256"] = payload_digest(release)
    write_json(attestation, document)
    with pytest.raises(ValueError, match="RELEASE_ID_DRIFT"):
        admit_environment_release(
            _attestation_args(attestation, tmp_path),
            repo_root=ROOT,
            output_root=tmp_path,
            release_root=tmp_path / "data/releases",
        )


def test_dispatch_invalid_attestation_fails_before_lock_or_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        ship_dispatch,
        "release_operation_guard",
        lambda **_kwargs: events.append("lock"),
    )
    with pytest.raises(SystemExit, match="SYSTEM_ATTESTATION_MISSING"):
        ship_dispatch.dispatch_ship(
            argparse.Namespace(
                ship_command="apply",
                env="gamma",
                run_id="apply-a",
                system_attestation_ref=(
                    "data/releases/baseline-a/attestations/release.json"
                ),
                system_attestation_digest="sha256:" + "0" * 64,
            ),
            release_root=tmp_path / "data/releases",
            output_root=tmp_path,
            repo_root=ROOT,
            apply=lambda _args: events.append("apply"),
            rollback=lambda _args: events.append("rollback"),
            verify=lambda _args: events.append("verify"),
        )
    assert events == []


@pytest.mark.parametrize("command", ["apply", "activate", "verify", "rollback"])
def test_cli_accepts_exactly_one_system_attestation_pair(command: str) -> None:
    parser = _ship_parser()
    argv = [
        "ship",
        command,
        "--system-attestation-ref",
        "data/releases/baseline-a/attestations/release.json",
        "--system-attestation-digest",
        "sha256:" + "1" * 64,
        "--env",
        "alpha",
    ]
    if command in {"activate", "verify"}:
        argv += ["--import-run-id", "apply-a"]
    if command == "rollback":
        argv += [
            "--from-release-id",
            "release-current",
            "--from-manifest-digest",
            "sha256:" + "2" * 64,
        ]
    parsed = parser.parse_args(argv)
    assert parsed.system_attestation_ref.endswith("/attestations/release.json")
    assert parsed.handoff_ref is None
    assert not hasattr(parsed, "handoff_digest")


@pytest.mark.parametrize("command", ["apply", "activate", "verify", "rollback"])
def test_cli_rejects_crossed_admission_pairs(command: str) -> None:
    parser = _ship_parser()
    argv = [
        "ship",
        command,
        "--handoff-ref",
        _authority_ref(),
        "--system-attestation-digest",
        "sha256:" + "1" * 64,
        "--env",
        "alpha",
    ]
    if command in {"activate", "verify"}:
        argv += ["--import-run-id", "apply-a"]
    if command == "rollback":
        argv += [
            "--from-release-id",
            "release-current",
            "--from-manifest-digest",
            "sha256:" + "2" * 64,
        ]
    parsed = parser.parse_args(argv)
    with pytest.raises(ValueError, match="ADMISSION_PAIR_INVALID"):
        admit_environment_release(
            parsed,
            repo_root=ROOT,
            output_root=Path("/unused"),
            release_root=Path("/unused/data/releases"),
        )


def test_empty_baseline_header_identity_must_match_attestation(
    tmp_path: Path,
) -> None:
    release, attestation, document = _empty_baseline_attestation(tmp_path)
    header_path = release / "payload/release.json"
    header = json.loads(header_path.read_text())
    header["releaseClass"] = "research"
    header["productLifecycleState"] = "research"
    write_json(header_path, header)
    document["payloadSha256"] = payload_digest(release)
    write_json(attestation, document)

    with pytest.raises(ValueError, match="SYSTEM_ATTESTATION_RELEASE_ID_DRIFT"):
        admit_environment_release(
            _attestation_args(attestation, tmp_path),
            repo_root=ROOT,
            output_root=tmp_path,
            release_root=tmp_path / "data/releases",
        )


def test_empty_baseline_payload_identity_files_reject_symlinks(
    tmp_path: Path,
) -> None:
    release, attestation, _ = _empty_baseline_attestation(tmp_path)
    desired = release / "payload/desired_state.json"
    outside = tmp_path / "outside-desired.json"
    outside.write_bytes(desired.read_bytes())
    desired.unlink()
    desired.symlink_to(outside)

    with pytest.raises(ValueError, match="SYSTEM_ATTESTATION_SYMLINK_REJECTED"):
        admit_environment_release(
            _attestation_args(attestation, tmp_path),
            repo_root=ROOT,
            output_root=tmp_path,
            release_root=tmp_path / "data/releases",
        )


def _environment_result_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": "alpha",
        "releaseId": "release-a",
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "containsUnverifiedAssets": False,
        "manifestDigest": "sha256:" + "a" * 64,
        "admissionKind": "producer_handoff",
        "handoffRef": _authority_ref(),
        "handoffArtifactRef": ".qwq_output/data/releases/release-a/producer_release_handoff.json",
        "handoffArtifactDigest": "sha256:" + "b" * 64,
        "runId": "apply-a",
        "status": "prepared",
        "startedAt": "2026-09-05T00:00:00Z",
        "endedAt": "2026-09-05T00:00:01Z",
        "durationMs": 1000,
        "verificationChecksum": "sha256:" + "c" * 64,
    }
    document.update(overrides)
    return document


def test_environment_result_schema_separates_authority_artifact_and_baseline() -> None:
    from core.schema import assert_valid

    base = _environment_result_document()
    assert_valid(base, "release", "environment_release_result")
    baseline = {
        **base,
        "releaseId": "baseline-a",
        "admissionKind": "empty_baseline_attestation",
        "systemAttestationRef": "data/releases/baseline-a/attestations/release.json",
        "systemAttestationDigest": "sha256:" + "d" * 64,
    }
    for field in ("handoffRef", "handoffArtifactRef", "handoffArtifactDigest"):
        baseline.pop(field)
    assert_valid(baseline, "release", "environment_release_result")
    for legacy in ("admissionRef", "admissionDigest"):
        with pytest.raises(ValueError):
            assert_valid(
                {**base, legacy: "legacy"}, "release", "environment_release_result"
            )


def test_environment_result_schema_requires_exact_failure_diagnostics() -> None:
    from core.schema import assert_valid

    failed = _environment_result_document(
        status="failed", failedStage="ship.apply", error="import failed"
    )
    assert_valid(failed, "release", "environment_release_result")
    for missing in ("failedStage", "error"):
        invalid = dict(failed)
        invalid.pop(missing)
        with pytest.raises(ValueError):
            assert_valid(invalid, "release", "environment_release_result")
    for status in ("completed", "dry_run", "prepared"):
        with pytest.raises(ValueError):
            assert_valid(
                _environment_result_document(status=status, error="bad"),
                "release",
                "environment_release_result",
            )
