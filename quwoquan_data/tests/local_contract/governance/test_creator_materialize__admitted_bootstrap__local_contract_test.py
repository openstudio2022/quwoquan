"""已准入作者显式物化：原件闭包、空仓与不可覆盖。

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-001
"""
from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

from content.release.canonical.content_pool_record import is_pool_record_admitted, latest_pool_record
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from core import content_library
from core.paths import CONTROL_PLANE_CREATOR_POOL_ROOT
from governance.creators import materialize
from governance.handler import register_parser
from support.media_fixture import tiny_png_bytes

CREATOR = "qwq_creator_travel_blogger_001"


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    pool = tmp_path / "registry"
    source = CONTROL_PLANE_CREATOR_POOL_ROOT / "profiles/system_builtin/travel_blogger.creator.yaml"
    profile = yaml.safe_load(source.read_bytes())
    admission_ref = profile["admission"]["evidenceRef"]
    admission = pool / admission_ref
    admission.parent.mkdir(parents=True)
    admission.write_bytes((CONTROL_PLANE_CREATOR_POOL_ROOT / admission_ref).read_bytes())
    # 仅在隔离测试中以真实摘要的小图片替换头像；不伪造生产 CAS 摘要。
    body = tiny_png_bytes()
    digest = hashlib.sha256(body).hexdigest()
    asset = profile["avatarAsset"]
    rights = json.loads((CONTROL_PLANE_CREATOR_POOL_ROOT / asset["evidenceRef"]).read_bytes())
    asset.update(sha256=f"sha256:{digest}", bytes=len(body), mimeType="image/png",
                 objectKey=f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.png")
    rights["manifestAsset"]["sha256"] = asset["sha256"]
    rights["commercialRights"]["asset"].update(sha256=asset["sha256"], bytes=len(body), mimeType="image/png")
    _json(pool / asset["evidenceRef"], rights)
    profile_path = pool / "profiles/system_builtin/travel_blogger.creator.yaml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(content_library, "LIBRARY_CAS_ROOT_BY_KIND", {"media": tmp_path / "library/_media_cas"})
    content_library.admit_library_bytes(body, kind="media")
    publish = tmp_path / "publish"
    (publish / ".git").mkdir(parents=True)
    _json(publish / "repository.json", {
        "schema": "quwoquan_data.publish_repository.v2", "repositoryId": "test-content",
        "layoutVersion": 2, "producerContractDigest": "sha256:" + "a" * 64,
    })
    monkeypatch.setattr(materialize, "CONTROL_PLANE_CREATOR_POOL_ROOT", pool)
    monkeypatch.setattr(materialize, "PUBLISH_ROOT", publish)
    return pool, profile_path, profile, publish, body


def test_empty_repository_and_same_replay_preserve_original_evidence(inputs, monkeypatch):
    pool, _, profile, publish, body = inputs
    before = _tree(pool)
    locked = []

    @contextmanager
    def observed_lock(root):
        with canonical_publish_lock(root):
            locked.append(root)
            yield

    monkeypatch.setattr(materialize, "canonical_publish_lock", observed_lock)
    result = materialize.materialize_creator(creator_ref=CREATOR)
    target = publish / "creators" / CREATOR
    projected = json.loads((target / "profile.json").read_bytes())
    assert result["status"] == "created"
    assert result["repositoryId"] == "test-content"
    assert result["objectRef"] == f"creators/{CREATOR}"
    assert projected["admission"] == profile["admission"]
    assert projected["authorId"] == profile["authorId"]
    assert (target / profile["admission"]["evidenceRef"]).read_bytes() == before[profile["admission"]["evidenceRef"]]
    assert (target / "sources/avatar/evidence.json").read_bytes() == before[profile["avatarAsset"]["evidenceRef"]]
    assert (target / projected["assets"][0]["path"]).read_bytes() == body
    assert is_pool_record_admitted(latest_pool_record(target, "author"))
    assert not (target / "records").exists()
    published = _tree(target)
    inode = target.stat().st_ino
    repeated = materialize.materialize_creator(creator_ref=CREATOR)
    assert repeated["status"] == "same"
    assert repeated["treeDigest"] == result["treeDigest"]
    assert _tree(target) == published and target.stat().st_ino == inode
    assert _tree(pool) == before
    assert locked == [publish, publish]
    assert sorted(p.name for p in (publish / "creators").iterdir()) == [CREATOR]


@pytest.mark.parametrize("mutation", ["schema", "digest", "authorIds", "review_failed", "inactive", "profile_schema", "missing"])
def test_invalid_original_admission_never_publishes(inputs, mutation):
    pool, profile_path, profile, publish, _ = inputs
    evidence = pool / profile["admission"]["evidenceRef"]
    original = json.loads(evidence.read_bytes())
    if mutation == "schema":
        original["schema"] = "invented"
    elif mutation == "authorIds":
        original["authorIds"] = ["someone_else"]
    elif mutation == "review_failed":
        original["checks"]["profile"] = "failed"
    elif mutation == "inactive":
        profile["status"] = "draft"
    elif mutation == "profile_schema":
        profile["new_admission_authority"] = True
    elif mutation == "missing":
        evidence.unlink()
    if mutation != "missing":
        _json(evidence, original)
        if mutation != "digest":
            profile["admission"]["evidenceDigest"] = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
    profile_path.write_text(yaml.safe_dump(profile), encoding="utf-8")
    with pytest.raises(materialize.CreatorMaterializationError):
        materialize.materialize_creator(creator_ref=CREATOR)
    assert not (publish / "creators" / CREATOR).exists()


@pytest.mark.parametrize("creator_ref", ["unknown", "../escape", f" {CREATOR}", f"{CREATOR},other"])
def test_exact_creator_ref_required(inputs, creator_ref):
    with pytest.raises(materialize.CreatorMaterializationError):
        materialize.materialize_creator(creator_ref=creator_ref)


def test_duplicate_registry_identity_is_rejected(inputs):
    pool, profile_path, _, publish, _ = inputs
    (profile_path.parent / "duplicate.creator.yaml").write_bytes(profile_path.read_bytes())
    with pytest.raises(materialize.CreatorMaterializationError, match="exactly once"):
        materialize.materialize_creator(creator_ref=CREATOR)
    assert not (publish / "creators" / CREATOR).exists()


@pytest.mark.parametrize("change", ["profile", "media", "extra_file", "empty_target"])
def test_different_target_is_never_overwritten(inputs, change):
    _, _, _, publish, _ = inputs
    target = publish / "creators" / CREATOR
    if change == "empty_target":
        target.mkdir(parents=True)
    else:
        materialize.materialize_creator(creator_ref=CREATOR)
        file = {"profile": "profile.json", "media": "media/avatar.png", "extra_file": "extra.json"}[change]
        if (target / file).exists():
            (target / file).chmod(0o644)
        (target / file).write_bytes(b"different")
    before = _tree(target)
    with pytest.raises(materialize.CreatorMaterializationError, match="CONFLICT"):
        materialize.materialize_creator(creator_ref=CREATOR)
    assert _tree(target) == before


@pytest.mark.parametrize("problem", ["evidence_symlink", "parent_symlink", "target_symlink", "repository", "avatar_missing", "avatar_corrupt"])
def test_unsafe_or_missing_dependencies_fail_closed(inputs, tmp_path, problem):
    pool, _, profile, publish, body = inputs
    evidence = pool / profile["admission"]["evidenceRef"]
    if problem == "evidence_symlink":
        original = tmp_path / "original.json"
        original.write_bytes(evidence.read_bytes())
        evidence.unlink()
        evidence.symlink_to(original)
    elif problem in {"parent_symlink", "target_symlink"}:
        outside = tmp_path / "outside"
        outside.mkdir()
        target = publish / "creators"
        if problem == "target_symlink":
            target.mkdir()
            target = target / CREATOR
        target.symlink_to(outside, target_is_directory=True)
    elif problem == "repository":
        (publish / "repository.json").unlink()
    else:
        entry = content_library.library_cas_path("media", profile["avatarAsset"]["sha256"])
        entry.chmod(0o644)
        if problem == "avatar_missing":
            entry.unlink()
        else:
            entry.write_bytes(b"x" * len(body))
    with pytest.raises(materialize.CreatorMaterializationError):
        materialize.materialize_creator(creator_ref=CREATOR)
    assert not (publish / "creators" / CREATOR / "profile.json").exists()


def test_projection_failure_and_registry_race_leave_no_partial_object(inputs, monkeypatch):
    _, profile_path, _, publish, _ = inputs
    real = materialize.creator_projection.project_creator_object

    def racing_projection(*args, **kwargs):
        result = real(*args, **kwargs)
        profile_path.write_bytes(profile_path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(materialize.creator_projection, "project_creator_object", racing_projection)
    with pytest.raises(materialize.CreatorMaterializationError, match="DRIFT"):
        materialize.materialize_creator(creator_ref=CREATOR)
    assert not (publish / "creators" / CREATOR).exists()
    assert not list((publish / ".git/qwq-publish").glob("creator-materialize-*"))


def test_cli_routes_only_explicit_materialize_and_blocks_failure(inputs, monkeypatch, capsys):
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers())
    with pytest.raises(SystemExit):
        parser.parse_args(["governance", "creators", "materialize"])
    args = parser.parse_args(["governance", "creators", "materialize", "--creator-ref", CREATOR])
    args.handler(args)
    assert json.loads(capsys.readouterr().out)["status"] == "created"

    def blocked(**kwargs):
        raise materialize.CreatorMaterializationError("AUTHOR_AUTHORITY_DRIFT")

    monkeypatch.setattr(materialize, "materialize_creator", blocked)
    with pytest.raises(SystemExit, match="GATE_BLOCK.*AUTHOR_AUTHORITY_DRIFT"):
        args.handler(args)
