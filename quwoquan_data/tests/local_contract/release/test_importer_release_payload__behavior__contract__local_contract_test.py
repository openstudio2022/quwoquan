"""Service importers consume immutable release object snapshots only."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

from content.release.environment import importers
from content.release.environment.handler import _sync_media
from content.release.model import ImportMode


def test_importers_read_release_payload_without_publish_root(
    tmp_path: Path, monkeypatch
) -> None:
    release = tmp_path / "releases/release-a"
    run = tmp_path / "runs/apply-a"
    payload = release / "payload/desired_state.json"
    payload.parent.mkdir(parents=True)
    payload.write_text('{"releaseId":"release-a"}\n', encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(importers.subprocess, "run", fake_run)
    monkeypatch.setattr(
        importers,
        "assert_import_report_contract",
        lambda *_args, **_kwargs: {
            "releaseId": "release-a",
            "issues": [],
            "skipped": [],
            "projected": 0,
            "entityRefToHomepageId": {},
            "tagRefs": ["Topic/旅行"],
            "nodeCount": 1,
        },
    )
    monkeypatch.setattr(
        importers,
        "read_json",
        lambda _path: {
            "desiredRefs": {"entities": [], "tags": ["Topic/旅行"]}
        },
    )

    importers.run_tag_importer(
        release=release,
        env="gamma",
        run=run,
        mongo_uri="mongodb://gamma",
        dry_run=True,
    )
    importers.run_content_importer(
        release=release,
        env="gamma",
        run=run,
        mongo_uri="mongodb://gamma",
        media_avatar_base_url="https://cdn.example.invalid",
        media_image_base_url="https://cdn.example.invalid",
        media_video_base_url="https://cdn.example.invalid",
        dry_run=True,
        creator_receipt=run / "creator-import.json",
    )
    importers.run_creator_importer(
        release=release,
        env="gamma",
        run=run,
        mongo_uri="mongodb://gamma",
        postgres_dsn="postgres://gamma",
        media_avatar_base_url="https://cdn.example.invalid",
        dry_run=True,
    )
    importers.run_homepage_importer(
        release=release,
        env="gamma",
        run=run,
        run_id="apply-a",
        mongo_uri="mongodb://gamma",
        media_image_base_url="https://cdn.example.invalid",
        dry_run=True,
        mode=ImportMode.UPSERT,
    )

    assert len(commands) == 4
    assert "--creator-receipt" in commands[1]
    assert "--redis-addr" not in commands[1]
    assert "--redis-db" not in commands[1]
    assert commands[1][commands[1].index("--media-avatar-base-url") + 1] == (
        "https://cdn.example.invalid"
    )
    assert commands[3][commands[3].index("--run-id") + 1] == "apply-a"
    for command in commands:
        assert "--publish-root" not in command
        release_index = command.index("--release-root")
        assert command[release_index + 1] == str(release)
        assert "--media-base-url" not in command
    assert commands[0][commands[0].index("--release-id") + 1] == "release-a"
    assert commands[1][commands[1].index("--media-image-base-url") + 1] == (
        "https://cdn.example.invalid"
    )
    assert commands[1][commands[1].index("--media-video-base-url") + 1] == (
        "https://cdn.example.invalid"
    )
    assert commands[2][commands[2].index("--media-avatar-base-url") + 1] == (
        "https://cdn.example.invalid"
    )
    assert commands[2][commands[2].index("--run-id") + 1] == "apply-a"
    assert commands[3][commands[3].index("--media-image-base-url") + 1] == (
        "https://cdn.example.invalid"
    )


def test_media_sync_reads_only_immutable_release_payload(tmp_path: Path) -> None:
    release = tmp_path / "releases/release-a"
    run = tmp_path / "runs/apply-a"
    destination = tmp_path / "environment-media"
    content = b"release-owned-media"
    digest = hashlib.sha256(content).hexdigest()
    public_slice_key = "media/image/s/asset/release-image/v1/source.webp"
    source = release / "payload" / public_slice_key
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    header = release / "payload/release.json"
    header.write_text(
        json.dumps({"releaseId": "release-a", "releaseClass": "commercial"}),
        encoding="utf-8",
    )
    manifest = release / "payload/media_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.release_media_manifest",
                "releaseId": "release-a",
                "assets": [
                    {
                        "assetId": "release-image",
                        "publicSliceKey": public_slice_key,
                        "sha256": f"sha256:{digest}",
                        "bytes": len(content),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    _sync_media(release=release, destination=str(destination), run=run)

    assert (destination / public_slice_key).read_bytes() == content
    report = json.loads((run / "media-sync.json").read_text(encoding="utf-8"))
    assert report["copied"] == 1
    assert report["failed"] == 0
