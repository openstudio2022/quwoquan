"""Local contracts for the dependency-sync source projection closure."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from quwoquan_ops.cli.commands import app_dependency_sync as sync
from quwoquan_ops.cli.commands import app_dependency_sync_projection as projection
from quwoquan_ops.tests.support.app_dependency_sync_test_support import (
    PROJECTION_INPUTS,
    PROJECTION_MANIFEST,
    PROJECTION_OUTPUTS,
    minimal_projection_source,
    write_projection_closure,
)


def _manifest(root: Path) -> dict[str, Any]:
    return json.loads((root / PROJECTION_MANIFEST).read_text(encoding="utf-8"))


def _write_manifest(root: Path, value: dict[str, Any]) -> None:
    (root / PROJECTION_MANIFEST).write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def test_projection_materializes_current_metadata_and_ops_output_closure(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    contents = {
        relative: (repo / relative).read_bytes()
        for relative in (*PROJECTION_INPUTS, *PROJECTION_OUTPUTS)
    }

    app = sync._project(repo, tmp_path / "projection")
    target = app.parent

    for relative in (*PROJECTION_INPUTS, *PROJECTION_OUTPUTS):
        assert (target / relative).read_bytes() == contents[relative]
    assert (target / PROJECTION_MANIFEST).read_bytes() == (
        repo / PROJECTION_MANIFEST
    ).read_bytes()


def test_projection_follows_new_manifest_declared_metadata_input(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    dynamic = "quwoquan_service/contracts/metadata/_shared/new_contract.yaml"
    contents = write_projection_closure(
        repo,
        inputs=(*PROJECTION_INPUTS, dynamic),
    )

    app = sync._project(repo, tmp_path / "projection")

    assert (app.parent / dynamic).read_bytes() == contents[dynamic]


def test_projection_rejects_declared_digest_mismatch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    (repo / PROJECTION_INPUTS[0]).write_text("drift\n", encoding="utf-8")

    with pytest.raises(ValueError, match="closure_digest_mismatch"):
        sync._project(repo, tmp_path / "projection")


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    [
        ("schema", "wrong-schema", "manifest_schema_invalid"),
        ("generator", "wrong-generator", "manifest_generator_invalid"),
        ("sourceDigest", "sha256:wrong", "manifest_digest_invalid"),
    ],
)
def test_projection_rejects_noncanonical_manifest_identity(
    tmp_path: Path, field: str, value: str, blocker: str
) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    manifest = _manifest(repo)
    manifest[field] = value
    _write_manifest(repo, manifest)

    with pytest.raises(ValueError, match=blocker):
        sync._project(repo, tmp_path / "projection")


@pytest.mark.parametrize(
    ("kind", "invalid", "blocker"),
    [
        (
            "inputs",
            "quwoquan_service/contracts/runtime_errors/not_metadata.yaml",
            "manifest_input_outside_allowlist",
        ),
        (
            "outputs",
            "quwoquan_service/contracts/metadata/generated.py",
            "manifest_output_outside_allowlist",
        ),
    ],
)
def test_projection_rejects_closure_path_outside_allowlist(
    tmp_path: Path, kind: str, invalid: str, blocker: str
) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    manifest = _manifest(repo)
    manifest[kind][0]["path"] = invalid
    _write_manifest(repo, manifest)

    with pytest.raises(ValueError, match=blocker):
        sync._project(repo, tmp_path / "projection")


@pytest.mark.parametrize("invalid", ["/absolute.yaml", "../escape.yaml"])
def test_projection_rejects_non_relative_manifest_path(
    tmp_path: Path, invalid: str
) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    manifest = _manifest(repo)
    manifest["inputs"][0]["path"] = invalid
    _write_manifest(repo, manifest)

    with pytest.raises(ValueError, match="manifest_path_invalid"):
        sync._project(repo, tmp_path / "projection")


def test_projection_rejects_duplicate_manifest_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    manifest = _manifest(repo)
    manifest["inputs"][1]["path"] = manifest["inputs"][0]["path"]
    _write_manifest(repo, manifest)

    with pytest.raises(ValueError, match="manifest_path_duplicate"):
        sync._project(repo, tmp_path / "projection")


def _make_unsafe(path: Path, mode: str, root: Path) -> None:
    content = path.read_bytes()
    path.unlink()
    if mode == "missing":
        return
    peer = root / f"{mode}-peer"
    peer.write_bytes(content)
    if mode == "symlink":
        path.symlink_to(peer)
    else:
        os.link(peer, path)


@pytest.mark.parametrize("mode", ["symlink", "hardlink", "missing"])
@pytest.mark.parametrize("relative", [PROJECTION_MANIFEST, PROJECTION_INPUTS[0]])
def test_projection_rejects_unsafe_or_missing_manifest_closure_source(
    tmp_path: Path, mode: str, relative: str
) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    _make_unsafe(repo / relative, mode, repo)

    with pytest.raises(
        ValueError,
        match="APP.DEPENDENCY.source_projection_source_read_invalid",
    ):
        sync._project(repo, tmp_path / "projection")


@pytest.mark.parametrize(
    "linked_parent",
    [
        "quwoquan_service/contracts/metadata",
        "quwoquan_ops/cli/lib/generated",
    ],
)
def test_projection_rejects_linked_closure_parent_before_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    linked_parent: str,
) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    linked = repo / linked_parent
    external = tmp_path / f"external-{linked.name}"
    linked.rename(external)
    linked.symlink_to(external, target_is_directory=True)

    def unexpected_copy(*_args: object, **_kwargs: object) -> Path:
        raise AssertionError(
            "projection copy must not start for a linked closure parent"
        )

    monkeypatch.setattr(projection.shutil, "copytree", unexpected_copy)
    target = tmp_path / "projection"

    with pytest.raises(
        ValueError,
        match="APP.DEPENDENCY.source_projection_source_read_invalid",
    ):
        sync._project(repo, target)

    assert not target.exists()


def test_projection_rejects_noncanonical_source_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    alias = tmp_path / "repo-alias"
    alias.symlink_to(repo, target_is_directory=True)

    with pytest.raises(
        ValueError,
        match="APP.DEPENDENCY.source_projection_source_root_invalid",
    ):
        sync._project(alias, tmp_path / "projection")


def test_projection_rejects_noncanonical_target_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    physical_parent = tmp_path / "physical-target-parent"
    physical_parent.mkdir()
    alias_parent = tmp_path / "target-parent-alias"
    alias_parent.symlink_to(physical_parent, target_is_directory=True)

    with pytest.raises(
        ValueError,
        match="APP.DEPENDENCY.source_projection_target_parent_invalid",
    ):
        sync._project(repo, alias_parent / "projection")

    assert not (physical_parent / "projection").exists()


def test_projection_does_not_overwrite_mismatched_app_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    original = projection.shutil.copytree

    def copytree(source: Path, target: Path, *args: Any, **kwargs: Any) -> Path:
        result = original(source, target, *args, **kwargs)
        if Path(source).name == "quwoquan_app":
            copied = Path(target) / Path(PROJECTION_OUTPUTS[0]).relative_to(
                "quwoquan_app"
            )
            copied.write_text("wrong copy\n", encoding="utf-8")
        return result

    monkeypatch.setattr(projection.shutil, "copytree", copytree)

    with pytest.raises(ValueError, match="closure_drift"):
        sync._project(repo, tmp_path / "projection")


def test_projection_second_source_readback_detects_concurrent_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    minimal_projection_source(repo)
    original = projection._assert_projection_closure

    def assert_then_drift(target: Path, seal: Any) -> None:
        original(target, seal)
        (repo / PROJECTION_INPUTS[0]).write_text("concurrent drift\n", encoding="utf-8")

    monkeypatch.setattr(projection, "_assert_projection_closure", assert_then_drift)

    with pytest.raises(ValueError, match="source_drift"):
        sync._project(repo, tmp_path / "projection")
