# spec_ref: specs/feature-tree/discovery-content/spec.md
"""Content release-control Data adapters and activation orchestration contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment import _ship_operations, importers  # noqa: E402
from content.release.environment.release_runtime import ReleaseAdmission  # noqa: E402
from content.release.environment.run_evidence import (  # noqa: E402
    create_run,
    write_environment_result,
)
from content.release.model import DeploymentEnvironment  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from core.release_layout import payload_digest  # noqa: E402
from core.schema import assert_valid  # noqa: E402

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
VALID_ENVS = frozenset({"alpha"})


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-042
def _homepage_mapping_proofs(root: Path) -> tuple[Path, Path, Path]:
    release = root / "releases/release-a"
    write_json(release / "payload/desired_state.json", {"desiredRefs": {"entities": ["opaque-a", "opaque-b"]}})
    digest = payload_digest(release)
    mapping = {"opaque-a": "hp-entity-owned-a", "opaque-b": "hp-entity-owned-b"}
    entries = [{"entityRef": ref, "homepageId": mapping[ref]} for ref in sorted(mapping)]
    mapping_digest = "sha256:" + hashlib.sha256(json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    report = {
        "schema": "quwoquan_service.homepage_import_report", "releaseId": release.name,
        "env": "alpha", "dryRun": False, "sourceOwner": "qwq_data", "manifestDigest": digest,
        "projectionVersion": 7, "closureDigest": DIGEST_B, "expected": 2, "projected": 2,
        "entityRefToHomepageId": mapping, "entityRefMappingDigest": mapping_digest,
        "replayed": False, "verifiedAt": "2026-09-09T00:00:00Z", "finishedAt": "2026-09-09T00:00:01Z", "issues": [],
    }
    candidate = {
        "schema": "quwoquan.homepage_release_candidate_receipt", "status": "found",
        "identity": {"environment": "alpha", "sourceOwner": "qwq_data", "releaseId": release.name, "manifestDigest": digest},
        "projectionVersion": 7, "closureDigest": DIGEST_B, "verifiedAt": report["verifiedAt"],
        "counts": {"expected": 2, "projected": 2}, "entityRefMappingDigest": mapping_digest,
    }
    report_path, candidate_path = root / "report.json", root / "candidate.json"
    write_json(report_path, report)
    write_json(candidate_path, candidate)
    return release, report_path, candidate_path


def test_content_command_consumes_only_candidate_authenticated_homepage_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release, report, candidate = _homepage_mapping_proofs(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(importers.subprocess, "run", lambda command, **_kwargs: (commands.append(command) or SimpleNamespace(returncode=0)))
    original = importers.assert_import_report_contract
    monkeypatch.setattr(importers, "assert_import_report_contract", lambda path, **kwargs: {} if path.name == "import.json" else original(path, **kwargs))
    importers.run_content_importer(
        release=release, env="alpha", run=tmp_path, mongo_uri="mongodb://example.invalid",
        media_avatar_base_url="", media_image_base_url="", media_video_base_url="", dry_run=False,
        creator_candidate_receipt=tmp_path / "creator.json", homepage_import_report=report,
        homepage_candidate_receipt=candidate,
    )
    assert len(commands) == 1
    assert commands[0][commands[0].index("--homepage-report") + 1] == str(report)
    assert commands[0][commands[0].index("--homepage-candidate-receipt") + 1] == str(candidate)


@pytest.mark.parametrize("drift", ["environment", "release", "owner", "manifest", "count", "closure", "version", "mapping", "digest", "dry-run", "candidate-status", "candidate-mapping"])
def test_content_rejects_homepage_mapping_drift_before_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str) -> None:
    release, report, candidate = _homepage_mapping_proofs(tmp_path)
    payload = read_json(report)
    if drift in {"environment", "release", "owner", "manifest"}:
        field = {"environment": "env", "release": "releaseId", "owner": "sourceOwner", "manifest": "manifestDigest"}[drift]
        payload[field] = DIGEST_B if drift == "manifest" else "other"
    elif drift == "count": payload["projected"] = 1
    elif drift == "closure": payload["closureDigest"] = DIGEST_A
    elif drift == "version": payload["projectionVersion"] = 8
    elif drift == "mapping": payload["entityRefToHomepageId"]["opaque-a"] = "hp-tampered"
    elif drift == "digest": payload["entityRefMappingDigest"] = DIGEST_A
    elif drift == "dry-run": payload["dryRun"] = True
    else:
        proof = read_json(candidate)
        if drift == "candidate-status": proof = {"schema": proof["schema"], "status": "not_found", "identity": proof["identity"]}
        else: proof["entityRefMappingDigest"] = DIGEST_A
        write_json(candidate, proof)
    write_json(report, payload)
    monkeypatch.setattr(importers.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("drift reached Content subprocess"))
    with pytest.raises((RuntimeError, ValueError)):
        importers.run_content_importer(
            release=release, env="alpha", run=tmp_path, mongo_uri="mongodb://example.invalid",
            media_avatar_base_url="", media_image_base_url="", media_video_base_url="", dry_run=False,
            creator_candidate_receipt=tmp_path / "creator.json", homepage_import_report=report,
            homepage_candidate_receipt=candidate,
        )


def _write_receipt(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")


def _candidate(release_id: str = "release-a") -> dict[str, object]:
    return {
        "schema": "quwoquan.content_release_candidate_receipt",
        "status": "found",
        "environment": "alpha",
        "sourceOwner": "qwq_data",
        "releaseId": release_id,
        "manifestDigest": DIGEST_A,
        "releaseClass": "production",
        "releaseKind": "content",
        "mode": "sync",
        "deletePolicy": "tombstone",
        "projectionVersion": 7,
        "verifiedAt": "2026-09-05T00:00:00Z",
        "closureDigests": {"posts": DIGEST_A, "facts": DIGEST_A, "media": DIGEST_A},
        "counts": {
            "postsExpected": 1,
            "postsProjected": 1,
            "outboxExpected": 1,
            "outboxProjected": 1,
            "mediaExpected": 0,
            "mediaProjected": 0,
        },
        "generatedAt": "2026-09-05T00:00:01Z",
    }


def _owner_candidate(owner: str, manifest_digest: str = DIGEST_A) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": f"quwoquan.{owner}_release_candidate_receipt",
        "status": "found",
        "environment": "alpha",
        "sourceOwner": "qwq_data",
        "releaseId": "release-a",
        "manifestDigest": manifest_digest,
        "projectionVersion": 7,
        "verifiedAt": "2026-09-05T00:00:00Z",
        "closureDigest": DIGEST_A,
        "generatedAt": "2026-09-05T00:00:01Z",
    }
    if owner == "tag":
        base.update(
            counts={"expected": 1, "projected": 1},
            canonicalDigest=DIGEST_A,
            releaseKind="content",
            tagRefsDigest=DIGEST_A,
        )
    elif owner == "creator":
        base.update(
            counts={"expected": 1, "projected": 1},
            authorIds=["author-a"],
            profileDigests=[{"creatorId": "creator-a", "authorId": "author-a", "digest": DIGEST_A}],
        )
    else:
        identity = {
            "environment": base.pop("environment"),
            "sourceOwner": base.pop("sourceOwner"),
            "releaseId": base.pop("releaseId"),
            "manifestDigest": base.pop("manifestDigest"),
        }
        base.pop("generatedAt")
        base.update(
            identity=identity,
            counts={"expected": 1, "projected": 1},
            entityRefMappingDigest=DIGEST_A,
        )
    return base

def _active(
    *,
    found: bool,
    release_id: str = "release-old",
    digest: str = DIGEST_B,
    revision: int = 3,
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": "quwoquan.content_release_active_receipt",
        "status": "found" if found else "not_found",
        "environment": "alpha",
        "sourceOwner": "qwq_data",
        "generatedAt": "2026-09-05T00:00:02Z",
    }
    if found:
        result.update(
            releaseId=release_id,
            manifestDigest=digest,
            releaseClass="production",
            projectionVersion=5,
            revision=revision,
            activatedAt="2026-09-05T00:00:00Z",
        )
    return result


def _activation(expected: dict[str, object], *, revision: int) -> dict[str, object]:
    predecessor = {
        "found": expected["status"] == "found",
        "sourceOwner": "qwq_data",
        "revision": int(expected.get("revision", 0)),
    }
    if predecessor["found"]:
        predecessor.update(
            releaseId=expected["releaseId"],
            manifestDigest=expected["manifestDigest"],
        )
    return {
        "schema": "quwoquan.content_release_activation_receipt",
        "status": "activated",
        "environment": "alpha",
        "sourceOwner": "qwq_data",
        "target": {"releaseId": "release-a", "manifestDigest": DIGEST_A},
        "expectedActive": predecessor,
        "previousActive": dict(predecessor),
        "active": {
            "releaseId": "release-a",
            "manifestDigest": DIGEST_A,
            "releaseClass": "production",
            "projectionVersion": 8,
            "revision": revision,
            "activatedAt": "2026-09-05T00:00:03Z",
        },
        "counts": {
            "postsMaterialized": 1,
            "postsRemoved": 0,
            "mediaAssetsMaterialized": 0,
            "mediaAssetsRemoved": 0,
            "outboxEventsReady": 1,
            "outboxEventsAppended": 1,
        },
        "generatedAt": "2026-09-05T00:00:03Z",
    }


def test_receipt_schemas_accept_exact_found_and_not_found_shapes() -> None:
    assert_valid(_candidate(), "release", "content_release_candidate_receipt")
    assert_valid(_active(found=False), "release", "content_release_active_receipt")
    assert_valid(_active(found=True), "release", "content_release_active_receipt")
    assert_valid(
        _activation(_active(found=False), revision=1),
        "release",
        "content_release_activation_receipt",
    )


def test_release_control_adapters_build_exact_flags_and_never_expose_mongo_uri(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        operation = command[command.index("--operation") + 1]
        report = Path(command[command.index("--report") + 1])
        if operation == "query-candidate":
            _write_receipt(report, _candidate())
        elif operation == "query-active":
            _write_receipt(report, _active(found=False))
        else:
            _write_receipt(report, _activation(_active(found=False), revision=1))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(importers.subprocess, "run", run)
    candidate = importers.query_content_release_candidate(
        env="alpha",
        mongo_uri="mongodb://user:secret@example.invalid",
        release_id="release-a",
        manifest_digest=DIGEST_A,
        report_path=tmp_path / "candidate.json",
        output_root=tmp_path,
    )
    pre = importers.query_content_active_release(
        env="alpha",
        mongo_uri="mongodb://user:secret@example.invalid",
        report_path=tmp_path / "pre.json",
        output_root=tmp_path,
    )
    activation = importers.activate_content_release(
        env="alpha",
        mongo_uri="mongodb://user:secret@example.invalid",
        release_id="release-a",
        manifest_digest=DIGEST_A,
        expected_active=pre.document,
        report_path=tmp_path / "activation.json",
        output_root=tmp_path,
    )
    assert candidate.digest.startswith("sha256:")
    assert activation.document["active"]["revision"] == 1
    assert commands[0][commands[0].index("--operation") + 1] == "query-candidate"
    assert "--expected-active-empty" in commands[2]
    assert "--expected-active-release-id" not in commands[2]

    monkeypatch.setattr(
        importers.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=17),
    )
    with pytest.raises(SystemExit) as exc:
        importers.query_content_active_release(
            env="alpha",
            mongo_uri="mongodb://user:secret@example.invalid",
            report_path=tmp_path / "failed.json",
            output_root=tmp_path,
        )
    assert "secret" not in str(exc.value)


def test_activate_adapter_derives_revision_bearing_expected_tuple(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _active(found=True)
    command_seen: list[str] = []

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        command_seen.extend(command)
        report = Path(command[command.index("--report") + 1])
        _write_receipt(report, _activation(expected, revision=4))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(importers.subprocess, "run", run)
    importers.activate_content_release(
        env="alpha",
        mongo_uri="mongodb://example.invalid",
        release_id="release-a",
        manifest_digest=DIGEST_A,
        expected_active=expected,
        report_path=tmp_path / "activation.json",
        output_root=tmp_path,
    )
    assert (
        command_seen[command_seen.index("--expected-active-release-id") + 1]
        == "release-old"
    )
    assert (
        command_seen[command_seen.index("--expected-active-manifest-digest") + 1]
        == DIGEST_B
    )
    assert command_seen[command_seen.index("--expected-active-revision") + 1] == "3"
    assert "--expected-active-empty" not in command_seen


def test_candidate_digest_drift_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "candidate.json"
    _write_receipt(path, _candidate())
    expected = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    loaded = importers.load_content_release_candidate_receipt(
        path,
        output_root=tmp_path,
        environment="alpha",
        release_id="release-a",
        manifest_digest=DIGEST_A,
        expected_digest=expected,
    )
    path.write_text(path.read_text() + " ", encoding="utf-8")
    with pytest.raises(RuntimeError, match="digest drift"):
        importers.assert_content_release_evidence_unchanged(loaded)


def test_activate_rejects_active_receipt_identity_before_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        nonlocal called
        called = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(importers.subprocess, "run", run)
    drifted = {**_active(found=False), "environment": "beta"}
    with pytest.raises(RuntimeError, match="environment/sourceOwner"):
        importers.activate_content_release(
            env="alpha",
            mongo_uri="mongodb://example.invalid",
            release_id="release-a",
            manifest_digest=DIGEST_A,
            expected_active=drifted,
            report_path=tmp_path / "activation.json",
            output_root=tmp_path,
        )
    assert not called


def test_content_receipt_loader_rejects_pre_and_post_digest_drift(
    tmp_path: Path,
) -> None:
    for name, document in (
        ("pre.json", _active(found=False)),
        ("post.json", _active(found=True)),
        ("activation.json", _activation(_active(found=False), revision=1)),
    ):
        path = tmp_path / name
        _write_receipt(path, document)
        expected = importers.file_byte_digest(path)
        path.write_text(path.read_text() + " ", encoding="utf-8")
        schema = (
            "quwoquan.content_release_activation_receipt"
            if name == "activation.json"
            else "quwoquan.content_release_active_receipt"
        )
        with pytest.raises(RuntimeError, match="digest drift"):
            importers.load_content_release_receipt(
                path,
                output_root=tmp_path,
                schema=schema,
                environment="alpha",
                expected_digest=expected,
            )


def _release(root: Path) -> tuple[Path, ReleaseAdmission]:
    release = root / "data/releases/release-a"
    write_json(
        release / "payload/release.json",
        {
            "releaseId": "release-a",
            "releaseClass": "production",
            "productLifecycleState": "production",
            "containsUnverifiedAssets": True,
        },
    )
    write_json(
        release / "payload/desired_state.json",
        {"releaseId": "release-a", "desiredRefs": {"entities": [], "posts": []}},
    )
    digest = payload_digest(release)
    return release, ReleaseAdmission(
        release=release,
        contract={
            "releaseId": "release-a",
            "desiredRefs": {"entities": [], "posts": []},
        },
        release_id="release-a",
        manifest_digest=digest,
        admission_kind="producer_handoff",
        handoff_ref=f"handoff-ref-v1:{DIGEST_B}:{DIGEST_B}",
        handoff_artifact_ref="data/releases/release-a/producer_release_handoff.json",
        handoff_artifact_digest=DIGEST_B,
    )


def _evidence(
    path: Path, document: dict[str, object], root: Path
) -> importers.ContentReleaseEvidence:
    _write_receipt(path, document)
    return importers.ContentReleaseEvidence(
        document=document,
        path=path,
        ref=path.relative_to(root).as_posix(),
        digest=importers.file_byte_digest(path),
    )


def _activate_dependencies(
    root: Path, admission: ReleaseAdmission, pre: dict[str, object]
) -> SimpleNamespace:
    target = SimpleNamespace(
        environment=DeploymentEnvironment.ALPHA, mongo_uri="mongodb://example.invalid"
    )

    def query_active(**kwargs: object) -> importers.ContentReleaseEvidence:
        path = Path(kwargs["report_path"])
        if "pre" in path.name:
            return _evidence(path, pre, root)
        revision = int(pre.get("revision", 0)) + 1
        active = _active(
            found=True,
            release_id="release-a",
            digest=admission.manifest_digest,
            revision=revision,
        )
        active["projectionVersion"] = 8
        active["activatedAt"] = "2026-09-05T00:00:03Z"
        return _evidence(path, active, root)

    def activate(**kwargs: object) -> importers.ContentReleaseEvidence:
        expected = dict(kwargs["expected_active"])
        document = _activation(expected, revision=int(expected.get("revision", 0)) + 1)
        document["target"]["manifestDigest"] = admission.manifest_digest
        document["active"]["manifestDigest"] = admission.manifest_digest
        return _evidence(Path(kwargs["report_path"]), document, root)

    def _fenced_evidence(kwargs: dict[str, object], owner: str) -> importers.OwnerReleaseEvidence:
        path = Path(kwargs["report_path"])
        document = {"status": "passed", **dict(kwargs["fence"]), "owner": owner}
        return _evidence(path, document, root)

    return SimpleNamespace(
        output_root=root,
        admit_release=lambda _args: admission,
        run_root=lambda env, release_id, run_id: (
            root / "env" / env / "runs/data-release" / release_id / run_id
        ),
        create_run=lambda env, release_id, run_id, *, kind: create_run(
            output_root=root,
            environment=env,
            release_id=release_id,
            run_id=run_id,
            kind=kind,
            valid_environments=VALID_ENVS,
        ),
        resolve_environment_release_target=lambda _env: target,
        assert_environment_release_policy=lambda **_kwargs: None,
        assert_target_action_allowed=lambda **_kwargs: None,
        load_content_release_candidate_receipt=importers.load_content_release_candidate_receipt,
        load_owner_release_candidate_receipt=importers.load_owner_release_candidate_receipt,
        query_content_active_release=query_active,
        activate_content_release=activate,
        write_verification_result=write_environment_result,
        write_applied_ref=lambda **kwargs: write_json(
            kwargs["run"] / "applied_ref.json", {"releaseId": kwargs["release_id"]}
        ),
        require_owner_local_staging_admission=(
            __import__(
                "content.release.environment.owner_local_staging_admission",
                fromlist=["require_owner_local_staging_admission"],
            ).require_owner_local_staging_admission
        ),
        readback_tag_at_content_fence=lambda **kwargs: _fenced_evidence(kwargs, "tag"),
        readback_creator_at_content_fence=lambda **kwargs: _fenced_evidence(kwargs, "creator"),
        readback_homepage_at_content_fence=lambda **kwargs: _fenced_evidence(kwargs, "homepage"),
        readback_content_at_content_fence=lambda **kwargs: _fenced_evidence(kwargs, "content"),
        now_compact=lambda: "20260905T000000Z",
    )


def _prepare_apply(root: Path, admission: ReleaseAdmission) -> None:
    run = create_run(
        output_root=root,
        environment="alpha",
        release_id="release-a",
        run_id="apply-1",
        kind="apply",
        valid_environments=VALID_ENVS,
    )
    candidate = run / "content-candidate-receipt.json"
    _write_receipt(
        candidate, {**_candidate(), "manifestDigest": admission.manifest_digest}
    )
    owner_fields: dict[str, str] = {}
    for owner in ("tag", "creator", "homepage"):
        path = run / f"{owner}-candidate-receipt.json"
        _write_receipt(path, _owner_candidate(owner, admission.manifest_digest))
        owner_fields[f"{owner}CandidateReceiptRef"] = path.relative_to(root).as_posix()
        owner_fields[f"{owner}CandidateReceiptDigest"] = importers.file_byte_digest(path)
    write_environment_result(
        run / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": "alpha",
            "releaseId": "release-a",
            "releaseClass": "production",
            "productLifecycleState": "production",
            "containsUnverifiedAssets": True,
            "manifestDigest": admission.manifest_digest,
            **admission.result_envelope(),
            "runId": "apply-1",
            "status": "prepared",
            "contentImportReportRef": "env/alpha/runs/data-release/release-a/apply-1/import.json",
            "contentCandidateReceiptRef": candidate.relative_to(root).as_posix(),
            "contentCandidateReceiptDigest": importers.file_byte_digest(candidate),
            **owner_fields,
        },
    )


@pytest.mark.parametrize("found", [False, True])
def test_activate_consumes_prepared_apply_and_derives_expected_from_query(
    tmp_path: Path,
    found: bool,
) -> None:
    _release_path, admission = _release(tmp_path)
    _prepare_apply(tmp_path, admission)
    pre = _active(found=found)
    deps = _activate_dependencies(tmp_path, admission, pre)
    _ship_operations.activate_release(
        argparse.Namespace(
            env="alpha",
            import_run_id="apply-1",
            run_id=f"activate-{found}",
            confirm_prod_apply=False,
            release_admission=admission,
        ),
        dependencies=deps,
    )
    run = tmp_path / f"env/alpha/runs/data-release/release-a/activate-{found}"
    result = read_json(run / "result.json")
    assert result["status"] == "completed"
    assert result["importRunId"] == "apply-1"
    assert result["contentCandidateReceiptDigest"].startswith("sha256:")
    assert result["contentPreActiveReceiptDigest"].startswith("sha256:")
    assert (run / "applied_ref.json").is_file()


def test_activate_rejects_candidate_digest_drift_before_run_create(
    tmp_path: Path,
) -> None:
    _release_path, admission = _release(tmp_path)
    _prepare_apply(tmp_path, admission)
    candidate = (
        tmp_path
        / "env/alpha/runs/data-release/release-a/apply-1/content-candidate-receipt.json"
    )
    candidate.write_text(candidate.read_text() + " ", encoding="utf-8")
    deps = _activate_dependencies(tmp_path, admission, _active(found=False))
    with pytest.raises(RuntimeError, match="digest drift"):
        _ship_operations.activate_release(
            argparse.Namespace(
                env="alpha",
                import_run_id="apply-1",
                run_id="activate-drift",
                confirm_prod_apply=False,
                release_admission=admission,
            ),
            dependencies=deps,
        )
    assert not (
        tmp_path / "env/alpha/runs/data-release/release-a/activate-drift"
    ).exists()


def test_activate_applied_ref_failure_seals_failed_not_completed_result(
    tmp_path: Path,
) -> None:
    _release_path, admission = _release(tmp_path)
    _prepare_apply(tmp_path, admission)
    deps = _activate_dependencies(tmp_path, admission, _active(found=False))

    def _fail_applied_ref(**_kwargs: object) -> None:
        raise OSError("applied ref disk failure")

    deps.write_applied_ref = _fail_applied_ref
    with pytest.raises(OSError, match="applied ref disk failure"):
        _ship_operations.activate_release(
            argparse.Namespace(
                env="alpha",
                import_run_id="apply-1",
                run_id="activate-applied-ref-failed",
                confirm_prod_apply=False,
                release_admission=admission,
            ),
            dependencies=deps,
        )

    run = (
        tmp_path
        / "env/alpha/runs/data-release/release-a/activate-applied-ref-failed"
    )
    result = read_json(run / "result.json")
    assert result["status"] == "failed"
    assert result["failedStage"] == "applied_ref"
    assert not (run / "applied_ref.json").exists()


def test_activate_without_cross_owner_staging_contract_gate_blocks_before_cas(
    tmp_path: Path,
) -> None:
    _release_path, admission = _release(tmp_path)
    _prepare_apply(tmp_path, admission)
    observed: list[str] = []
    deps = _activate_dependencies(tmp_path, admission, _active(found=False))
    deps.require_owner_local_staging_admission = None
    deps.query_content_active_release = lambda **_kwargs: observed.append("query")

    with pytest.raises(SystemExit, match="owner release adapter missing"):
        _ship_operations.activate_release(
            argparse.Namespace(
                env="alpha",
                import_run_id="apply-1",
                run_id="activate-owner-staging-missing",
                confirm_prod_apply=False,
                release_admission=admission,
            ),
            dependencies=deps,
        )

    assert observed == []
    run = (
        tmp_path
        / "env/alpha/runs/data-release/release-a/activate-owner-staging-missing"
    )
    result = read_json(run / "result.json")
    assert result["status"] == "failed"
    assert result["failedStage"] == "owner_local_staging_admission"


def test_activate_readback_failure_is_ambiguous_without_applied_ref(
    tmp_path: Path,
) -> None:
    _release_path, admission = _release(tmp_path)
    _prepare_apply(tmp_path, admission)
    deps = _activate_dependencies(tmp_path, admission, _active(found=False))
    deps.readback_homepage_at_content_fence = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("homepage readback failed after CAS")
    )

    with pytest.raises(RuntimeError, match="after CAS"):
        _ship_operations.activate_release(
            argparse.Namespace(
                env="alpha", import_run_id="apply-1", run_id="activate-readback-failed",
                confirm_prod_apply=False, release_admission=admission,
            ),
            dependencies=deps,
        )

    run = tmp_path / "env/alpha/runs/data-release/release-a/activate-readback-failed"
    result = read_json(run / "result.json")
    assert result["status"] == "failed"
    assert result["failedStage"] == "owner_fenced_readback"
    assert not (run / "applied_ref.json").exists()
