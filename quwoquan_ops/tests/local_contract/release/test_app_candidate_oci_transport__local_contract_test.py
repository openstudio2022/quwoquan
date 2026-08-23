from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from quwoquan_ops.ci import app_candidate_oci_transport as subject

SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"
EXPECTED_PRODUCTS = (
    "android-nonprod-apk",
    "android-prod-apk",
    "ios-nonprod-app",
    "ios-prod-app",
    "web-shared",
)


def test_shard_archive_round_trip_is_deterministic_and_collision_safe(
    tmp_path: Path,
) -> None:
    assert SPEC_REF
    shard = tmp_path / "shard"
    (shard / "payloads/android-nonprod-apk").mkdir(parents=True)
    (shard / "payloads/android-nonprod-apk/app-release.apk").write_bytes(b"apk")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    subject.create_archive(shard, first)
    subject.create_archive(shard, second)

    assert first.read_bytes() == second.read_bytes()
    aggregate = tmp_path / "aggregate"
    subject.merge_archive(first, aggregate)
    assert (
        aggregate / "payloads/android-nonprod-apk/app-release.apk"
    ).read_bytes() == b"apk"
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


def test_transport_materializes_exactly_canonical_product_repositories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert SPEC_REF
    assert subject.BUILD_PRODUCT_IDS == EXPECTED_PRODUCTS
    calls: list[list[str]] = []
    digest = "sha256:" + "a" * 64

    def fake_run(command: list[str], *, cwd: Path | None = None) -> str:
        del cwd
        calls.append(command)
        if command[:3] == ["oras", "resolve", "--full-reference"]:
            return command[3].split(":run-1", 1)[0] + "@" + digest
        if command[:2] == ["oras", "pull"]:
            stage = Path(command[3])
            product_id = stage.name
            shard = tmp_path / f"source-{product_id}"
            (shard / "application-packages").mkdir(parents=True)
            (shard / "application-packages" / f"{product_id}.json").write_text(
                "{}\n", encoding="utf-8"
            )
            subject.create_archive(shard, stage / subject.ARCHIVE_NAME)
            return ""
        raise AssertionError(command)

    monkeypatch.setattr(subject, "_run", fake_run)
    refs = subject.materialize_shards(
        bundle_dir=tmp_path / "aggregate",
        repository_prefix="ghcr.io/example/quwoquan",
        transport_tag="run-1",
    )

    assert tuple(refs) == EXPECTED_PRODUCTS
    assert refs == {
        product_id: (
            f"ghcr.io/example/quwoquan/app-candidate-shard-{product_id}@{digest}"
        )
        for product_id in EXPECTED_PRODUCTS
    }
    resolved_tags = [command[3] for command in calls if command[1] == "resolve"]
    assert resolved_tags == [
        f"ghcr.io/example/quwoquan/app-candidate-shard-{product_id}:run-1"
        for product_id in EXPECTED_PRODUCTS
    ]


def test_transport_media_identities_have_no_contract_number_suffix() -> None:
    assert SPEC_REF
    assert subject.ARTIFACT_TYPE == "application/vnd.quwoquan.app-candidate-shard"
    assert subject.LAYER_TYPE == "application/vnd.quwoquan.app-candidate-shard+tar+gzip"
