"""Local contracts for dependency-sync Android trust-root validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import app_dependency_sync as sync
from quwoquan_ops.tests.support.app_dependency_sync_test_support import source_identity


def _write_trust_root(root: Path) -> Path:
    trust_directory = root / "qwq_runtime"
    trust_directory.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    trust_directory.chmod(0o700)
    trust_path = trust_directory / "runtime-config-trust.json"
    trust_path.write_text("{}", encoding="utf-8")
    trust_path.chmod(0o600)
    return trust_path


def test_runtime_trust_alias_into_repository_is_blocked_before_dependency_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_trust_root(repo / "private-trust")
    alias_parent = tmp_path / "outside-repository-alias"
    alias_parent.symlink_to(repo, target_is_directory=True)
    context = sync.DependencyComponentBuildContext(
        repo_root=repo,
        attempt_id="a" * 32,
        work_root=tmp_path / "work",
        process_root=tmp_path / "process",
        generation_root=tmp_path / "generation",
        flutter_identity={"executable": "/flutter"},
        source_identity=source_identity(),
    )

    def unexpected_toolchain(_raw: str) -> str:
        raise AssertionError("dependency commands must not start for repository trust")

    monkeypatch.setattr(
        sync._builder,
        "resolve_cocoapods_executable",
        unexpected_toolchain,
    )

    with pytest.raises(
        ValueError,
        match="APP.DEPENDENCY.android_runtime_trust_root_invalid",
    ):
        sync._builder.build_dependency_components(
            context,
            trust_root=alias_parent / "private-trust",
        )


def test_runtime_trust_root_canonicalizes_external_ancestor_alias(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    physical_parent = tmp_path / "physical"
    trust = physical_parent / "private-trust"
    trust_path = _write_trust_root(trust)
    alias_parent = tmp_path / "external-alias"
    alias_parent.symlink_to(physical_parent, target_is_directory=True)

    validated, sensitive = sync._builder._validated_runtime_trust_root(
        alias_parent / "private-trust",
        repo_root=repo,
    )

    assert validated == trust.resolve(strict=True)
    assert sensitive[:2] == (
        str(trust.resolve(strict=True)),
        str(trust_path.resolve(strict=True)),
    )
