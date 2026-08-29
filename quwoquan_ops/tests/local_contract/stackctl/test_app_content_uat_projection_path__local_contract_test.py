"""Strict App UAT projection paths preserve their literal candidate identity.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands.app_preflight_uat_launch_binding import (
    _verified_dependency_projection_binding,
)
from quwoquan_ops.cli.commands.app_preflight_uat_projection_path import (
    SourceProjectionRootError,
    canonical_source_projection_root,
)


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _binding_report(root: Path) -> dict[str, str]:
    return {
        "dependencyProjectionExpectationRef": str(root / "expectation.json"),
        "dependencyProjectionExpectationDigest": _digest("a"),
        "dependencyProjectionPrebuildReadbackRef": str(root / "prebuild.json"),
        "dependencyProjectionPrebuildReadbackDigest": _digest("b"),
        "dependencyProjectionPostbuildReadbackRef": str(root / "postbuild.json"),
        "dependencyProjectionPostbuildReadbackDigest": _digest("c"),
    }


def test_canonical_projection_root_accepts_only_exact_real_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source-projection"
    root.mkdir()

    assert canonical_source_projection_root(str(root)) == root


@pytest.mark.parametrize("spelling", ("relative", "dot", "dotdot"))
def test_launch_binding_rejects_normalizable_raw_projection_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    spelling: str,
) -> None:
    root = tmp_path / "source-projection"
    root.mkdir()
    raw = {
        "relative": root.name,
        "dot": f"{root.parent}/./{root.name}",
        "dotdot": f"{root}/../{root.name}",
    }[spelling]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)

    with pytest.raises(
        ValueError,
        match=r"APP\.LAUNCH\.receipt_invalid: current dependency projection root",
    ):
        _verified_dependency_projection_binding(
            report=_binding_report(root),
            launch_projection={"sourceProjectionRoot": raw},
            platform="android",
        )


def test_launch_binding_rejects_projection_root_with_ancestor_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "real-parent/source-projection"
    root.mkdir(parents=True)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(root.parent, target_is_directory=True)
    linked_root = linked_parent / root.name
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)

    with pytest.raises(SourceProjectionRootError):
        canonical_source_projection_root(str(linked_root))
    with pytest.raises(
        ValueError,
        match=r"APP\.LAUNCH\.receipt_invalid: current dependency projection root",
    ):
        _verified_dependency_projection_binding(
            report=_binding_report(root),
            launch_projection={"sourceProjectionRoot": str(linked_root)},
            platform="android",
        )


@pytest.mark.parametrize("spelling", ("dot", "dotdot", "empty-segment"))
def test_dependency_evidence_rejects_normalizable_reference_spelling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    spelling: str,
) -> None:
    root = tmp_path / "source-projection"
    state = root / "state"
    state.mkdir(parents=True)
    report = _binding_report(state)
    report["dependencyProjectionExpectationRef"] = {
        "dot": f"{root}/./state/expectation.json",
        "dotdot": f"{state}/../state/expectation.json",
        "empty-segment": f"{root}//state/expectation.json",
    }[spelling]
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)

    with pytest.raises(ValueError, match=r"APP\.LAUNCH\.receipt_invalid"):
        _verified_dependency_projection_binding(
            report=report,
            launch_projection={"sourceProjectionRoot": str(root)},
            platform="android",
        )


def test_dependency_evidence_rejects_cross_root_and_linked_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "source-projection"
    state = root / "state"
    state.mkdir(parents=True)
    other = tmp_path / "other-projection"
    other.mkdir()
    report = _binding_report(state)
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)

    report["dependencyProjectionExpectationRef"] = str(other / "expectation.json")
    with pytest.raises(ValueError, match=r"APP\.LAUNCH\.receipt_invalid"):
        _verified_dependency_projection_binding(
            report=report,
            launch_projection={"sourceProjectionRoot": str(root)},
            platform="android",
        )

    real_parent = root / "real-state"
    real_parent.mkdir()
    (real_parent / "expectation.json").write_text("{}", encoding="utf-8")
    linked_parent = root / "linked-state"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    report["dependencyProjectionExpectationRef"] = str(
        linked_parent / "expectation.json"
    )
    with pytest.raises(ValueError, match=r"APP\.LAUNCH\.receipt_invalid"):
        _verified_dependency_projection_binding(
            report=report,
            launch_projection={"sourceProjectionRoot": str(root)},
            platform="android",
        )

    real = state / "real-expectation.json"
    real.write_text("{}", encoding="utf-8")
    linked = state / "linked-expectation.json"
    linked.symlink_to(real)
    report["dependencyProjectionExpectationRef"] = str(linked)
    with pytest.raises(ValueError, match=r"APP\.LAUNCH\.receipt_invalid"):
        _verified_dependency_projection_binding(
            report=report,
            launch_projection={"sourceProjectionRoot": str(root)},
            platform="android",
        )
