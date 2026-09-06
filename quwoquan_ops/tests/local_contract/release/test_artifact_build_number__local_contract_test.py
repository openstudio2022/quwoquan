import json
from pathlib import Path

import pytest

from quwoquan_ops.ci.artifact_build_number import (
    ArtifactBuildNumberError, allocate, allocate_hosted_sequence, digest,
)


def exact(root: Path, path: Path) -> dict[str, str]:
    return {"ref": path.relative_to(root).as_posix(), "digest": digest(path)}


def test_allocator_is_monotonic_append_only_and_idempotent(tmp_path: Path) -> None:
    first = allocate(root=tmp_path, request_id="rc-v1.2.3-1", predecessor_ref=None, allocated_at="2026-09-05T10:00:00Z")
    assert json.loads(first.read_text())["artifactBuildNumber"] == 1
    assert allocate(root=tmp_path, request_id="rc-v1.2.3-1", predecessor_ref=None, allocated_at="2026-09-05T10:00:00Z") == first
    second = allocate(root=tmp_path, request_id="rc-v1.2.3-2", predecessor_ref=exact(tmp_path, first), allocated_at="2026-09-05T10:01:00Z")
    assert json.loads(second.read_text())["artifactBuildNumber"] == 2


def test_allocator_rejects_stale_predecessor(tmp_path: Path) -> None:
    first = allocate(root=tmp_path, request_id="one", predecessor_ref=None, allocated_at="2026-09-05T10:00:00Z")
    reference = exact(tmp_path, first); first.write_text("{}\n")
    with pytest.raises(ArtifactBuildNumberError, match="STALE_PREDECESSOR"):
        allocate(root=tmp_path, request_id="two", predecessor_ref=reference, allocated_at="2026-09-05T10:01:00Z")


def test_hosted_sequence_binds_exact_qualification_request(tmp_path: Path) -> None:
    request_body = {
        "schema": "quwoquan_ops.release_qualification_request.v1",
        "requestId": "sha256:" + "a" * 64,
    }
    request = tmp_path / "request.json"
    request.write_text(json.dumps(request_body, sort_keys=True, separators=(",", ":")) + "\n")
    request_ref = exact(tmp_path, request)
    first = allocate_hosted_sequence(
        root=tmp_path, request_ref=request_ref, hosted_run_number=41, hosted_run_id="9001"
    )
    fact = json.loads(first.read_text())
    assert fact["artifactBuildNumber"] == 41
    assert fact["qualificationRequest"] == request_ref
    assert fact["hostedAuthority"]["provider"] == "github_actions_workflow_run_number"
    assert allocate_hosted_sequence(
        root=tmp_path, request_ref=request_ref, hosted_run_number=41, hosted_run_id="9001"
    ) == first


def test_hosted_sequence_rejects_number_reuse_for_another_request(tmp_path: Path) -> None:
    refs = []
    for suffix in ("a", "b"):
        path = tmp_path / f"request-{suffix}.json"
        path.write_text(json.dumps({
            "schema": "quwoquan_ops.release_qualification_request.v1",
            "requestId": "sha256:" + suffix * 64,
        }, sort_keys=True, separators=(",", ":")) + "\n")
        refs.append(exact(tmp_path, path))
    allocate_hosted_sequence(
        root=tmp_path, request_ref=refs[0], hosted_run_number=42, hosted_run_id="9002"
    )
    with pytest.raises(ArtifactBuildNumberError, match="CAS_CONFLICT"):
        allocate_hosted_sequence(
            root=tmp_path, request_ref=refs[1], hosted_run_number=42, hosted_run_id="9003"
        )
