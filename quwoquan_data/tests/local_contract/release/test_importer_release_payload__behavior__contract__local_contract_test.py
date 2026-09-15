"""Service importers consume immutable release object snapshots only."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from content.release.environment import importers
from quwoquan_ops.cli.lib.content_release_environment.handler import _sync_media
from content.release.model import ImportMode
from quwoquan_data.tests.local_contract.release.test_release_header__typed_identity__contract__local_contract_test import _header


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
        lambda _path: {"desiredRefs": {"entities": [], "tags": ["Topic/旅行"]}},
    )

    importers.run_tag_importer(
        release=release,
        env="gamma",
        run=run,
        mongo_uri="mongodb://gamma",
        dry_run=True,
        importer_image_ref="candidate/service-core:test",
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
        creator_candidate_receipt=run / "creator-import.json",
        homepage_import_report=run / "homepage-import.json",
        homepage_candidate_receipt=None,
        importer_image_ref="candidate/service-core:test",
    )
    importers.run_creator_importer(
        release=release,
        env="gamma",
        run=run,
        mongo_uri="mongodb://gamma",
        postgres_dsn="postgres://gamma",
        media_avatar_base_url="https://cdn.example.invalid",
        dry_run=True,
        importer_image_ref="candidate/service-core:test",
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
        importer_image_ref="candidate/service-core:test",
    )

    assert len(commands) == 4
    assert "--creator-receipt" in commands[1]
    assert commands[1][commands[1].index("--homepage-report") + 1] == "/run/quwoquan/import-run/homepage-import.json"
    assert "--homepage-candidate-receipt" not in commands[1]
    assert commands[1].count("--activation-mode") == 1
    assert commands[1][commands[1].index("--activation-mode") + 1] == "stage-only"
    assert not any(flag.startswith("--expected-active-") for flag in commands[1])
    assert "--redis-addr" not in commands[1]
    assert "--redis-db" not in commands[1]
    assert commands[1][commands[1].index("--media-avatar-base-url") + 1] == (
        "https://cdn.example.invalid"
    )
    assert commands[3][commands[3].index("--run-id") + 1] == "apply-a"
    for command in commands:
        assert "--publish-root" not in command
        release_index = command.index("--release-root")
        assert command[release_index + 1] == "/run/quwoquan/release"
        report = command[command.index("--report") + 1]
        assert report.startswith("/run/quwoquan/import-run/")
        assert f"{release}:/run/quwoquan/release:ro" in command
        assert f"{run}:/run/quwoquan/import-run" in command
        assert not any(value == str(release) or value.startswith(str(release) + "/") for value in command[command.index("--entrypoint"):])
        assert not any(value == str(run) or value.startswith(str(run) + "/") for value in command[command.index("--entrypoint"):])
        assert "--media-base-url" not in command
    assert commands[0][commands[0].index("--release-id") + 1] == "release-a"
    assert commands[1][commands[1].index("--media-image-base-url") + 1] == (
        "https://cdn.example.invalid"
    )
    assert commands[1][commands[1].index("--media-video-base-url") + 1] == (
        "https://cdn.example.invalid"
    )
    assert "--database" not in commands[2]
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
        json.dumps(_header(release_id="release-a")),
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


def _content_importer_kwargs(tmp_path: Path) -> dict[str, object]:
    release = tmp_path / "releases/release-a"
    (release / "payload").mkdir(parents=True)
    return {
        "release": release,
        "env": "gamma",
        "run": tmp_path / "runs/apply-a",
        "mongo_uri": "mongodb://gamma",
        "media_avatar_base_url": "https://cdn.example.invalid",
        "media_image_base_url": "https://cdn.example.invalid",
        "media_video_base_url": "https://cdn.example.invalid",
        "dry_run": True,
        "creator_candidate_receipt": tmp_path / "runs/apply-a/creator-candidate-receipt.json",
        "homepage_import_report": tmp_path / "runs/apply-a/homepage-import.json",
        "homepage_candidate_receipt": None,
    }


def test_mutating_content_import_uses_candidate_image_and_only_locator_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    kwargs = _content_importer_kwargs(tmp_path)
    kwargs["dry_run"] = False
    kwargs["homepage_candidate_receipt"] = Path(kwargs["run"]) / "homepage-candidate.json"
    material = tmp_path / "post-safety"
    material.mkdir()
    kwargs.update({
        "post_safety_material_root": material,
        "post_safety_current_binding_ref": "current.json",
        "post_safety_recovery_evidence_ref": "fact.json",
        "post_safety_hmac_secret_ref": "post-safety.key",
        "runtime_auth_env_ref": tmp_path / "auth.env",
        "runtime_auth_issuer": "quwoquan.gamma.local",
        "runtime_auth_audience": "quwoquan-app",
        "runtime_auth_token_version": "1",
        "account_security_authority_base_url": "http://127.0.0.1:19210",
        "account_security_authority_timeout_ms": 300,
        "importer_image_ref": "localhost/service-core@sha256:" + "a" * 64,
    })
    commands: list[list[str]] = []
    monkeypatch.setattr(importers, "_validate_homepage_mapping_input", lambda **_kwargs: None)
    monkeypatch.setattr(importers.subprocess, "run", lambda command, **_kwargs: commands.append(command) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(importers, "assert_import_report_contract", lambda *_args, **_kwargs: {})
    importers.run_content_importer(**kwargs)
    command = commands[0]
    assert command[:3] == ["docker", "run", "--rm"]
    assert "--user" in command
    assert command[command.index("--entrypoint") + 1] == "/usr/local/bin/content-import"
    assert "localhost/service-core@sha256:" + "a" * 64 in command
    assert f"{material}:/run/quwoquan/post-safety:ro" in command
    assert command[command.index("--post-safety-material-root") + 1] == "/run/quwoquan/post-safety"
    assert command[command.index("--post-safety-current-binding-ref") + 1] == "current.json"
    assert command[command.index("--post-safety-recovery-evidence-ref") + 1] == "fact.json"
    assert command[command.index("--post-safety-hmac-secret-ref") + 1] == "post-safety.key"
    assert f"{tmp_path / 'auth.env'}:/run/quwoquan/runtime-auth.env:ro" in command
    assert command[command.index("--runtime-auth-env-ref") + 1] == "/run/quwoquan/runtime-auth.env"
    assert command[command.index("--account-security-authority-base-url") + 1] == "http://127.0.0.1:19210"
    assert not any("secret-bytes" in value for value in command)


def test_mutating_content_import_rejects_missing_post_safety_locator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    kwargs = _content_importer_kwargs(tmp_path)
    kwargs["dry_run"] = False
    kwargs["homepage_candidate_receipt"] = Path(kwargs["run"]) / "homepage-candidate.json"
    monkeypatch.setattr(importers, "_validate_homepage_mapping_input", lambda **_kwargs: None)
    with pytest.raises(RuntimeError, match="canonical Post safety startup locators"):
        importers.run_content_importer(**kwargs)
