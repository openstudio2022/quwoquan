"""Release 交付 key → 环境媒体根同步（WP5 环境通路）契约测试。

覆盖：增量 copy/skip、声明摘要与内容不符时 fail closed、目标漂移 repaired、
research CAS 交付 key 同步（DEC-031）、prune 不触及 CAS 根、
topology CDN base 解析（prod invalid fallback 阻断）。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(p for p in Path(__file__).resolve().parents if p.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.environment.topology import resolve_media_cdn_bases
from core.media_library_sync import sync_media_library


def _write_public_slice(
    root: Path,
    key: str,
    payload: bytes,
) -> tuple[str, str]:
    """Write one release public slice and return its (key, declared digest)."""
    target = root / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return key, "sha256:" + hashlib.sha256(payload).hexdigest()


class TestSyncMediaLibrary:
    def test_copies_new_objects_and_skips_existing(self, tmp_path: Path) -> None:
        source = tmp_path / "release-payload"
        dest = tmp_path / "media-root"
        key_a, digest_a = _write_public_slice(
            source,
            "media/image/s/release-a/post-a/v1/cover.jpg",
            b"alpha-image-bytes",
        )
        key_b, digest_b = _write_public_slice(
            source,
            "media/avatar/s/release-a/creator-a/v1/avatar.png",
            b"beta-avatar-bytes",
        )
        closure = {key_a: digest_a, key_b: digest_b}

        first = sync_media_library(source, dest, object_digests=closure)
        assert first["copied"] == 2
        assert first["skipped"] == 0
        assert first["failed"] == 0
        assert first["issues"] == []
        assert (dest / key_a).read_bytes() == b"alpha-image-bytes"

        second = sync_media_library(source, dest, object_digests=closure)
        assert second["copied"] == 0
        assert second["skipped"] == 2
        assert second["failed"] == 0

    def test_corrupt_source_is_fail_closed(self, tmp_path: Path) -> None:
        source = tmp_path / "release-payload"
        dest = tmp_path / "media-root"
        key, digest = _write_public_slice(
            source,
            "media/image/s/release-a/post-a/v1/cover.jpg",
            b"honest-bytes",
        )
        (source / key).write_bytes(b"tampered-bytes")

        report = sync_media_library(source, dest, object_digests={key: digest})
        assert report["copied"] == 0
        assert report["failed"] == 1
        assert any("corrupt" in issue for issue in report["issues"])
        assert not (dest / key).exists()

    def test_drifted_destination_is_repaired(self, tmp_path: Path) -> None:
        source = tmp_path / "release-payload"
        dest = tmp_path / "media-root"
        key, digest = _write_public_slice(
            source,
            "media/image/s/release-a/post-a/v1/cover.jpg",
            b"stable-bytes",
        )
        target = dest / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"drifted-bytes")

        report = sync_media_library(source, dest, object_digests={key: digest})
        assert report["repaired"] == 1
        assert report["failed"] == 0
        assert target.read_bytes() == b"stable-bytes"

    def test_missing_source_root_reports_issue(self, tmp_path: Path) -> None:
        report = sync_media_library(
            tmp_path / "nope",
            tmp_path / "media-root",
            object_digests={
                "media/image/s/release-a/post-a/v1/cover.jpg": "sha256:" + "0" * 64,
            },
        )
        assert report["objects"] == 0
        assert any("missing" in issue for issue in report["issues"])

    def test_empty_release_closure_is_an_idempotent_success(self, tmp_path: Path) -> None:
        report = sync_media_library(
            tmp_path / "release-without-media",
            tmp_path / "media-root",
            object_digests={},
        )

        assert report["scope"] == "public-slices"
        assert report["requestedObjects"] == 0
        assert report["objects"] == 0
        assert report["issues"] == []

    def test_selected_release_closure_never_copies_unrelated_slices(self, tmp_path: Path) -> None:
        source = tmp_path / "release-payload"
        dest = tmp_path / "media-root"
        selected_key, selected_digest = _write_public_slice(
            source,
            "media/image/s/release-a/post-a/v1/cover.jpg",
            b"release-selected",
        )
        unrelated_key, _ = _write_public_slice(
            source,
            "media/image/s/release-a/post-b/v1/cover.jpg",
            b"payload-but-not-selected",
        )

        report = sync_media_library(
            source,
            dest,
            object_digests={selected_key: selected_digest},
        )

        assert report["scope"] == "public-slices"
        assert report["requestedObjects"] == 1
        assert report["objects"] == 1
        assert report["copied"] == 1
        assert report["issues"] == []
        assert (dest / selected_key).is_file()
        assert not (dest / unrelated_key).exists()

    def test_research_cas_delivery_key_is_synced(self, tmp_path: Path) -> None:
        """DEC-031：research release 以 CAS objectKey 为交付 key，字节须落进环境媒体根。"""
        source = tmp_path / "release-payload"
        dest = tmp_path / "media-root"
        payload = b"private-body"
        digest = hashlib.sha256(payload).hexdigest()
        cas_key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.jpg"
        cas_object = source / cas_key
        cas_object.parent.mkdir(parents=True, exist_ok=True)
        cas_object.write_bytes(payload)

        report = sync_media_library(
            source,
            dest,
            object_digests={cas_key: f"sha256:{digest}"},
        )

        assert report["objects"] == 1
        assert report["copied"] == 1
        assert report["issues"] == []
        assert (dest / cas_key).read_bytes() == payload

    def test_non_delivery_prefix_key_is_rejected(self, tmp_path: Path) -> None:
        """既非 public slice 也非 CAS objectKey 的 key 不得进入环境媒体根。"""
        source = tmp_path / "release-payload"
        payload = b"rogue-body"
        digest = hashlib.sha256(payload).hexdigest()
        rogue_key = "media/image/p/release-a/post-a/v1/cover.jpg"
        rogue_object = source / rogue_key
        rogue_object.parent.mkdir(parents=True, exist_ok=True)
        rogue_object.write_bytes(payload)

        report = sync_media_library(
            source,
            tmp_path / "media-root",
            object_digests={rogue_key: f"sha256:{digest}"},
        )

        assert report["objects"] == 0
        assert report["copied"] == 0
        assert any("unsafe" in issue for issue in report["issues"])

    def test_full_sync_prune_never_touches_cas_root(self, tmp_path: Path) -> None:
        """环境上传媒体共用 CAS 前缀：prune 只回收 public slice，不得删除 CAS 对象。"""
        source = tmp_path / "release-payload"
        dest = tmp_path / "media-root"
        payload = b"research-cover"
        digest = hashlib.sha256(payload).hexdigest()
        cas_key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.webp"
        cas_object = source / cas_key
        cas_object.parent.mkdir(parents=True, exist_ok=True)
        cas_object.write_bytes(payload)
        uploaded = dest / "media/objects/sha256/aa/bb/aabb.jpg"
        uploaded.parent.mkdir(parents=True, exist_ok=True)
        uploaded.write_bytes(b"user-uploaded-body")
        stale_slice = dest / "media/image/s/release-old/post-old/v1/cover.jpg"
        stale_slice.parent.mkdir(parents=True, exist_ok=True)
        stale_slice.write_bytes(b"prior-release-cover")

        report = sync_media_library(
            source,
            dest,
            object_digests={cas_key: f"sha256:{digest}"},
            prune_unselected=True,
        )

        assert report["failed"] == 0
        assert report["issues"] == []
        assert report["pruned"] == 1
        assert uploaded.read_bytes() == b"user-uploaded-body"
        assert not stale_slice.exists()
        assert (dest / cas_key).read_bytes() == payload

    def test_selected_release_closure_rejects_missing_or_unsafe_slices(self, tmp_path: Path) -> None:
        source = tmp_path / "release-payload"
        _write_public_slice(
            source,
            "media/image/s/release-a/post-a/v1/cover.jpg",
            b"present",
        )

        report = sync_media_library(
            source,
            tmp_path / "media-root",
            object_digests={
                "../escape.jpg": "sha256:" + "1" * 64,
                "media/image/s/release-a/post-a/v1/absent.jpg": "sha256:" + "2" * 64,
                "media/image/s/release-a/post-a/v1/cover.jpg": "not-a-digest",
            },
        )

        assert report["objects"] == 0
        assert report["issues"]
        assert any("unsafe" in issue for issue in report["issues"])
        assert any("missing" in issue for issue in report["issues"])

    def test_full_sync_public_slices_prunes_fixture_and_prior_release_media(
        self,
        tmp_path: Path,
    ) -> None:
        source = tmp_path / "release-payload"
        dest = tmp_path / "media-root"
        selected = source / "media/image/s/release-a/post-a/v1/cover.jpg"
        selected.parent.mkdir(parents=True, exist_ok=True)
        selected.write_bytes(b"release-a-cover")
        selected_digest = hashlib.sha256(selected.read_bytes()).hexdigest()
        stale_fixture = dest / "media/image/s/archived-image/post/fixture_post/cover.jpg"
        stale_fixture.parent.mkdir(parents=True, exist_ok=True)
        stale_fixture.write_bytes(b"fixture-cover")
        stale_prior = dest / "media/video/s/release-old/post-old/v1/video.mp4"
        stale_prior.parent.mkdir(parents=True, exist_ok=True)
        stale_prior.write_bytes(b"prior-release-video")
        infrastructure_probe = dest / "probes/media-edge/health.txt"
        infrastructure_probe.parent.mkdir(parents=True, exist_ok=True)
        infrastructure_probe.write_text("ready", encoding="utf-8")

        report = sync_media_library(
            source,
            dest,
            object_digests={
                selected.relative_to(source).as_posix(): f"sha256:{selected_digest}",
            },
            prune_unselected=True,
        )

        assert report["failed"] == 0
        assert report["issues"] == []
        assert report["pruned"] == 2
        assert (dest / selected.relative_to(source)).read_bytes() == b"release-a-cover"
        assert not stale_fixture.exists()
        assert not stale_prior.exists()
        assert infrastructure_probe.read_text(encoding="utf-8") == "ready"

    def test_full_sync_does_not_prune_when_selected_release_is_invalid(
        self,
        tmp_path: Path,
    ) -> None:
        source = tmp_path / "release-payload"
        dest = tmp_path / "media-root"
        stale = dest / "media/image/s/release-old/post-old/v1/cover.jpg"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes(b"recoverable-old-release")

        report = sync_media_library(
            source,
            dest,
            object_digests={
                "media/image/s/release-new/post-new/v1/cover.jpg": "sha256:" + "0" * 64,
            },
            prune_unselected=True,
        )

        assert report["issues"]
        assert report["pruned"] == 0
        assert stale.read_bytes() == b"recoverable-old-release"


class TestResolveMediaCdnBases:
    def _manifest(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "environment_topology_manifest.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_resolves_gamma_bases_from_manifest(self, tmp_path: Path) -> None:
        manifest = self._manifest(
            tmp_path,
            (
                '{"environments": {"gamma": {"publicBases": {'
                '"mediaImage": "https://cdn.gamma.example.invalid:19100/media/image",'
                '"mediaVideo": "https://cdn.gamma.example.invalid:19100/media/video"}}}}'
            ),
        )
        image, video = resolve_media_cdn_bases("gamma", topology_manifest=manifest)
        assert image == "https://cdn.gamma.example.invalid:19100/media/image"
        assert video == "https://cdn.gamma.example.invalid:19100/media/video"

    def test_non_prod_missing_base_returns_empty(self, tmp_path: Path) -> None:
        manifest = self._manifest(tmp_path, '{"environments": {}}')
        image, video = resolve_media_cdn_bases("gamma", topology_manifest=manifest)
        assert image == ""
        assert video == ""

    def test_prod_missing_base_blocks(self, tmp_path: Path) -> None:
        manifest = self._manifest(tmp_path, '{"environments": {}}')
        with pytest.raises(SystemExit, match="prod media CDN base unresolved"):
            resolve_media_cdn_bases("prod", topology_manifest=manifest)

    def test_prod_invalid_placeholder_blocks(self, tmp_path: Path) -> None:
        manifest = self._manifest(
            tmp_path,
            (
                '{"environments": {"prod": {"publicBases": {'
                '"mediaImage": "https://media.quwoquan.invalid"}}}}'
            ),
        )
        with pytest.raises(SystemExit, match="refusing media.quwoquan.invalid"):
            resolve_media_cdn_bases("prod", topology_manifest=manifest)

    def test_repo_manifest_resolves_all_env_image_bases(self) -> None:
        """真仓库 manifest：四环境 image base 均可解析且 prod 非占位。"""
        for env in ("alpha", "beta", "gamma", "prod"):
            image, _video = resolve_media_cdn_bases(env)
            assert image, f"{env} mediaImage missing in repo topology manifest"
            assert "quwoquan.invalid" not in image
