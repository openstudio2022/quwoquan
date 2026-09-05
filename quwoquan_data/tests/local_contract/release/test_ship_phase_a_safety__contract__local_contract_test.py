"""Phase A Data environment safety contracts for single-environment ship runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment import _ship_operations, ship_dispatch  # noqa: E402
from content.release.environment.release_runtime import ReleaseAdmission  # noqa: E402
from content.release.environment.release_runtime import sync_media  # noqa: E402
from content.release.environment.run_evidence import (  # noqa: E402
    create_once_canonical_json,
    create_run,
    write_release_evidence,
)
from content.release.model import DeploymentEnvironment  # noqa: E402
from core.io import read_json, write_json  # noqa: E402
from core.release_layout import payload_digest  # noqa: E402

_VALID_ENVS = frozenset({"alpha", "beta", "gamma", "prod"})
_DIGEST_A = "sha256:" + "a" * 64


def _admission(release_id: str = "release-a") -> ReleaseAdmission:
    return ReleaseAdmission(
        release=Path(f"/admitted/{release_id}"),
        contract={
            "releaseId": release_id,
            "desiredRefs": {"entities": [], "posts": []},
        },
        release_id=release_id,
        manifest_digest=_DIGEST_A,
        admission_kind="producer_handoff",
        handoff_ref=f"handoff-ref-v1:sha256:{'1' * 64}:sha256:{'2' * 64}",
        handoff_artifact_ref=f".qwq_output/data/releases/{release_id}/producer_release_handoff.json",
        handoff_artifact_digest=_DIGEST_A,
    )


def _release(tmp_path: Path, release_id: str = "release-a") -> tuple[Path, dict]:
    release = tmp_path / "data" / "releases" / release_id
    contract = {"releaseId": release_id, "desiredRefs": {"entities": [], "posts": []}}
    write_json(
        release / "payload/release.json",
        {
            "releaseId": release_id,
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "containsUnverifiedAssets": False,
        },
    )
    write_json(release / "payload/desired_state.json", contract)
    return release, contract


def _dependencies(
    tmp_path: Path,
    release: Path,
    contract: dict,
    *,
    tag_importer: object | None = None,
) -> SimpleNamespace:
    target = SimpleNamespace(
        environment=DeploymentEnvironment.GAMMA,
        media_sync_root=None,
        mongo_uri="mongodb://example.invalid",
        user_postgres_dsn="postgres://example.invalid/quwoquan",
        media_delivery_base_url="https://media.example.invalid",
        api_base_url="https://api.example.invalid",
    )
    return SimpleNamespace(
        output_root=tmp_path,
        admit_release=lambda _args: ReleaseAdmission(
            release=release,
            contract=contract,
            release_id=release.name,
            manifest_digest=payload_digest(release),
            admission_kind="producer_handoff",
            handoff_ref=f"handoff-ref-v1:sha256:{'1' * 64}:sha256:{'2' * 64}",
            handoff_artifact_ref=f".qwq_output/data/releases/{release.name}/producer_release_handoff.json",
            handoff_artifact_digest="sha256:" + "0" * 64,
        ),
        release_requires_full_sync=lambda _release: False,
        assert_environment_release_policy=lambda **_kwargs: None,
        resolve_environment_release_target=lambda _env: target,
        assert_target_action_allowed=lambda **_kwargs: None,
        create_run=lambda env, release_id, run_id, *, kind: create_run(
            output_root=tmp_path,
            environment=env,
            release_id=release_id,
            run_id=run_id,
            kind=kind,
            valid_environments=_VALID_ENVS,
        ),
        now_compact=lambda: "20260905T120000Z",
        require_environment_readiness=lambda **_kwargs: None,
        sync_media=lambda **_kwargs: None,
        run_tag_importer=tag_importer
        or (lambda **kwargs: kwargs["run"] / "tag-import.json"),
        run_creator_importer=lambda **kwargs: kwargs["run"] / "creator-import.json",
        run_content_importer=lambda **kwargs: kwargs["run"] / "import.json",
        run_homepage_importer=lambda **_kwargs: {},
        write_environment_coverage_receipt=lambda **kwargs: (
            kwargs["run_root"] / "coverage-receipt.json"
        ),
        write_homepage_verification_case_manifest=lambda **kwargs: (
            kwargs["run_root"] / "homepage_verification_cases.json"
        ),
        write_applied_ref=lambda **_kwargs: None,
        require_owner_local_staging_admission=lambda **_kwargs: None,
        write_release_evidence=write_release_evidence,
        write_verification_result=lambda path, result: write_release_evidence(
            path,
            result,
            "environment_release_result",
        ),
    )


@pytest.mark.parametrize(
    "environment",
    ["alpha,beta", "gamma prod", "beta\tprod", " prod", "staging"],
)
def test_dispatch_rejects_multi_or_composite_env_before_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    lock_calls: list[object] = []

    def _unexpected_lock(**kwargs: object) -> object:
        lock_calls.append(kwargs)
        raise AssertionError("lock must not be acquired")

    monkeypatch.setattr(ship_dispatch, "release_operation_guard", _unexpected_lock)
    args = argparse.Namespace(
        ship_command="apply",
        env=environment,
    )

    with pytest.raises(SystemExit, match="只能是一个有效环境"):
        ship_dispatch.dispatch_ship(
            args,
            release_root=tmp_path / "data/releases",
            apply=lambda _args: None,
            rollback=lambda _args: None,
            verify=lambda _args: None,
        )

    assert lock_calls == []


def test_candidate_media_sync_preserves_previous_public_slice(tmp_path: Path) -> None:
    release, _ = _release(tmp_path)
    candidate = b"candidate-body"
    candidate_digest = hashlib.sha256(candidate).hexdigest()
    candidate_key = "media/image/s/asset/candidate/v1/source.webp"
    candidate_source = release / "payload" / candidate_key
    candidate_source.parent.mkdir(parents=True)
    candidate_source.write_bytes(candidate)
    write_json(
        release / "payload/media_manifest.json",
        {
            "schema": "quwoquan_data.release_media_manifest",
            "releaseId": release.name,
            "assets": [
                {
                    "assetId": "candidate",
                    "publicSliceKey": candidate_key,
                    "sha256": f"sha256:{candidate_digest}",
                    "bytes": len(candidate),
                }
            ],
        },
    )
    destination = tmp_path / "environment-media"
    previous = destination / "media/image/s/asset/previous/v1/source.webp"
    previous.parent.mkdir(parents=True)
    previous.write_bytes(b"previous-public-body")
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-media"

    sync_media(release=release, destination=str(destination), run=run)

    assert previous.read_bytes() == b"previous-public-body"
    assert (destination / candidate_key).read_bytes() == candidate
    assert read_json(run / "media-sync.json")["pruned"] == 0


def test_apply_exception_records_create_once_failed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, contract = _release(tmp_path)
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )

    def _fail_tag_import(**_kwargs: object) -> Path:
        raise RuntimeError(
            "tag importer failed password=hunter2\ntraceback must not persist"
        )

    dependencies = _dependencies(
        tmp_path,
        release,
        contract,
        tag_importer=_fail_tag_import,
    )
    args = argparse.Namespace(
        env="gamma",
        run_id="apply-failed",
        import_to_db=True,
        full_sync=False,
        dry_run=True,
        confirm_prod_apply=False,
        release_admission=__import__("dataclasses").replace(
            _admission(),
            release=release,
            contract=contract,
            manifest_digest=payload_digest(release),
        ),
    )

    with pytest.raises(RuntimeError, match="tag importer failed"):
        _ship_operations.apply_release(args, dependencies=dependencies)

    result_path = (
        tmp_path / "env/gamma/runs/data-release/release-a/apply-failed/result.json"
    )
    result = read_json(result_path)
    assert result["status"] == "failed"
    assert result["handoffArtifactRef"].endswith("/producer_release_handoff.json")
    assert result["handoffArtifactDigest"].startswith("sha256:")
    assert result["failedStage"] == "tag_import"
    assert "hunter2" not in result["error"]
    assert "[REDACTED]" in result["error"]
    assert "Traceback (most recent call last)" not in result["error"]
    assert 0 <= result["durationMs"]
    assert datetime.fromisoformat(result["startedAt"])
    assert datetime.fromisoformat(result["endedAt"])


def test_apply_preserves_primary_error_when_failed_receipt_write_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, contract = _release(tmp_path)
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )

    def _fail_tag_import(**_kwargs: object) -> Path:
        raise RuntimeError("primary import failure")

    dependencies = _dependencies(
        tmp_path,
        release,
        contract,
        tag_importer=_fail_tag_import,
    )

    def _fail_result_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("result disk failure")

    dependencies.write_verification_result = _fail_result_write
    args = argparse.Namespace(
        env="gamma",
        run_id="apply-double-failure",
        import_to_db=True,
        full_sync=False,
        dry_run=True,
        confirm_prod_apply=False,
        release_admission=__import__("dataclasses").replace(
            _admission(),
            release=release,
            contract=contract,
            manifest_digest=payload_digest(release),
        ),
    )

    with pytest.raises(RuntimeError) as caught:
        _ship_operations.apply_release(args, dependencies=dependencies)

    assert caught.value.args == ("primary import failure",)
    assert "primary import failure" in str(caught.value)
    assert any(
        "failed result evidence error: result disk failure" in note
        for note in getattr(caught.value, "__notes__", ())
    )
    assert caught.tb is not None
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-double-failure"
    assert not (run / "result.json").exists()


def test_create_once_link_oserror_fails_closed_without_final_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "result.json"
    real_link = os.link

    def _fail_link(_source: object, _target: object) -> None:
        raise OSError("hardlink unavailable")

    monkeypatch.setattr(os, "link", _fail_link)
    with pytest.raises(OSError, match="hardlink unavailable"):
        create_once_canonical_json(target, {"status": "prepared"})
    assert not target.exists()
    assert not tuple(tmp_path.glob(".result.json.*.tmp"))
    monkeypatch.setattr(os, "link", real_link)


def test_create_once_accepts_canonical_macos_temp_alias() -> None:
    alias = Path("/var")
    if not alias.is_symlink() or alias.resolve() != Path("/private/var"):
        pytest.skip("canonical macOS /var alias is not present")
    with tempfile.TemporaryDirectory(dir="/var/tmp") as directory:
        target = Path(directory) / "result.json"
        create_once_canonical_json(target, {"status": "prepared"})
        assert target.is_file()


def test_apply_does_not_catch_keyboard_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, contract = _release(tmp_path)
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )

    def _interrupt(**_kwargs: object) -> Path:
        raise KeyboardInterrupt

    dependencies = _dependencies(
        tmp_path,
        release,
        contract,
        tag_importer=_interrupt,
    )
    args = argparse.Namespace(
        env="gamma",
        run_id="apply-interrupted",
        import_to_db=True,
        full_sync=False,
        dry_run=True,
        confirm_prod_apply=False,
        release_admission=__import__("dataclasses").replace(
            _admission(),
            release=release,
            contract=contract,
            manifest_digest=payload_digest(release),
        ),
    )

    with pytest.raises(KeyboardInterrupt):
        _ship_operations.apply_release(args, dependencies=dependencies)
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-interrupted"
    assert not (run / "result.json").exists()


@pytest.mark.parametrize(
    "unsafe",
    ["", ".", "..", "/absolute", "a/b", "a\\b", "a\x00b", "a\nb", " a", "a "],
)
def test_create_run_rejects_unsafe_release_and_run_segments(
    tmp_path: Path,
    unsafe: str,
) -> None:
    for field in ("release_id", "run_id"):
        kwargs = {
            "output_root": tmp_path,
            "environment": "gamma",
            "release_id": "合法发布-一",
            "run_id": "合法运行-一",
            "kind": "apply",
            "valid_environments": _VALID_ENVS,
        }
        kwargs[field] = unsafe
        with pytest.raises(SystemExit, match="单一安全路径段"):
            create_run(**kwargs)


def test_create_run_accepts_chinese_id_at_255_byte_limit(tmp_path: Path) -> None:
    long_chinese_id = "界" * 85
    run = create_run(
        output_root=tmp_path,
        environment="gamma",
        release_id=long_chinese_id,
        run_id="中文运行",
        kind="apply",
        valid_environments=_VALID_ENVS,
    )
    assert run.name == "中文运行"
    assert run.parent.name == long_chinese_id


def test_create_run_rejects_apply_predeposit_and_symlink_ancestor(
    tmp_path: Path,
) -> None:
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-preset"
    run.mkdir(parents=True)
    (run / "result.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="预存证据"):
        create_run(
            output_root=tmp_path,
            environment="gamma",
            release_id="release-a",
            run_id="apply-preset",
            kind="apply",
            valid_environments=_VALID_ENVS,
        )

    outside = tmp_path / "outside"
    outside.mkdir()
    symlink = tmp_path / "symlink-root"
    symlink.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SystemExit, match="symlink"):
        create_run(
            output_root=symlink,
            environment="gamma",
            release_id="release-a",
            run_id="apply-symlink",
            kind="apply",
            valid_environments=_VALID_ENVS,
        )


def test_create_run_rejects_symlink_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside-run"
    outside.mkdir()
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-symlink-target"
    run.parent.mkdir(parents=True)
    run.symlink_to(outside, target_is_directory=True)

    with pytest.raises(SystemExit, match="symlink"):
        create_run(
            output_root=tmp_path,
            environment="gamma",
            release_id="release-a",
            run_id="apply-symlink-target",
            kind="apply",
            valid_environments=_VALID_ENVS,
        )


def test_create_run_rejects_identifier_over_255_bytes(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="255 bytes"):
        create_run(
            output_root=tmp_path,
            environment="gamma",
            release_id="界" * 86,
            run_id="run-a",
            kind="apply",
            valid_environments=_VALID_ENVS,
        )


def test_environment_result_checksum_covers_timing_and_excludes_checksum(
    tmp_path: Path,
) -> None:
    run = create_run(
        output_root=tmp_path,
        environment="gamma",
        release_id="release-a",
        run_id="apply-checksum",
        kind="apply",
        valid_environments=_VALID_ENVS,
    )
    write_release_evidence(
        run / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": "gamma",
            "releaseId": "release-a",
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "containsUnverifiedAssets": False,
            "manifestDigest": _DIGEST_A,
            **_admission().result_envelope(),
            "runId": "apply-checksum",
            "status": "prepared",
        },
        "environment_release_result",
    )
    result = read_json(run / "result.json")
    checksum = result.pop("verificationChecksum")
    canonical = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert checksum == "sha256:" + hashlib.sha256(canonical).hexdigest()
    assert {"startedAt", "endedAt", "durationMs"}.issubset(result)


def test_duplicate_run_and_result_never_overwrite_existing_bytes(
    tmp_path: Path,
) -> None:
    run = create_run(
        output_root=tmp_path,
        environment="gamma",
        release_id="release-a",
        run_id="apply-duplicate",
        kind="apply",
        valid_environments=_VALID_ENVS,
    )
    run_bytes = (run / "run.json").read_bytes()
    with pytest.raises(SystemExit, match="append-only run 已存在"):
        create_run(
            output_root=tmp_path,
            environment="gamma",
            release_id="release-a",
            run_id="apply-duplicate",
            kind="apply",
            valid_environments=_VALID_ENVS,
        )
    assert (run / "run.json").read_bytes() == run_bytes

    base_result = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": "gamma",
        "releaseId": "release-a",
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "containsUnverifiedAssets": False,
        "manifestDigest": _DIGEST_A,
        **_admission().result_envelope(),
        "runId": "apply-duplicate",
        "status": "prepared",
    }
    write_release_evidence(
        run / "result.json",
        base_result,
        "environment_release_result",
    )
    result_bytes = (run / "result.json").read_bytes()
    with pytest.raises(FileExistsError):
        write_release_evidence(
            run / "result.json",
            {**base_result, "status": "failed", "failedStage": "late", "error": "late"},
            "environment_release_result",
        )
    assert (run / "result.json").read_bytes() == result_bytes
    assert read_json(run / "result.json")["status"] == "prepared"


def test_rollback_intent_binds_from_and_to_manifest_digests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, contract = _release(tmp_path)
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )
    dependencies = _dependencies(tmp_path, release, contract)
    args = argparse.Namespace(
        from_release_id="release-current",
        from_manifest_digest=_DIGEST_A,
        env="gamma",
        run_id="rollback-digests",
        import_to_db=False,
        dry_run=True,
        confirm_prod_apply=False,
        release_admission=__import__("dataclasses").replace(
            _admission(),
            release=release,
            contract=contract,
            manifest_digest=payload_digest(release),
        ),
    )

    _ship_operations.rollback_release(args, dependencies=dependencies)

    run = tmp_path / "env/gamma/runs/data-release/release-a/rollback-digests"
    intent = read_json(run / "rollback_ref.json")
    assert intent["authority"] == "asserted_intent"
    assert intent["rollbackFromManifestDigest"] == _DIGEST_A
    assert intent["rollbackToManifestDigest"] == payload_digest(release)
    result = read_json(run / "result.json")
    assert result["status"] == "dry_run"
    assert result["handoffArtifactRef"].endswith("/producer_release_handoff.json")
    assert result["handoffArtifactDigest"].startswith("sha256:")
    assert result["startedAt"] and result["endedAt"]
    assert result["durationMs"] >= 0


def test_apply_import_stages_candidate_and_never_writes_applied_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, contract = _release(tmp_path)
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )
    calls: list[str] = []
    dependencies = _dependencies(tmp_path, release, contract)
    dependencies.require_environment_readiness = lambda **_kwargs: calls.append(
        "readiness"
    )
    dependencies.run_tag_importer = lambda **kwargs: kwargs["run"] / "tag-import.json"
    dependencies.run_creator_importer = lambda **kwargs: (
        kwargs["run"] / "creator-import.json"
    )
    dependencies.run_content_importer = lambda **kwargs: kwargs["run"] / "import.json"
    dependencies.run_homepage_importer = lambda **_kwargs: {}
    candidate_path = (
        tmp_path
        / "env/gamma/runs/data-release/release-a/apply-candidate/content-candidate-receipt.json"
    )

    def _query_candidate(**_kwargs: object) -> SimpleNamespace:
        candidate_path.write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(
            ref=candidate_path.relative_to(tmp_path).as_posix(),
            digest="sha256:" + hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        )

    dependencies.query_content_release_candidate = _query_candidate
    dependencies.write_applied_ref = lambda **_kwargs: calls.append("applied-ref")
    args = argparse.Namespace(
        env="gamma",
        run_id="apply-candidate",
        import_to_db=True,
        full_sync=False,
        dry_run=False,
        confirm_prod_apply=False,
        release_admission=__import__("dataclasses").replace(
            _admission(),
            release=release,
            contract=contract,
            manifest_digest=payload_digest(release),
        ),
    )

    _ship_operations.apply_release(args, dependencies=dependencies)

    assert calls == ["readiness"]
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-candidate"
    assert not (run / "applied_ref.json").exists()
    result = read_json(run / "result.json")
    assert result["status"] == "prepared"
    assert result["contentCandidateReceiptDigest"].startswith("sha256:")


def test_apply_dry_run_passes_content_stage_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, contract = _release(tmp_path)
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )
    observed: dict[str, object] = {}
    dependencies = _dependencies(tmp_path, release, contract)
    dependencies.run_content_importer = lambda **kwargs: (
        observed.update(kwargs) or kwargs["run"] / "import.json"
    )
    args = argparse.Namespace(
        env="gamma",
        run_id="apply-dry-run-stage-only",
        import_to_db=True,
        full_sync=False,
        dry_run=True,
        confirm_prod_apply=False,
        release_admission=__import__("dataclasses").replace(
            _admission(),
            release=release,
            contract=contract,
            manifest_digest=payload_digest(release),
        ),
    )

    _ship_operations.apply_release(args, dependencies=dependencies)

    assert "activation_mode" not in observed
    run = tmp_path / "env/gamma/runs/data-release/release-a/apply-dry-run-stage-only"
    assert read_json(run / "result.json")["status"] == "dry_run"
    assert not (run / "applied_ref.json").exists()


def test_rollback_dry_run_passes_content_stage_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, contract = _release(tmp_path)
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )
    observed: dict[str, object] = {}
    dependencies = _dependencies(tmp_path, release, contract)
    dependencies.run_content_importer = lambda **kwargs: (
        observed.update(kwargs) or kwargs["run"] / "import.json"
    )
    args = argparse.Namespace(
        from_release_id="release-current",
        from_manifest_digest=_DIGEST_A,
        env="gamma",
        run_id="rollback-dry-run-stage-only",
        import_to_db=True,
        dry_run=True,
        confirm_prod_apply=False,
        release_admission=__import__("dataclasses").replace(
            _admission(),
            release=release,
            contract=contract,
            manifest_digest=payload_digest(release),
        ),
    )

    _ship_operations.rollback_release(args, dependencies=dependencies)

    assert "activation_mode" not in observed
    run = tmp_path / "env/gamma/runs/data-release/release-a/rollback-dry-run-stage-only"
    assert read_json(run / "result.json")["status"] == "dry_run"
    assert not (run / "applied_ref.json").exists()


def _rollback_active_document(
    *,
    release_id: str = "release-current",
    manifest_digest: str = _DIGEST_A,
    revision: int = 7,
) -> dict[str, object]:
    return {
        "schema": "quwoquan.content_release_active_receipt",
        "status": "found",
        "environment": "gamma",
        "sourceOwner": "qwq_data",
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "releaseClass": "commercial",
        "projectionVersion": 4,
        "revision": revision,
        "activatedAt": "2026-09-05T00:00:00Z",
        "generatedAt": "2026-09-05T00:00:01Z",
    }


def test_rollback_uses_queried_active_tuple_and_rejects_asserted_intent_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, contract = _release(tmp_path)
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )
    queried = _rollback_active_document()
    observed: dict[str, object] = {}
    dependencies = _dependencies(tmp_path, release, contract)
    dependencies.query_content_release_candidate = lambda **kwargs: SimpleNamespace(
        document={},
        path=kwargs["report_path"],
        ref=kwargs["report_path"].relative_to(tmp_path).as_posix(),
        digest=_DIGEST_A,
    )
    dependencies.query_content_active_release = lambda **kwargs: SimpleNamespace(
        document=queried,
        path=kwargs["report_path"],
        ref=kwargs["report_path"].relative_to(tmp_path).as_posix(),
        digest=_DIGEST_A,
    )
    dependencies.activate_content_release = lambda **kwargs: observed.update(kwargs)
    args = argparse.Namespace(
        from_release_id="release-other",
        from_manifest_digest=_DIGEST_A,
        env="gamma",
        run_id="rollback-intent-drift",
        import_to_db=True,
        dry_run=False,
        confirm_prod_apply=False,
        release_admission=__import__("dataclasses").replace(
            _admission(),
            release=release,
            contract=contract,
            manifest_digest=payload_digest(release),
        ),
    )

    with pytest.raises(SystemExit, match="asserted intent differs"):
        _ship_operations.rollback_release(args, dependencies=dependencies)

    assert observed == {}
    result = read_json(
        tmp_path
        / "env/gamma/runs/data-release/release-a/rollback-intent-drift/result.json"
    )
    assert result["status"] == "failed"
    assert result["failedStage"] == "content_active_pre_query"
    intent = read_json(
        tmp_path
        / "env/gamma/runs/data-release/release-a/rollback-intent-drift/rollback_ref.json"
    )
    assert intent["authority"] == "asserted_intent"


def test_live_apply_without_cross_owner_staging_contract_blocks_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, contract = _release(tmp_path)
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )
    mutations: list[str] = []
    dependencies = _dependencies(tmp_path, release, contract)
    dependencies.require_owner_local_staging_admission = None
    dependencies.require_environment_readiness = lambda **_kwargs: mutations.append(
        "readiness"
    )
    dependencies.run_tag_importer = lambda **_kwargs: mutations.append("tag")

    with pytest.raises(SystemExit, match="cross-owner live release"):
        _ship_operations.apply_release(
            argparse.Namespace(
                env="gamma",
                run_id="apply-owner-staging-missing",
                import_to_db=True,
                full_sync=False,
                dry_run=False,
                confirm_prod_apply=False,
                release_admission=__import__("dataclasses").replace(
                    _admission(),
                    release=release,
                    contract=contract,
                    manifest_digest=payload_digest(release),
                ),
            ),
            dependencies=dependencies,
        )

    assert mutations == []
    run = (
        tmp_path
        / "env/gamma/runs/data-release/release-a/apply-owner-staging-missing"
    )
    result = read_json(run / "result.json")
    assert result["status"] == "failed"
    assert result["failedStage"] == "owner_local_staging_admission"


def test_rollback_passes_queried_revision_bearing_tuple_to_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release, contract = _release(tmp_path)
    target_digest = payload_digest(release)
    monkeypatch.setattr(
        _ship_operations,
        "scan_release_contract",
        lambda *_args, **_kwargs: {"status": "passed"},
    )
    queried = _rollback_active_document(revision=11)
    observed: dict[str, object] = {}
    completion_order: list[str] = []
    query_count = 0
    dependencies = _dependencies(tmp_path, release, contract)

    def _candidate(**kwargs: object) -> SimpleNamespace:
        path = Path(kwargs["report_path"])
        path.write_text("candidate\n", encoding="utf-8")
        return SimpleNamespace(
            document={},
            path=path,
            ref=path.relative_to(tmp_path).as_posix(),
            digest="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def _query_active(**kwargs: object) -> SimpleNamespace:
        nonlocal query_count
        query_count += 1
        path = Path(kwargs["report_path"])
        if query_count == 1:
            document = queried
        else:
            document = {
                **_rollback_active_document(
                    release_id="release-a",
                    manifest_digest=target_digest,
                    revision=12,
                ),
                "projectionVersion": 9,
                "activatedAt": "2026-09-05T00:00:03Z",
            }
        path.write_text("active\n", encoding="utf-8")
        return SimpleNamespace(
            document=document,
            path=path,
            ref=path.relative_to(tmp_path).as_posix(),
            digest="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def _activate(**kwargs: object) -> SimpleNamespace:
        observed.update(kwargs)
        expected = dict(kwargs["expected_active"])
        document = {
            "active": {
                "releaseId": "release-a",
                "manifestDigest": target_digest,
                "releaseClass": "commercial",
                "projectionVersion": 9,
                "revision": 12,
                "activatedAt": "2026-09-05T00:00:03Z",
            }
        }
        path = Path(kwargs["report_path"])
        path.write_text("activation\n", encoding="utf-8")
        return SimpleNamespace(
            document=document,
            path=path,
            ref=path.relative_to(tmp_path).as_posix(),
            digest="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    dependencies.query_content_release_candidate = _candidate
    dependencies.query_content_active_release = _query_active
    dependencies.activate_content_release = _activate
    dependencies.write_applied_ref = lambda **_kwargs: completion_order.append(
        "applied_ref"
    )

    def _write_result(path: Path, result: dict[str, object]) -> None:
        completion_order.append(str(result["status"]))
        write_release_evidence(path, result, "environment_release_result")

    dependencies.write_verification_result = _write_result
    args = argparse.Namespace(
        from_release_id="release-current",
        from_manifest_digest=_DIGEST_A,
        env="gamma",
        run_id="rollback-revision-authority",
        import_to_db=True,
        dry_run=False,
        confirm_prod_apply=False,
        release_admission=__import__("dataclasses").replace(
            _admission(),
            release=release,
            contract=contract,
            manifest_digest=target_digest,
        ),
    )

    _ship_operations.rollback_release(args, dependencies=dependencies)

    assert observed["expected_active"] == queried
    assert completion_order == ["applied_ref", "completed"]
    result = read_json(
        tmp_path
        / "env/gamma/runs/data-release/release-a/rollback-revision-authority/result.json"
    )
    assert result["status"] == "completed"
    assert result["contentPreActiveReceiptDigest"].startswith("sha256:")
