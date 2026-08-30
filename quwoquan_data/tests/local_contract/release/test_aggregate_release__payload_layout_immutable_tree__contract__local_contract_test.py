"""场景组：aggregate release 不可变 payload 树、幂等防篡改与 handler 推导。

Aggregate homepage releases use one immutable payload tree.

从 test_aggregate_release__payload_layout__contract__local_contract_test.py
按场景拆出（本文件经 git mv 承接原文件历史）；测试逐字搬移。
"""
from __future__ import annotations

import json
import shutil
from argparse import Namespace
from pathlib import Path

import pytest
from content.release.canonical import handler
from content.release.canonical.aggregate_release import build_aggregate_release
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core.release_layout import payload_digest, payload_file

from support.aggregate_release_payload_fixture import (
    ENTITY_CATALOG_DIGEST,
    EXECUTION_ID,
    RELEASE_ID,
    TAG_REF,
    _fixture,
    _release_source_identity,
    _use_release_test_output,
    _write_json,
)


def test_aggregate_release__payload_layout__contract__local_contract(tmp_path: Path) -> None:
    publish_root, execution_root, release_root, selected_key, unrelated_key = _fixture(tmp_path)
    frozen_source_digest = json.loads(
        (
            publish_root / "entities/地点/景区/测试实体甲/manifest.json"
        ).read_text(encoding="utf-8")
    )["sourceDigest"]
    identity = _release_source_identity(str(frozen_source_digest["digest"]))
    shutil.rmtree(execution_root)

    result = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=RELEASE_ID,
        execution_ids=[EXECUTION_ID],
        release_class="research",
        **identity,
    )

    release = release_root / RELEASE_ID
    assert result["idempotent"] is False
    assert payload_file(release, "release.json").is_file()
    assert payload_file(release, "desired_state.json").is_file()
    assert payload_file(release, "objects/entities/地点/景区/测试实体甲/manifest.json").is_file()
    assert payload_file(release, "objects/tags/Topic/旅行/_definition.json").is_file()
    desired = json.loads(payload_file(release, "desired_state.json").read_text(encoding="utf-8"))
    assert desired["desiredRefs"]["tags"] == [TAG_REF]
    media = json.loads(payload_file(release, "media_manifest.json").read_text(encoding="utf-8"))
    assert len(media["assets"]) == 1
    release_asset = media["assets"][0]
    assert "objectKey" not in release_asset
    # DEC-031: research release delivers the CAS body, never a public slice.
    assert "publicSliceKey" not in release_asset
    assert release_asset["privateObjectKey"].startswith("media/objects/sha256/")
    assert payload_file(release, release_asset["privateObjectKey"]).is_file()
    release_objects_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(payload_file(release, "objects").rglob("*.json"))
    )
    assert '"objectKey"' not in release_objects_text
    assert "media/objects/sha256/" not in release_objects_text
    assert unrelated_key != selected_key
    assert all(unrelated_key not in str(item) for item in media["assets"])
    aggregate = json.loads((release / "attestations/release.json").read_text(encoding="utf-8"))
    assert aggregate["payloadSha256"] == payload_digest(release)
    assert aggregate["sourceDigests"] == [frozen_source_digest]
    assert aggregate["sourceDigest"] == frozen_source_digest["digest"]
    assert aggregate["entityCatalogDigest"] == ENTITY_CATALOG_DIGEST
    assert aggregate["sourceRevision"] == identity["source_revision"]
    assert aggregate["postCount"] == 0
    assert aggregate["creatorCount"] == 0
    header = json.loads(payload_file(release, "release.json").read_text(encoding="utf-8"))
    assert header["sourceDigests"] == [frozen_source_digest]
    assert header["sourceDigest"] == frozen_source_digest["digest"]
    assert header["entityCatalogDigest"] == ENTITY_CATALOG_DIGEST
    assert header["sourceRevision"] == identity["source_revision"]
    assert not (release / "release.json").exists()
    assert not (release / "desired_state.json").exists()

    later = publish_root / "entities/地点/景区/后续对象"
    _write_json(later / "manifest.json", {"schema": "quwoquan_data.entity_manifest"})
    _write_json(later / "creator.refs.json", {"creatorRefs": []})
    _write_json(later / "tag.refs.json", {"tagRefs": []})
    _write_json(later / "asset.refs.json", {"assets": []})

    rerun = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=RELEASE_ID,
        execution_ids=[EXECUTION_ID],
        release_class="research",
        **identity,
    )
    assert rerun["idempotent"] is True


def test_existing_release__self_consistent_rights_tamper__rejects_idempotent(
    tmp_path: Path,
) -> None:
    publish_root, execution_root, release_root, _selected_key, _unrelated_key = (
        _fixture(tmp_path)
    )
    frozen_source_digest = json.loads(
        (
            publish_root / "entities/地点/景区/测试实体甲/manifest.json"
        ).read_text(encoding="utf-8")
    )["sourceDigest"]
    identity = _release_source_identity(str(frozen_source_digest["digest"]))
    shutil.rmtree(execution_root)
    build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=RELEASE_ID,
        execution_ids=[EXECUTION_ID],
        release_class="research",
        **identity,
    )

    release = release_root / RELEASE_ID
    header_path = payload_file(release, "release.json")
    attestation_path = release / "attestations/release.json"
    admission = json.loads(
        payload_file(release, "asset_admission.json").read_text(encoding="utf-8")
    )
    assert admission["containsUnverifiedAssets"] is True
    assert admission["rightsStatusCounts"]["unverified"] == 1

    tampered_rights = {
        "verified": 1,
        "unverified": 0,
        "restricted": 0,
        "unknown": 0,
    }
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header.update(
        {
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": tampered_rights,
            "authorizationRequiredAssetIds": [],
            "commercialAcceptedCount": header["researchAcceptedCount"],
        }
    )
    _write_json(header_path, header)
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation.update(
        {
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": tampered_rights,
            "authorizationRequiredAssetIds": [],
            "commercialAcceptedCount": attestation["researchAcceptedCount"],
            "payloadSha256": payload_digest(release),
        }
    )
    _write_json(attestation_path, attestation)
    assert attestation["payloadSha256"] == payload_digest(release)

    with pytest.raises(
        ObjectTransactionError,
        match="aggregate release create-once conflict",
    ):
        build_aggregate_release(
            publish_root=publish_root,
            release_root=release_root,
            release_id=RELEASE_ID,
            execution_ids=[EXECUTION_ID],
            release_class="research",
            **identity,
        )


def test_copy_tag_snapshot__excludes_nested_child_tags__local_contract(tmp_path: Path) -> None:
    from content.release.canonical.aggregate_release_closure import copy_tag_snapshot

    source = tmp_path / "Topic" / "旅行"
    nested = source / "玩法" / "观光游览"
    nested.mkdir(parents=True)
    (source / "_definition.json").write_text('{"label":"旅行"}\n', encoding="utf-8")
    (nested / "_definition.json").write_text('{"label":"观光游览"}\n', encoding="utf-8")
    target = tmp_path / "out" / "Topic" / "旅行"
    copy_tag_snapshot(source, target)
    assert (target / "_definition.json").is_file()
    assert not (target / "玩法" / "观光游览" / "_definition.json").is_file()


def test_release_campaign_aggregate_handler__derives_execution_ids__contract(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    root_execution_id = (
        "20260715--travel-homepage-coverage--test-region-a--pilot-001"
    )
    captured: dict[str, object] = {}

    def _build(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"releaseId": RELEASE_ID, "idempotent": False}

    monkeypatch.setattr(handler, "build_campaign_release", _build)
    monkeypatch.setattr(handler, "PUBLISH_ROOT", tmp_path / "publish")
    handler.handle_campaign_aggregate_release(
        Namespace(
            root_execution_id=root_execution_id,
            output_root=str(tmp_path / "output"),
            release_id=RELEASE_ID,
            release_class="research",
        )
    )

    assert captured["root_execution_id"] == root_execution_id
    assert captured["release_class"] == "research"
    assert "execution_ids" not in captured
    assert json.loads(capsys.readouterr().out)["releaseId"] == RELEASE_ID
