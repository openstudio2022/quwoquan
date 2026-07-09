"""ship 环境媒体通路契约（WP5）：CDN base topology 解析 + CAS 媒体同步步骤。"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import pytest  # noqa: E402

import ship.handler as ship_handler  # noqa: E402
from _common.io import read_json  # noqa: E402


class TestMediaCdnBasesForEnv:
    def test_env_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QWQ_MEDIA_IMAGE_CDN_BASE_URL", "https://override-image.example")
        monkeypatch.setenv("QWQ_MEDIA_VIDEO_CDN_BASE_URL", "https://override-video.example")
        image, video = ship_handler._media_cdn_bases_for_env("gamma")
        assert image == "https://override-image.example"
        assert video == "https://override-video.example"

    def test_falls_back_to_topology_manifest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("QWQ_MEDIA_IMAGE_CDN_BASE_URL", raising=False)
        monkeypatch.delenv("QWQ_MEDIA_VIDEO_CDN_BASE_URL", raising=False)
        monkeypatch.setattr(
            ship_handler,
            "resolve_media_cdn_bases",
            lambda env: (f"https://{env}-image.resolved", f"https://{env}-video.resolved"),
        )
        image, video = ship_handler._media_cdn_bases_for_env("gamma")
        assert image == "https://gamma-image.resolved"
        assert video == "https://gamma-video.resolved"

    def test_prod_placeholder_override_blocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QWQ_MEDIA_IMAGE_CDN_BASE_URL", "https://media.quwoquan.invalid")
        with pytest.raises(SystemExit, match="quwoquan.invalid"):
            ship_handler._media_cdn_bases_for_env("prod")

    def test_prod_topology_block_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("QWQ_MEDIA_IMAGE_CDN_BASE_URL", raising=False)

        def _blocked(env: str) -> tuple[str, str]:
            raise SystemExit("FAIL: prod media CDN base unresolved")

        monkeypatch.setattr(ship_handler, "resolve_media_cdn_bases", _blocked)
        with pytest.raises(SystemExit, match="unresolved"):
            ship_handler._media_cdn_bases_for_env("prod")


class TestShipMediaSyncStep:
    def _seed_cas_object(self, library: Path, payload: bytes) -> Path:
        digest = hashlib.sha256(payload).hexdigest()
        obj = library / "media" / "objects" / "sha256" / digest[:2] / digest[2:4] / f"{digest}.jpg"
        obj.parent.mkdir(parents=True, exist_ok=True)
        obj.write_bytes(payload)
        return obj

    def test_sync_step_copies_and_writes_report(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        publish_root = tmp_path / "publish"
        library = publish_root / "media" / "library"
        obj = self._seed_cas_object(library, b"pilot-image")
        dest = tmp_path / "media-root"
        monkeypatch.setattr(ship_handler, "PUBLISH_ROOT", publish_root)

        report_path = ship_handler._sync_media_to_root(str(dest), release_id="rel-test-1")
        report = read_json(report_path)
        assert report["copied"] == 1
        assert report["failed"] == 0
        assert (dest / obj.relative_to(library)).is_file()
        assert report_path == publish_root / "env_releases" / "rel-test-1" / "media-sync.json"

    def test_sync_step_blocks_on_corrupt_source(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        publish_root = tmp_path / "publish"
        library = publish_root / "media" / "library"
        obj = self._seed_cas_object(library, b"honest")
        obj.write_bytes(b"tampered")
        monkeypatch.setattr(ship_handler, "PUBLISH_ROOT", publish_root)

        with pytest.raises(SystemExit, match="media sync failed"):
            ship_handler._sync_media_to_root(str(tmp_path / "media-root"), release_id="rel-test-2")

    def test_ship_parser_exposes_sync_media_root(self) -> None:
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        ship_handler.register_parser(subparsers)
        args = parser.parse_args(["ship", "--skip-promote", "--sync-media-root", "/tmp/x"])
        assert args.sync_media_root == "/tmp/x"
