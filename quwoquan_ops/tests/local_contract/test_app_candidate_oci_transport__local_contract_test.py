from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from quwoquan_ops.ci import app_candidate_oci_transport as subject


SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"


def test_shard_archive_round_trip_is_deterministic_and_collision_safe(
    tmp_path: Path,
) -> None:
    assert SPEC_REF
    shard = tmp_path / "shard"
    (shard / "payloads/alpha/android").mkdir(parents=True)
    (shard / "payloads/alpha/android/app-release.apk").write_bytes(b"apk")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    subject.create_archive(shard, first)
    subject.create_archive(shard, second)

    assert first.read_bytes() == second.read_bytes()
    aggregate = tmp_path / "aggregate"
    subject.merge_archive(first, aggregate)
    assert (aggregate / "payloads/alpha/android/app-release.apk").read_bytes() == b"apk"
    with pytest.raises(ValueError, match="file collision"):
        subject.merge_archive(second, aggregate)


def test_shard_archive_rejects_path_traversal(tmp_path: Path) -> None:
    assert SPEC_REF
    archive_path = tmp_path / subject.ARCHIVE_NAME
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"escape"
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    with pytest.raises(ValueError, match="unsafe"):
        subject.merge_archive(archive_path, tmp_path / "aggregate")


def test_transport_media_identities_have_no_contract_number_suffix() -> None:
    assert SPEC_REF
    assert subject.ARTIFACT_TYPE == "application/vnd.quwoquan.app-candidate-shard"
    assert subject.LAYER_TYPE == "application/vnd.quwoquan.app-candidate-shard+tar+gzip"
