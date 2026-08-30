"""Strict App UAT projection paths preserve their literal candidate identity.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import (
    app_preflight_uat_projection_path as projection_path,
)
from quwoquan_ops.cli.commands.app_preflight_uat_launch_binding import (
    _exact_source_capsule_manifest_ref,
    _verified_candidate_contract_graph_binding,
    _verified_dependency_projection_binding,
)
from quwoquan_ops.cli.commands.app_preflight_uat_projection_path import (
    SourceProjectionRootError,
    canonical_source_projection_root,
    load_canonical_projection_evidence,
)


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _binding_report(root: Path) -> dict[str, object]:
    return {
        "dependencyProjectionExpectationRef": str(root / "expectation.json"),
        "dependencyProjectionExpectationDigest": _digest("a"),
        "dependencyProjectionPrebuildReadbackRef": str(root / "prebuild.json"),
        "dependencyProjectionPrebuildReadbackDigest": _digest("b"),
        "dependencyProjectionPostbuildReadbackRef": str(root / "postbuild.json"),
        "dependencyProjectionPostbuildReadbackDigest": _digest("c"),
    }


@pytest.mark.parametrize(
    "raw",
    (
        "relative/manifest.json",
        "~/manifest.json",
        "/candidate/./manifest.json",
        "/candidate/child/../manifest.json",
        "/candidate//manifest.json",
        "/candidate/manifest.json ",
    ),
)
def test_source_capsule_refs_reject_noncanonical_raw_bytes(raw: str) -> None:
    with pytest.raises(ValueError, match=r"APP\.LAUNCH\.receipt_invalid"):
        _exact_source_capsule_manifest_ref(raw, raw)


def test_source_capsule_refs_require_exact_string_equality_before_path_use() -> None:
    canonical = "/candidate/input-capsule/manifest.json"
    assert _exact_source_capsule_manifest_ref(canonical, canonical) == canonical
    with pytest.raises(ValueError, match="source identity drifted"):
        _exact_source_capsule_manifest_ref(
            canonical,
            "/other-candidate/input-capsule/manifest.json",
        )


def test_candidate_contract_graph_binds_manifest_entry_and_projection_bytes(
    tmp_path: Path,
) -> None:
    candidate_root = (tmp_path / "candidate").resolve()
    capsule_root = candidate_root / "input-capsule"
    projection_root = (tmp_path / "source-projection").resolve()
    graph_relative = Path("quwoquan_service/generated/contract_graph.json")
    graph_ref = projection_root / graph_relative
    graph_ref.parent.mkdir(parents=True)
    encoded = json.dumps(
        {
            "operations": [
                {
                    "id": "content.post.GetFeed",
                    "errorCodes": ["CONTENT.SYSTEM.required_dependency_unavailable"],
                }
            ]
        },
        separators=(",", ":"),
    ).encode("utf-8")
    graph_ref.write_bytes(encoded)
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    capsule_root.mkdir(parents=True)
    manifest_ref = capsule_root / "manifest.json"
    manifest_ref.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "logicalPath": graph_relative.as_posix(),
                        "capsulePath": f"repo/{graph_relative.as_posix()}",
                        "kind": "file",
                        "digest": digest,
                        "mode": 0o444,
                        "size": len(encoded),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    launch_projection = {
        "sourceCapsuleManifestRef": str(manifest_ref),
        "sourceProjectionRoot": str(projection_root),
    }

    binding = _verified_candidate_contract_graph_binding(
        runtime_binding={"contractGraphDigest": digest},
        launch_projection=launch_projection,
    )
    assert binding == {
        "contractGraphDigest": digest,
        "contractGraphRef": str(graph_ref),
        "contractGraphOperationCount": 1,
        "sourceProjectionRoot": str(projection_root),
    }

    graph_ref.write_text('{"operations":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="ContractGraph projection drifted"):
        _verified_candidate_contract_graph_binding(
            runtime_binding={"contractGraphDigest": digest},
            launch_projection=launch_projection,
        )


@pytest.mark.parametrize(
    "field",
    (
        "dependencyProjectionExpectationRef",
        "dependencyProjectionExpectationDigest",
        "dependencyProjectionPrebuildReadbackRef",
        "dependencyProjectionPrebuildReadbackDigest",
        "dependencyProjectionPostbuildReadbackRef",
        "dependencyProjectionPostbuildReadbackDigest",
    ),
)
@pytest.mark.parametrize("invalid", (7, True, " leading", "trailing "))
def test_dependency_binding_rejects_non_exact_raw_ref_or_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    invalid: object,
) -> None:
    root = tmp_path / "source-projection"
    root.mkdir()
    report = _binding_report(root)
    report[field] = invalid
    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)

    with pytest.raises(ValueError, match=r"APP\.LAUNCH\.receipt_invalid"):
        _verified_dependency_projection_binding(
            report=report,
            launch_projection={"sourceProjectionRoot": str(root)},
            platform="android",
        )


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


def test_dependency_evidence_rejects_file_name_swap_during_fd_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "source-projection"
    state = root / "state"
    state.mkdir(parents=True)
    evidence = state / "expectation.json"
    evidence.write_bytes(b"first")
    evidence.chmod(0o600)
    original_read = projection_path.os.read
    swapped = False

    def swap_then_read(descriptor: int, count: int) -> bytes:
        nonlocal swapped
        if not swapped:
            swapped = True
            evidence.rename(state / "old-expectation.json")
            evidence.write_bytes(b"replacement")
            evidence.chmod(0o600)
        return original_read(descriptor, count)

    monkeypatch.setattr(projection_path.os, "read", swap_then_read)
    with pytest.raises(ValueError, match="changed during read"):
        load_canonical_projection_evidence(
            str(evidence),
            projection_root=root,
            output_root=tmp_path,
            label="expectation",
            loader=lambda path, encoded, mode: (path, encoded, mode),
        )


def test_dependency_evidence_rejects_ancestor_swap_during_fd_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "source-projection"
    state = root / "state"
    state.mkdir(parents=True)
    evidence = state / "expectation.json"
    evidence.write_bytes(b"first")
    evidence.chmod(0o600)
    original_read = projection_path.os.read
    swapped = False

    def swap_then_read(descriptor: int, count: int) -> bytes:
        nonlocal swapped
        if not swapped:
            swapped = True
            state.rename(root / "old-state")
            state.mkdir()
            evidence.write_bytes(b"replacement")
            evidence.chmod(0o600)
        return original_read(descriptor, count)

    monkeypatch.setattr(projection_path.os, "read", swap_then_read)
    with pytest.raises(ValueError, match="changed during read"):
        load_canonical_projection_evidence(
            str(evidence),
            projection_root=root,
            output_root=tmp_path,
            label="expectation",
            loader=lambda path, encoded, mode: (path, encoded, mode),
        )
