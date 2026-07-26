"""Aggregate homepage releases use one immutable payload tree."""
from __future__ import annotations

import json
import hashlib
import shutil
import sys
from argparse import Namespace
from pathlib import Path



ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.release_layout import payload_digest, payload_file  # noqa: E402
from core.source_digest import current_source_digest  # noqa: E402
from content.release.canonical import handler  # noqa: E402
from content.release.canonical.aggregate_release import build_aggregate_release  # noqa: E402


EXECUTION_ID = "20260713--travel-homepage-coverage--test-region-a--scale-901"
RELEASE_ID = "20260713--travel-homepage-coverage--test-release-a--scale-901"
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
    source_digest = current_source_digest().to_document()
    _write_json(
        execution_root / "execution_manifest.json",
        {
            "executionId": EXECUTION_ID,
            "sourceDigest": source_digest,
        },
    )
    _write_json(
        execution_root / "publish_ref.json",
        {
            "schema": "quwoquan_data.execution_publish_ref",
            "executionId": EXECUTION_ID,
            "canonicalPublishRoot": "quwoquan_data/publish",
            "publishedRefs": {"entities": ["地点/景区/测试实体甲"], "posts": []},
        },
    )
    _write_json(
        execution_root / "entities/地点/景区/测试实体甲/5.review/attestation.json",
        {
            "decision": "approved",
            "objectRef": "/entity/地点/景区/测试实体甲",
            "independentReviewer": {"status": "passed"},
        },
    )
    selected_key, selected_asset = _write_cas(publish_root, b"putuo-release-asset")
    unrelated_key, unrelated_asset = _write_cas(publish_root, b"unrelated-canonical-asset")
    entity_root = publish_root / "entities/地点/景区/测试实体甲"
    _write_json(
        entity_root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_object",
            "executionId": EXECUTION_ID,
            "sourceDigest": source_digest,
            "finalContentRef": "page.md",
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
        },
    )
    (entity_root / "page.md").write_text("# 测试实体甲\n", encoding="utf-8")
    _write_json(entity_root / "source_catalog.json", {"sources": []})
    _write_json(entity_root / "rights.json", {"assets": []})
    _write_json(
        entity_root / "creator.refs.json",
        {"creatorRefs": []},
    )
    _write_json(
        entity_root / "tag.refs.json",
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
        entity_root / "asset.refs.json",
        {"assets": [selected_asset]},
    )
    _write_json(publish_root / "entities/地点/景区/其他/manifest.json", {"assets": []})
    _write_json(
        publish_root / "entities/地点/景区/其他/creator.refs.json",
        {"creatorRefs": []},
    )
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
    shutil.rmtree(execution_root)

    result = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=RELEASE_ID,
        execution_ids=[EXECUTION_ID],
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
    assert [item["objectKey"] for item in media["assets"]] == [selected_key]
    assert payload_file(release, selected_key).is_file()
    assert unrelated_key not in {item["objectKey"] for item in media["assets"]}
    aggregate = json.loads((release / "attestations/release.json").read_text(encoding="utf-8"))
    assert aggregate["payloadSha256"] == payload_digest(release)
    assert aggregate["sourceDigests"] == [current_source_digest().to_document()]
    assert aggregate["postCount"] == 0
    assert aggregate["creatorCount"] == 0
    header = json.loads(payload_file(release, "release.json").read_text(encoding="utf-8"))
    assert header["sourceDigests"] == [current_source_digest().to_document()]
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
    )
    assert rerun["idempotent"] is True


def test_release_aggregate_handler__execution_ids__contract__local_contract(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    execution_ids = [
        "20260715--travel-homepage-coverage--test-region-a--pilot-001",
        "20260715--travel-homepage-coverage--test-region-b--pilot-001",
    ]
    captured: dict[str, object] = {}

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
        )
    )

    assert captured["execution_ids"] == execution_ids
    assert json.loads(capsys.readouterr().out)["releaseId"] == RELEASE_ID


def test_release__multi_carrier_object_closure__contract__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    release_root = tmp_path / "releases"
    entity_ref = "地点/景区/测试实体甲"
    creator_ref = "test_creator_a"
    for relative in ("creators", "entities", "posts", "tags", "media/objects"):
        (publish_root / relative).mkdir(parents=True, exist_ok=True)
    entity_root = publish_root / "entities" / entity_ref
    _write_json(
        entity_root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_manifest",
            "finalContentRef": "page.md",
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
        },
    )
    (entity_root / "page.md").write_text("# test entity\n", encoding="utf-8")
    _write_json(entity_root / "source_catalog.json", {"sources": []})
    _write_json(entity_root / "rights.json", {"assets": []})
    _write_json(entity_root / "creator.refs.json", {"creatorRefs": []})
    _write_json(entity_root / "tag.refs.json", {"tagRefs": []})
    _write_json(entity_root / "asset.refs.json", {"assets": []})
    creator_root = publish_root / "creators" / creator_ref
    _write_json(
        creator_root / "_creator.json",
        {
            "schema": "quwoquan_data.creator_object",
            "creatorId": creator_ref,
            "profileRef": "profile.json",
            "assetsRef": "assets.refs.json",
            "worksRefsRef": "works.refs.ndjson",
            "tagRefs": [],
            "entityRefs": [],
        },
    )
    _write_json(creator_root / "profile.json", {"userId": creator_ref})
    _write_json(creator_root / "assets.refs.json", {"assets": []})
    (creator_root / "works.refs.ndjson").write_text("", encoding="utf-8")

    executions: list[str] = []

    def add_execution(
        execution_id: str,
        *,
        entities: list[str],
        posts: list[str],
        source_digest: dict[str, object] | None = None,
    ) -> None:
        source_digest = source_digest or current_source_digest().to_document()
        for kind, refs in (("entities", entities), ("posts", posts)):
            for ref in refs:
                manifest_path = publish_root / kind / ref / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["executionId"] = execution_id
                manifest["sourceDigest"] = source_digest
                _write_json(manifest_path, manifest)
        executions.append(execution_id)

    add_execution(
        "20260718--travel-homepage-coverage--test-region-a--scale-901",
        entities=[entity_ref],
        posts=[],
    )
    alternate_source_digest = current_source_digest().to_document()
    alternate_source_digest["digest"] = "sha256:" + "c" * 64
    for content_type, suffix in (("article", "guide"), ("image", "gallery"), ("video", "short")):
        post_ref = f"{content_type}/测试实体甲/{suffix}"
        post_root = publish_root / "posts" / post_ref
        object_key, asset = _write_cas(
            publish_root,
            f"{content_type}-asset".encode("utf-8"),
        )
        _write_json(
            post_root / "manifest.json",
            {
                "schema": "quwoquan_data.post_manifest",
                "vertical": "travel",
                "contentType": content_type,
                "creatorProfileId": creator_ref,
                "finalContentRef": "content.md",
                "sourceCatalogRef": "source_catalog.json",
                "rightsRef": "rights.json",
                "creatorRefsRef": "creator.refs.json",
                "tagRefsRef": "tag.refs.json",
                "assetRefsRef": "asset.refs.json",
            },
        )
        (post_root / "content.md").write_text(f"# {content_type}\n", encoding="utf-8")
        _write_json(post_root / "source_catalog.json", {"sources": []})
        _write_json(post_root / "rights.json", {"assets": []})
        _write_json(post_root / "creator.refs.json", {"creatorRefs": [creator_ref]})
        _write_json(post_root / "tag.refs.json", {"tagRefs": []})
        _write_json(post_root / "asset.refs.json", {"assets": [asset]})
        add_execution(
            f"20260718--travel-{content_type}-supply--test-region-a--scale-90{len(executions) + 1}",
            entities=[],
            posts=[post_ref],
            source_digest=(
                alternate_source_digest if content_type == "article" else None
            ),
        )
        assert (publish_root / object_key).is_file()

    result = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-multi-carrier--test-release-b--001",
        execution_ids=executions,
    )

    release = release_root / result["releaseId"]
    desired = json.loads(payload_file(release, "desired_state.json").read_text(encoding="utf-8"))
    assert desired["desiredRefs"] == {
        "creators": [creator_ref],
        "entities": [entity_ref],
        "posts": [
            "article/测试实体甲/guide",
            "image/测试实体甲/gallery",
            "video/测试实体甲/short",
        ],
        "tags": [],
    }
    assert payload_file(release, f"objects/creators/{creator_ref}/_creator.json").is_file()
    assert result["postCount"] == 3
    assert result["creatorCount"] == 1
    release_header = json.loads(payload_file(release, "release.json").read_text(encoding="utf-8"))
    assert release_header["sourceDigests"] == sorted(
        [current_source_digest().to_document(), alternate_source_digest],
        key=lambda item: item["digest"],
    )
