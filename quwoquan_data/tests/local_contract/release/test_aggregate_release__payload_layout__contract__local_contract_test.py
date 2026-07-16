"""Aggregate homepage releases use one immutable payload tree."""
from __future__ import annotations

import json
import hashlib
import sys
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.release_layout import payload_digest, payload_file  # noqa: E402
from content.release.canonical import handler  # noqa: E402
from content.release.canonical.object_transaction import build_aggregate_release  # noqa: E402


EXECUTION_ID = "20260713--travel-homepage-coverage--cn-zhejiang--canary-901"
RELEASE_ID = "20260713--travel-homepage-coverage--cn-zhejiang--canary-901"
TAG_REF = "Topic/旅行"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_cas(publish_root: Path, payload: bytes) -> tuple[str, dict[str, object]]:
    digest = hashlib.sha256(payload).hexdigest()
    object_key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.jpg"
    path = publish_root / object_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return object_key, {"objectKey": object_key, "sha256": f"sha256:{digest}"}


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, str, str]:
    publish_root = tmp_path / "publish"
    execution_root = tmp_path / EXECUTION_ID
    release_root = tmp_path / "releases"
    _write_json(execution_root / "execution_manifest.json", {"executionId": EXECUTION_ID})
    _write_json(
        execution_root / "entities/地点/景区/普陀山/5.review/attestation.json",
        {
            "decision": "approved",
            "objectRef": "/entity/地点/景区/普陀山",
            "independentReviewer": {"status": "passed"},
        },
    )
    selected_key, selected_asset = _write_cas(publish_root, b"putuo-release-asset")
    unrelated_key, unrelated_asset = _write_cas(publish_root, b"unrelated-canonical-asset")
    _write_json(publish_root / "entities/地点/景区/普陀山/manifest.json", {"assets": []})
    _write_json(
        publish_root / "entities/地点/景区/普陀山/tag.refs.json",
        {"tagRefs": [TAG_REF]},
    )
    _write_json(
        publish_root / "tags/Topic/旅行/_definition.json",
        {
            "label": "旅行",
            "labelEn": "travel",
            "createdAt": "2026-07-13T00:00:00Z",
            "updatedAt": "2026-07-13T00:00:00Z",
        },
    )
    _write_json(
        publish_root / "entities/地点/景区/普陀山/asset.refs.json",
        {"assets": [selected_asset]},
    )
    _write_json(publish_root / "entities/地点/景区/其他/manifest.json", {"assets": []})
    _write_json(
        publish_root / "entities/地点/景区/其他/tag.refs.json",
        {"tagRefs": [TAG_REF]},
    )
    _write_json(
        publish_root / "entities/地点/景区/其他/asset.refs.json",
        {"assets": [unrelated_asset]},
    )
    return publish_root, execution_root, release_root, selected_key, unrelated_key


def test_aggregate_release__payload_layout__contract__local_contract(tmp_path: Path) -> None:
    publish_root, execution_root, release_root, selected_key, unrelated_key = _fixture(tmp_path)

    result = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=RELEASE_ID,
        execution_roots=[execution_root],
        rollout_milestone="canary",
    )

    release = release_root / RELEASE_ID
    assert result["idempotent"] is False
    assert payload_file(release, "release.json").is_file()
    assert payload_file(release, "desired_state.json").is_file()
    assert payload_file(release, "objects/entities/地点/景区/普陀山/manifest.json").is_file()
    assert payload_file(release, "objects/tags/Topic/旅行/_definition.json").is_file()
    desired = json.loads(payload_file(release, "desired_state.json").read_text(encoding="utf-8"))
    assert desired["desiredRefs"]["tags"] == [TAG_REF]
    media = json.loads(payload_file(release, "media_manifest.json").read_text(encoding="utf-8"))
    assert [item["objectKey"] for item in media["assets"]] == [selected_key]
    assert unrelated_key not in {item["objectKey"] for item in media["assets"]}
    aggregate = json.loads((release / "attestations/aggregate.json").read_text(encoding="utf-8"))
    assert aggregate["payloadSha256"] == payload_digest(release)
    assert aggregate["rolloutMilestone"] == "canary"
    header = json.loads(payload_file(release, "release.json").read_text(encoding="utf-8"))
    assert header["rolloutMilestone"] == "canary"
    assert not (release / "release.json").exists()
    assert not (release / "desired_state.json").exists()

    rerun = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=RELEASE_ID,
        execution_roots=[execution_root],
        rollout_milestone="canary",
    )
    assert rerun["idempotent"] is True


def test_release_aggregate_handler__execution_ids__contract__local_contract(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    execution_ids = [
        "20260715--travel-homepage-coverage--cn-zhejiang--canary-001",
        "20260715--travel-homepage-coverage--cn-sichuan--canary-001",
    ]
    captured: dict[str, object] = {}

    monkeypatch.setattr(handler, "execution_root", lambda execution_id: tmp_path / "tasks" / execution_id)

    def _build(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"releaseId": RELEASE_ID, "idempotent": False}

    monkeypatch.setattr(handler, "build_aggregate_release", _build)
    handler.handle_aggregate_release(
        Namespace(
            execution_ids=",".join(execution_ids),
            publish_root=str(tmp_path / "publish"),
            release_root=str(tmp_path / "releases"),
            release_id=RELEASE_ID,
            rollout_milestone="canary",
        )
    )

    assert captured["execution_roots"] == [tmp_path / "tasks" / item for item in execution_ids]
    assert captured["rollout_milestone"] == "canary"
    assert json.loads(capsys.readouterr().out)["releaseId"] == RELEASE_ID
