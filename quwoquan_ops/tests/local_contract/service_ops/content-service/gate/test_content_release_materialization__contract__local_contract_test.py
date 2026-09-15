# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#req-002
"""Content release importers consume an exact target-owned Docker-visible copy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from quwoquan_ops.cli.lib.content_release_materialization import (
    ContentReleaseMaterializationError,
    materialize_content_release,
)
from content.release.canonical.producer_release_handoff import _artifact_inventory
from content.release.environment.release_runtime import ReleaseAdmission


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _admission(root: Path) -> ReleaseAdmission:
    release = root / "external" / "data" / "releases" / "release-a"
    payload = release / "payload"
    payload.mkdir(parents=True)
    (payload / "release.json").write_bytes(b'{"releaseId":"release-a"}\n')
    (payload / "desired_state.json").write_bytes(
        b'{"desiredRefs":{"entities":[],"posts":[]},"releaseId":"release-a"}\n'
    )
    manifest_digest = _digest((payload / "desired_state.json").read_bytes())
    handoff = {
        "schema": "quwoquan_data.producer_release_handoff",
        "releaseId": "release-a",
        "handoffId": "release-a",
        "release": {
            "ref": "data/releases/release-a",
            "payloadDigest": manifest_digest,
            "headerRef": "data/releases/release-a/payload/release.json",
        },
        "artifact": _artifact_inventory(release),
    }
    raw = (json.dumps(handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (release / "producer_release_handoff.json").write_bytes(raw)
    return ReleaseAdmission(
        release=release,
        contract={"releaseId": "release-a", "desiredRefs": {"entities": [], "posts": []}},
        release_id="release-a",
        manifest_digest=manifest_digest,
        admission_kind="producer_handoff",
        handoff_ref=f"data/releases/release-a/producer_release_handoff.json={_digest(raw)}",
        handoff_artifact_ref="data/releases/release-a/producer_release_handoff.json",
        handoff_artifact_digest=_digest(raw),
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_external_release_materializes_create_or_same_without_source_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    admission = _admission(tmp_path)
    before = _snapshot(admission.release)
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(tmp_path / "deploy"))

    first = materialize_content_release(admission, target_name="gamma-local")
    second = materialize_content_release(admission, target_name="gamma-local")

    assert first == second
    assert first.root.is_relative_to(tmp_path / "deploy" / "gamma-local")
    assert first.root != admission.release
    assert _snapshot(first.root) == before
    assert _snapshot(admission.release) == before
    assert first.digest == _artifact_inventory(admission.release)["treeDigest"]


def test_existing_managed_tamper_and_extra_file_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    admission = _admission(tmp_path)
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(tmp_path / "deploy"))
    materialized = materialize_content_release(admission, target_name="gamma-local")
    (materialized.root / "payload/release.json").write_bytes(b"tampered")
    with pytest.raises(ContentReleaseMaterializationError, match="TARGET_CONFLICT"):
        materialize_content_release(admission, target_name="gamma-local")

    # A distinct target proves undeclared extras are rejected independently.
    other = materialize_content_release(admission, target_name="beta-local")
    (other.root / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ContentReleaseMaterializationError, match="TARGET_CONFLICT"):
        materialize_content_release(admission, target_name="beta-local")


def test_symlinked_managed_parent_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    admission = _admission(tmp_path)
    deploy = tmp_path / "deploy"
    external = tmp_path / "escaped"
    external.mkdir()
    target = deploy / "gamma-local"
    target.mkdir(parents=True)
    (target / "content-release").symlink_to(external, target_is_directory=True)
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy))

    with pytest.raises(ContentReleaseMaterializationError, match="UNSAFE_PARENT"):
        materialize_content_release(admission, target_name="gamma-local")


def test_apply_routes_all_four_importers_to_managed_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from quwoquan_ops.cli.lib.content_release_environment import _ship_operations
    from content.release.environment.run_evidence import create_run, write_environment_result

    admission = _admission(tmp_path)
    managed = tmp_path / "deploy/gamma-local/content-release/releases/release-a/sha256-managed"
    managed.mkdir(parents=True)
    run_root = tmp_path / "output"
    seen: dict[str, Path] = {}

    def importer(owner: str, filename: str):
        def invoke(**kwargs: object):
            seen[owner] = Path(kwargs["release"])
            return Path(kwargs["run"]) / filename
        return invoke

    dependencies = SimpleNamespace(
        output_root=run_root,
        admit_release=lambda _args: admission,
        release_requires_full_sync=lambda _release: False,
        assert_environment_release_policy=lambda **_kwargs: None,
        resolve_environment_release_target=lambda _env: SimpleNamespace(
            environment="gamma", target_name="gamma-local", media_sync_root=None,
            mongo_uri="mongodb://example.invalid", user_postgres_dsn="postgres://example.invalid/db",
            media_delivery_base_url="https://media.example.invalid", api_base_url="https://api.example.invalid",
        ),
        assert_target_action_allowed=lambda **_kwargs: None,
        create_run=lambda env, release_id, run_id, *, kind: create_run(
            output_root=run_root, environment=env, release_id=release_id,
            run_id=run_id, kind=kind, valid_environments=frozenset({"gamma"}),
        ),
        materialize_content_release=lambda *_args, **_kwargs: SimpleNamespace(
            root=managed, ref="content-release/releases/release-a/sha256-" + "a" * 64,
            digest="sha256:" + "a" * 64,
        ),
        require_environment_readiness=lambda **_kwargs: None,
        sync_media=lambda **_kwargs: None,
        run_tag_importer=importer("tag", "tag-import.json"),
        run_creator_importer=importer("creator", "creator-import.json"),
        run_homepage_importer=lambda **kwargs: seen.update(homepage=Path(kwargs["release"])) or {},
        run_content_importer=importer("content", "import.json"),
        write_environment_coverage_receipt=lambda **kwargs: Path(kwargs["run_root"]) / "coverage-receipt.json",
        write_homepage_verification_case_manifest=lambda **kwargs: Path(kwargs["run_root"]) / "cases.json",
        write_verification_result=write_environment_result,
        now_compact=lambda: "20260915T000000Z",
    )
    monkeypatch.setattr(_ship_operations, "scan_release_contract", lambda *_a, **_k: {"status": "passed"})
    args = SimpleNamespace(
        env="gamma", run_id="managed-four", import_to_db=True, full_sync=False,
        dry_run=True, confirm_prod_apply=False, release_admission=admission,
    )

    _ship_operations.apply_release(args, dependencies=dependencies)

    assert seen == {owner: managed for owner in ("tag", "creator", "homepage", "content")}
