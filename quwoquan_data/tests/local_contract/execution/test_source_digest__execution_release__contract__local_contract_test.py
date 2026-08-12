"""Execution and release evidence must bind only repository-owned inputs."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core import source_digest as source_digest_module  # noqa: E402
from core.source_digest import (  # noqa: E402
    ExecutionBundleIdentity,
    SourceDigest,
    SourceDigestError,
    SourceDefinitionSnapshot,
    _iter_files,
    current_source_digest,
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)
from content.execution import workspace  # noqa: E402
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402


def test_source_digest__execution_release__contract__local_contract() -> None:
    document = current_source_digest().to_document()

    assert SourceDigest.from_document(document).to_document() == document
    assert ".qwq_output" not in document["inputs"]
    assert "quwoquan_data/control_plane" in document["inputs"]
    assert "quwoquan_data/verticals/travel" in document["inputs"]
    assert "quwoquan_data/requirements-cursor.txt" in document["inputs"]
    assert (
        "quwoquan_service/services/recommendation-service/contracts/"
        "recommendation/recommendation_feature_profile_view/projections/"
        "intersection_reason.yaml"
        in document["inputs"]
    )
    assert (
        "quwoquan_service/services/content-service/contracts/content/post/"
        "ui_config.yaml"
        in document["inputs"]
    )
    assert not any(input_path.startswith("quwoquan_ops/") for input_path in document["inputs"])


def test_source_digest__rejects_runtime_output_as_input__contract__local_contract() -> None:
    document = current_source_digest().to_document()
    document["inputs"] = [".qwq_output"]

    try:
        SourceDigest.from_document(document)
    except SourceDigestError as exc:
        assert "fixed repository inputs" in str(exc)
    else:
        raise AssertionError("runtime output must never become a source digest input")


def test_source_identity_splits_definitions_from_execution_bundle() -> None:
    snapshot = current_source_definition_snapshot().to_document()
    bundle = current_execution_bundle_identity().to_document()

    assert SourceDefinitionSnapshot.from_document(snapshot).to_document() == snapshot
    assert ExecutionBundleIdentity.from_document(bundle).to_document() == bundle
    assert "quwoquan_data/scripts" not in snapshot["inputs"]
    assert "quwoquan_data/scripts" in bundle["inputs"]
    assert "quwoquan_data/reference" in snapshot["inputs"]


def test_frozen_identity_parsers_never_read_a_live_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = current_source_definition_snapshot().to_document()
    bundle = current_execution_bundle_identity().to_document()

    monkeypatch.setattr(
        source_digest_module,
        "_digest_roots",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("live source tree read")
        ),
    )

    assert SourceDefinitionSnapshot.from_document(snapshot).digest == snapshot["digest"]
    assert ExecutionBundleIdentity.from_document(bundle).digest == bundle["digest"]


def test_source_digest__ignores_empty_directory_markers__contract__local_contract(
    tmp_path: Path,
) -> None:
    (tmp_path / ".gitkeep").touch()
    source = tmp_path / "policy.yaml"
    source.write_text("enabled: true\n", encoding="utf-8")

    assert _iter_files(tmp_path) == (source,)


def test_source_digest__frozen_execution_manifest_does_not_read_live_tree() -> None:
    execution_id = "20260727--travel-homepage-coverage--test-region-a--pilot-001"
    ExecutionFixtureBuilder(execution_id).build()
    frozen = workspace.load_execution_manifest(execution_id)
    assert frozen["executionId"] == execution_id


def test_existing_v2_manifest_resume_never_reads_live_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id = "20260727--travel-homepage-coverage--test-region-b--pilot-001"
    frozen = ExecutionFixtureBuilder(execution_id).build()

    monkeypatch.setattr(
        workspace,
        "current_execution_bundle_identity",
        lambda: (_ for _ in ()).throw(AssertionError("live execution bundle read")),
    )
    monkeypatch.setattr(
        workspace,
        "current_source_definition_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("live source definition read")),
    )

    resumed = ExecutionFixtureBuilder(execution_id).build()

    assert resumed == frozen


def test_source_digest__persistent_cache_rehashes_only_changed_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    seeded: list[Path] = []
    for relative in source_digest_module._INPUT_ROOTS:
        root = repo_root / relative
        if root.suffix:
            root.parent.mkdir(parents=True, exist_ok=True)
            root.write_text(f"seed:{relative}\n", encoding="utf-8")
            seeded.append(root)
        else:
            root.mkdir(parents=True, exist_ok=True)
            source = root / "source.txt"
            source.write_text(f"seed:{relative}\n", encoding="utf-8")
            seeded.append(source)

    cache_path = tmp_path / "cache" / "source-digest.json"
    first = SourceDigest.build(repo_root=repo_root, cache_path=cache_path)
    original_hash = source_digest_module._file_sha256
    hashed: list[Path] = []

    def _recording_hash(path: Path) -> str:
        hashed.append(path)
        return original_hash(path)

    monkeypatch.setattr(source_digest_module, "_file_sha256", _recording_hash)
    assert SourceDigest.build(repo_root=repo_root, cache_path=cache_path) == first
    assert hashed == []

    changed = seeded[0]
    changed.write_text(changed.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    second = SourceDigest.build(repo_root=repo_root, cache_path=cache_path)

    assert second != first
    assert hashed == [changed]


def test_source_digest__read_only_capsule_does_not_write_runtime_cache(
    tmp_path: Path,
) -> None:
    capsule = tmp_path / "source-capsule"
    for relative in source_digest_module._INPUT_ROOTS:
        root = capsule / relative
        if root.suffix:
            root.parent.mkdir(parents=True, exist_ok=True)
            root.write_text(f"seed:{relative}\n", encoding="utf-8")
        else:
            root.mkdir(parents=True, exist_ok=True)
            (root / "source.txt").write_text(
                f"seed:{relative}\n",
                encoding="utf-8",
            )

    expected = SourceDigest.build(
        repo_root=capsule,
        cache_path=tmp_path / "external-cache/source-digest.json",
    )
    (capsule / ".qwq_campaign_capsule.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    runtime_cache = capsule / ".qwq_output/data/local/cache/unrelated.json"
    runtime_cache.parent.mkdir(parents=True)
    runtime_cache.write_text("runtime-only\n", encoding="utf-8")

    for path in sorted(capsule.rglob("*"), reverse=True):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode & ~0o222)
    capsule.chmod(capsule.stat().st_mode & ~0o222)
    try:
        observed = SourceDigest.build(repo_root=capsule)
    finally:
        for path in sorted(capsule.rglob("*"), reverse=True):
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | 0o700)
        capsule.chmod(capsule.stat().st_mode | 0o700)

    assert observed == expected
    assert not (
        capsule / ".qwq_output/data/local/cache/source-digest"
    ).exists()
