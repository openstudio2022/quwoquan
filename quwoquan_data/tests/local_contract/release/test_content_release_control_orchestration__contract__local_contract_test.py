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
        "releaseClass": "research",
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
            releaseClass="research",
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
            "releaseClass": "research",
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
            "releaseClass": "research",
            "productLifecycleState": "research",
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
        query_content_active_release=query_active,
        activate_content_release=activate,
        write_verification_result=write_environment_result,
        write_applied_ref=lambda **kwargs: write_json(
            kwargs["run"] / "applied_ref.json", {"releaseId": kwargs["release_id"]}
        ),
        require_owner_local_staging_admission=lambda **_kwargs: None,
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
    write_environment_result(
        run / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": "alpha",
            "releaseId": "release-a",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "containsUnverifiedAssets": True,
            "manifestDigest": admission.manifest_digest,
            **admission.result_envelope(),
            "runId": "apply-1",
            "status": "prepared",
            "contentImportReportRef": "env/alpha/runs/data-release/release-a/apply-1/import.json",
            "contentCandidateReceiptRef": candidate.relative_to(root).as_posix(),
            "contentCandidateReceiptDigest": importers.file_byte_digest(candidate),
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

    with pytest.raises(SystemExit, match="cross-owner live release"):
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
