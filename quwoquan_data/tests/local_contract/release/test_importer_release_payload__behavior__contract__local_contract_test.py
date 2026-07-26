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
        },
    )
    monkeypatch.setattr(
        importers,
        "read_json",
        lambda _path: {"desiredRefs": {"entities": []}},
    )

    importers.run_content_importer(
        release=release,
        env="gamma",
        run=run,
        mongo_uri="mongodb://gamma",
        media_base_url="https://gamma-image.quwoquan-env.test",
        dry_run=True,
        creator_receipt=run / "creator-import.json",
    )
    importers.run_homepage_importer(
        release=release,
        env="gamma",
        run=run,
        run_id="apply-a",
        mongo_uri="mongodb://gamma",
        media_base_url="https://gamma-image.quwoquan-env.test",
        dry_run=True,
        mode=ImportMode.UPSERT,
    )

    assert len(commands) == 2
    assert "--creator-receipt" in commands[0]
    assert commands[1][commands[1].index("--run-id") + 1] == "apply-a"
    for command in commands:
        assert "--publish-root" not in command
        release_index = command.index("--release-root")
        assert command[release_index + 1] == str(release)
        media_index = command.index("--media-base-url")
        assert command[media_index + 1] == "https://gamma-image.quwoquan-env.test"


def test_media_sync_reads_only_immutable_release_payload(tmp_path: Path) -> None:
    release = tmp_path / "releases/release-a"
    run = tmp_path / "runs/apply-a"
    destination = tmp_path / "environment-media"
    content = b"release-owned-media"
    digest = hashlib.sha256(content).hexdigest()
    object_key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.webp"
    source = release / "payload" / object_key
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    manifest = release / "payload/media_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.release_media_manifest",
                "releaseId": "release-a",
                "assets": [
                    {
                        "objectKey": object_key,
                        "sha256": f"sha256:{digest}",
                        "bytes": len(content),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    _sync_media(release=release, destination=str(destination), run=run)

    assert (destination / object_key).read_bytes() == content
    report = json.loads((run / "media-sync.json").read_text(encoding="utf-8"))
    assert report["copied"] == 1
    assert report["failed"] == 0
