# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001.t3
"""场景组：aggregate release 多载体对象闭包（article/image/video 全链路）。

Aggregate homepage releases use one immutable payload tree.

从 test_aggregate_release__payload_layout__contract__local_contract_test.py
按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from content.release.canonical import integrity
from content.release.canonical.aggregate_release import (
    build_aggregate_release,
    build_pool_release,
)
from content.release.canonical.content_pool_record import (
    append_pool_record,
    build_canonical_pool_record,
)
from content.release.canonical.object_source_identity import (
    source_identity_digest,
    source_identity_set,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core import paths as core_paths
from core.content_library import resolve_media_holding
from core.release_layout import payload_file
from core.source_digest import (
    content_source_revision,
    current_source_definition_snapshot,
)
from tests.support.release_admission_fixture import (
    article_render_profile,
    bind_publishable_video_review,
)

from support.aggregate_release_payload_fixture import (
    ENTITY_CATALOG_DIGEST,
    _release_source_identity,
    _research_rights,
    _source_attribution,
    _admit_media,
    _use_release_test_output,
    _write_avatar_rights_snapshot,
    _write_json,
    _write_rights_snapshot,
)


def _commercial_rights(asset: dict[str, object]) -> dict[str, object]:
    rights = _research_rights(asset)
    rights.update(
        {
            "license": "CC BY 4.0",
            "licenseUrl": "https://creativecommons.org/licenses/by/4.0",
            "authorizationProof": "https://rights.example/authorization",
            "rightsAuditStatus": "verified",
            "rightsAuditIssues": [],
        }
    )
    return rights


def _commercial_source_attribution(content_type: str) -> dict[str, object]:
    attribution = _source_attribution(content_type)
    attribution.update(
        {
            "rightsBasis": "CC BY 4.0",
            "commercialAuthorizationStatus": "verified",
            "publicationAdmission": "commercial_release",
            "authorizationProofUrl": "https://rights.example/authorization",
            "termsUrl": "https://creativecommons.org/licenses/by/4.0",
        }
    )
    return attribution


def test_release__multi_carrier_object_closure__contract__local_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    publish_root = tmp_path / "publish"
    release_root = tmp_path / "releases"
    entity_ref = "地点/景区/测试实体甲"
    creator_ref = "test_creator_a"
    for relative in ("creators", "entities", "posts", "tags"):
        (publish_root / relative).mkdir(parents=True, exist_ok=True)
    entity_root = publish_root / "entities" / entity_ref
    _entity_key, entity_asset = _admit_media(b"entity-homepage-hero")
    entity_asset["role"] = "cover"
    _write_json(
        entity_root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_manifest",
            "entityId": entity_ref,
            "version": 1,
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": "commercial",
                "evidenceRef": "homepage-admission.json",
                "evidenceDigest": "sha256:" + "c" * 64,
            },
            "status": "active",
            "finalContentRef": "page.md",
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
            "assets": [entity_asset],
        },
    )
    (entity_root / "page.md").write_text("# test entity\n", encoding="utf-8")
    _write_json(entity_root / "source_catalog.json", {"sources": []})
    _write_json(
        entity_root / "rights.json",
        {"assets": [_commercial_rights(entity_asset)]},
    )
    _write_json(entity_root / "creator.refs.json", {"creatorRefs": [creator_ref]})
    _write_json(entity_root / "tag.refs.json", {"tagRefs": []})
    _write_json(entity_root / "asset.refs.json", {"assets": [entity_asset]})
    _write_rights_snapshot(entity_root, entity_asset)
    creator_root = publish_root / "creators" / creator_ref
    _avatar_key, avatar_asset = _admit_media(b"creator-avatar")
    avatar_asset["kind"] = "avatar"
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
    _write_json(
        creator_root / "profile.json",
        {
            "authorId": creator_ref,
            "userId": creator_ref,
            "version": 1,
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "author-admission.json",
                "evidenceDigest": "sha256:" + "a" * 64,
            },
            "status": "active",
            "avatarAsset": {
                "assetId": avatar_asset["assetId"],
                "kind": "avatar",
                "sha256": avatar_asset["sha256"],
            },
        },
    )
    avatar_asset["bytes"] = resolve_media_holding(
        str(avatar_asset["sha256"])
    ).stat().st_size
    _write_json(creator_root / "assets.refs.json", {"assets": [avatar_asset]})
    _write_avatar_rights_snapshot(creator_root, avatar_asset)
    (creator_root / "works.refs.ndjson").write_text("", encoding="utf-8")

    executions: list[str] = []
    frozen_source_digest = current_source_definition_snapshot().to_document()

    def add_execution(
        execution_id: str,
        *,
        entities: list[str],
        posts: list[str],
        source_digest: dict[str, object] | None = None,
        record_execution: bool = True,
    ) -> None:
        source_digest = source_digest or frozen_source_digest
        for kind, refs in (("entities", entities), ("posts", posts)):
            for ref in refs:
                manifest_path = publish_root / kind / ref / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["executionId"] = execution_id
                manifest["sourceDigest"] = source_digest
                source_identity = {
                    "executionId": execution_id,
                    "sourceRevision": content_source_revision(
                        source_digest=str(source_digest["digest"]),
                        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
                    ),
                    "sourceDigest": str(source_digest["digest"]),
                    "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
                }
                manifest["sourceIdentity"] = {
                    **source_identity,
                    "identityDigest": source_identity_digest(source_identity),
                }
                if kind == "entities":
                    manifest["sourceAttribution"] = (
                        _commercial_source_attribution("homepage")
                        if manifest.get("admission", {}).get("usageScope")
                        == "commercial"
                        else _source_attribution("homepage")
                    )
                admission = manifest.get("admission")
                if isinstance(admission, dict):
                    evidence_path = manifest_path.parent / str(
                        admission["evidenceRef"]
                    )
                    if not evidence_path.is_file():
                        _write_json(
                            evidence_path,
                            {
                                "schema": "quwoquan_data.test_release_admission_evidence",
                                "executionId": execution_id,
                                "result": "passed",
                            },
                        )
                    admission["evidenceDigest"] = (
                        "sha256:"
                        + hashlib.sha256(evidence_path.read_bytes()).hexdigest()
                    )
                _write_json(manifest_path, manifest)
                if kind in {"entities", "posts"}:
                    append_pool_record(
                        object_root=manifest_path.parent,
                        record=build_canonical_pool_record(
                            object_root=manifest_path.parent,
                            object_type=(
                                "homepage" if kind == "entities" else "content"
                            ),
                            object_ref=ref,
                        ),
                    )
        if record_execution:
            executions.append(execution_id)

    add_execution(
        "20260718--travel-homepage-coverage--test-region-a--scale-901",
        entities=[entity_ref],
        posts=[],
    )
    alternate_source_digest = {**frozen_source_digest}
    alternate_source_digest["digest"] = "sha256:" + "c" * 64
    for content_type, suffix in (("article", "guide"), ("image", "gallery"), ("video", "short")):
        post_ref = f"{content_type}/测试实体甲/{suffix}"
        post_root = publish_root / "posts" / post_ref
        object_keys: list[str] = []
        if content_type == "article":
            cover_key, cover = _admit_media(b"article-cover")
            body_key, body = _admit_media(b"article-body")
            article_source_ref = "sources/article-source-unit/source.md"
            cover.update(
                role="cover",
                sourceRef=article_source_ref,
            )
            body.update(
                role="embedded",
                sourceRef=article_source_ref,
            )
            assets = [cover, body]
            object_keys.extend((cover_key, body_key))
        elif content_type == "video":
            video_key, video = _admit_media(
                b"video-asset",
                suffix=".mp4",
                kind="video",
                mime_type="video/mp4",
            )
            poster_key, poster = _admit_media(b"video-poster")
            poster["role"] = "cover"
            video["posterAssetId"] = poster["assetId"]
            assets = [video, poster]
            object_keys.extend((video_key, poster_key))
        else:
            image_key, image = _admit_media(b"image-asset")
            image["role"] = "cover"
            assets = [image]
            object_keys.append(image_key)
        _write_json(
            post_root / "manifest.json",
            {
                "schema": "quwoquan_data.post_manifest",
                "contentIdentity": "work",
                "vertical": "travel",
                "contentType": content_type,
                "contentId": f"content-{content_type}",
                "version": 1,
                "sourceType": "data",
                "creatorProfileId": creator_ref,
                "authorId": creator_ref,
                "reviewDecision": "approved",
                "entityRefs": [f"/entity/{entity_ref}"],
                "sourceAttribution": (
                    _commercial_source_attribution(content_type)
                    if content_type in {"image", "video"}
                    else _source_attribution(content_type)
                ),
                "variantPurpose": "original",
                "admission": {
                    "processResult": "completed",
                    "qualityResult": "passed",
                    "usageScope": (
                        "commercial"
                        if content_type in {"image", "video"}
                        else "research"
                    ),
                    "evidenceRef": "attestation.json",
                    "evidenceDigest": "sha256:" + "b" * 64,
                },
                "status": "active",
                "finalContentRef": "content.md",
                "sourceCatalogRef": "source_catalog.json",
                "rightsRef": "rights.json",
                "creatorRefsRef": "creator.refs.json",
                "tagRefsRef": "tag.refs.json",
                "assetRefsRef": "asset.refs.json",
                "assets": assets,
                **(
                    {
                        "publishMediaMode": "same_source_illustrated",
                        "articleRenderProfile": article_render_profile(
                            mode="illustrated",
                            source_ref=article_source_ref,
                            cover_asset_id=str(assets[0]["assetId"]),
                            body_asset_ids=[str(assets[1]["assetId"])],
                        ),
                        "imageBindings": [
                            {"assetId": str(asset["assetId"])} for asset in assets
                        ],
                    }
                    if content_type == "article"
                    else {}
                ),
            },
        )
        (post_root / "content.md").write_text(f"# {content_type}\n", encoding="utf-8")
        _write_json(post_root / "source_catalog.json", {"sources": []})
        _write_json(
            post_root / "rights.json",
            {
                "assets": [
                    (
                        _commercial_rights(asset)
                        if content_type == "image"
                        else _research_rights(asset)
                    )
                    for asset in assets
                ]
            },
        )
        if content_type == "video":
            video_asset = next(
                asset for asset in assets if asset.get("kind") == "video"
            )
            bind_publishable_video_review(
                object_root=post_root,
                output_root=core_paths.OUTPUT_ROOT,
                asset_id=str(video_asset["assetId"]),
                content_sha256=str(video_asset["sha256"]),
                object_ref=post_ref,
                source_digest=str(frozen_source_digest["digest"]),
                entity_catalog_digest=ENTITY_CATALOG_DIGEST,
            )
        _write_json(post_root / "creator.refs.json", {"creatorRefs": [creator_ref]})
        _write_json(post_root / "tag.refs.json", {"tagRefs": []})
        _write_json(post_root / "asset.refs.json", {"assets": assets})
        for asset in assets:
            _write_rights_snapshot(post_root, asset)
        add_execution(
            f"20260718--travel-{content_type}-supply--test-region-a--scale-90{len(executions) + 1}",
            entities=[],
            posts=[post_ref],
        )
        # Publish records the reference and the library owns the body, so what
        # every object key has to prove is that the holding is reachable — not
        # that a file sits under the versioned tree.
        for object_key in object_keys:
            assert not (publish_root / object_key).exists()
        for asset in assets:
            assert resolve_media_holding(str(asset["sha256"])).is_file()

    result = build_aggregate_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-multi-carrier--test-release-b--001",
        execution_ids=executions,
        release_class="research",
        target_environment="alpha",
        **_release_source_identity(str(frozen_source_digest["digest"])),
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
    assert release_header["sourceOwner"] == "qwq_data"
    assert release_header["sourceDigests"] == [frozen_source_digest]
    assert release_header["targetEnvironment"] == "alpha"
    assert release_header["releaseMode"] == "research"
    assert release_header["counts"] == {
        "article": 1,
        "image": 1,
        "video": 1,
        "total": 3,
    }
    assert result["poolEligibleCount"] == 3
    monkeypatch.setattr(integrity.paths, "PUBLISH_ROOT", publish_root)
    integrity_report = integrity._release_integrity(result["releaseId"], release)
    stats = integrity_report["stats"]
    assert stats["postCount"] == 3
    assert stats["articleCount"] == 1
    assert stats["imageCount"] == 1
    assert stats["videoCount"] == 1
    assert (
        stats["articleCount"] + stats["imageCount"] + stats["videoCount"]
        == stats["postCount"]
    )

    article_manifest_path = (
        publish_root / "posts/article/测试实体甲/guide/manifest.json"
    )
    article_manifest = json.loads(article_manifest_path.read_text(encoding="utf-8"))
    original_article_manifest = json.loads(json.dumps(article_manifest))
    article_manifest["sourceDigest"] = alternate_source_digest
    _write_json(article_manifest_path, article_manifest)
    with pytest.raises(ObjectTransactionError, match="one frozen sourceDigest"):
        build_aggregate_release(
            publish_root=publish_root,
            release_root=release_root,
            release_id="20260718--travel-multi-carrier--mixed-source--001",
            execution_ids=executions,
            release_class="research",
            **_release_source_identity(str(frozen_source_digest["digest"])),
        )
    article_manifest = original_article_manifest
    _write_json(article_manifest_path, article_manifest)

    standalone_entity_ref = "地点/景区/独立实体乙"
    standalone_execution = (
        "20260718--travel-homepage-coverage--test-region-b--scale-902"
    )
    standalone_root = publish_root / "entities" / standalone_entity_ref
    _standalone_key, standalone_asset = _admit_media(
        b"standalone-entity-homepage-hero"
    )
    standalone_asset["role"] = "cover"
    _write_json(
        standalone_root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_manifest",
            "entityId": standalone_entity_ref,
            "version": 1,
            "executionId": standalone_execution,
            "sourceDigest": frozen_source_digest,
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "usageScope": "research",
                "evidenceRef": "homepage-admission.json",
                "evidenceDigest": "sha256:" + "d" * 64,
            },
            "status": "active",
            "finalContentRef": "page.md",
            "sourceCatalogRef": "source_catalog.json",
            "rightsRef": "rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
            "assets": [standalone_asset],
        },
    )
    (standalone_root / "page.md").write_text("# standalone entity\n", encoding="utf-8")
    _write_json(standalone_root / "source_catalog.json", {"sources": []})
    _write_json(
        standalone_root / "rights.json",
        {"assets": [_research_rights(standalone_asset)]},
    )
    _write_json(
        standalone_root / "creator.refs.json", {"creatorRefs": [creator_ref]}
    )
    _write_json(standalone_root / "tag.refs.json", {"tagRefs": []})
    _write_json(standalone_root / "asset.refs.json", {"assets": [standalone_asset]})
    _write_rights_snapshot(standalone_root, standalone_asset)
    add_execution(
        standalone_execution,
        entities=[standalone_entity_ref],
        posts=[],
        source_digest=alternate_source_digest,
        record_execution=False,
    )

    independent_creator_ref = "test_creator_independent"
    independent_tag_ref = "Topic/旅行/独立作者"
    independent_creator_root = publish_root / "creators" / independent_creator_ref
    _write_json(
        independent_creator_root / "_creator.json",
        {
            "schema": "quwoquan_data.creator_object",
            "creatorId": independent_creator_ref,
            "profileRef": "profile.json",
            "assetsRef": "assets.refs.json",
            "worksRefsRef": "works.refs.ndjson",
            "tagRefs": [independent_tag_ref],
            "entityRefs": [],
        },
    )
    _write_json(
        independent_creator_root / "profile.json",
        {
            "authorId": independent_creator_ref,
            "userId": independent_creator_ref,
            "version": 1,
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "author-admission.json",
                "evidenceDigest": "sha256:" + "e" * 64,
            },
            "status": "active",
        },
    )
    _write_json(independent_creator_root / "assets.refs.json", {"assets": []})
    (independent_creator_root / "works.refs.ndjson").write_text(
        "", encoding="utf-8"
    )
    _write_json(
        publish_root / "tags" / independent_tag_ref / "_definition.json",
        {"label": "独立作者", "labelEn": "independent-author"},
    )

    pool_result = build_pool_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-pool-alpha--001",
        target_environment="alpha",
        release_class="research",
    )
    assert pool_result["postCount"] == 3
    assert pool_result["entityCount"] == 2
    assert pool_result["counts"] == {
        "article": 1,
        "image": 1,
        "video": 1,
        "total": 3,
    }
    assert pool_result["targetEnvironment"] == "alpha"
    pool_header = json.loads(
        payload_file(
            release_root / pool_result["releaseId"],
            "release.json",
        ).read_text(encoding="utf-8")
    )
    assert pool_header["poolDigest"] == pool_result["poolDigest"]
    assert pool_header["executionIds"] == sorted([*executions, standalone_execution])
    expected_source_identities, expected_source_identity_set_digest = (
        source_identity_set(
            [
                {
                    "executionId": execution_id,
                    "sourceRevision": content_source_revision(
                        source_digest=str(frozen_source_digest["digest"]),
                        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
                    ),
                    "sourceDigest": str(frozen_source_digest["digest"]),
                    "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
                }
                for execution_id in executions
            ]
            + [
                {
                    "executionId": standalone_execution,
                    "sourceRevision": content_source_revision(
                        source_digest=str(alternate_source_digest["digest"]),
                        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
                    ),
                    "sourceDigest": str(alternate_source_digest["digest"]),
                    "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
                }
            ]
        )
    )
    assert pool_header["sourceIdentities"] == expected_source_identities
    assert (
        pool_header["sourceIdentitySetDigest"]
        == expected_source_identity_set_digest
    )
    assert {
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
    }.isdisjoint(pool_header)
    pool_attestation = json.loads(
        (
            release_root
            / pool_result["releaseId"]
            / "attestations/release.json"
        ).read_text(encoding="utf-8")
    )
    assert {
        "sourceIdentities",
        "sourceIdentitySetDigest",
    }.issubset(pool_attestation)
    assert pool_attestation["sourceIdentities"] == expected_source_identities
    assert (
        pool_attestation["sourceIdentitySetDigest"]
        == expected_source_identity_set_digest
    )
    assert {
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
    }.isdisjoint(pool_attestation)
    assert pool_header["authors"] == [
        {"authorId": creator_ref, "version": 1, "creatorRef": creator_ref},
        {
            "authorId": independent_creator_ref,
            "version": 1,
            "creatorRef": independent_creator_ref,
        },
    ]
    pool_desired = json.loads(
        payload_file(
            release_root / pool_result["releaseId"],
            "desired_state.json",
        ).read_text(encoding="utf-8")
    )
    assert pool_desired["desiredRefs"]["tags"] == [independent_tag_ref]
    assert {
        (item["contentId"], item["version"], item["postRef"])
        for item in pool_header["contents"]
    } == {
        (
            f"content-{ref.split('/', 1)[0]}",
            1,
            ref,
        )
        for ref in (
            "article/测试实体甲/guide",
            "image/测试实体甲/gallery",
            "video/测试实体甲/short",
        )
    }
    assert build_pool_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=pool_result["releaseId"],
        target_environment="alpha",
        release_class="research",
    )["idempotent"] is True

    commercial_result = build_pool_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-pool-alpha-commercial--001",
        target_environment="alpha",
        release_class="commercial",
    )
    assert commercial_result["postCount"] == 1
    assert commercial_result["entityCount"] == 1
    assert commercial_result["creatorCount"] == 1
    assert commercial_result["counts"] == {
        "article": 0,
        "image": 1,
        "video": 0,
        "total": 1,
    }
    assert commercial_result["poolDigest"] == pool_result["poolDigest"]
    assert {
        row["code"] for row in commercial_result["excluded"]
    } == {"DATA.POOL.COMMERCIAL_RIGHTS_REQUIRED"}
    assert {
        row["category"] for row in commercial_result["excluded"]
    } == {"eligibility"}
    assert any(
        row["postRef"] == "video/测试实体甲/short"
        and row["code"] == "DATA.POOL.COMMERCIAL_RIGHTS_REQUIRED"
        for row in commercial_result["excluded"]
    )
    commercial_header = json.loads(
        payload_file(
            release_root / commercial_result["releaseId"],
            "release.json",
        ).read_text(encoding="utf-8")
    )
    assert commercial_header["releaseClass"] == "commercial"
    assert commercial_header["productLifecycleState"] == "commercial"
    assert commercial_header["sourceIdentitySetDigest"].startswith("sha256:")
    assert commercial_header["authors"] == [
        {"authorId": creator_ref, "version": 1, "creatorRef": creator_ref}
    ]
    commercial_desired = json.loads(
        payload_file(
            release_root / commercial_result["releaseId"],
            "desired_state.json",
        ).read_text(encoding="utf-8")
    )
    assert commercial_desired["desiredRefs"]["posts"] == [
        "image/测试实体甲/gallery"
    ]
    assert independent_creator_ref not in commercial_desired["desiredRefs"]["creators"]

    invalid_article = json.loads(
        article_manifest_path.read_text(encoding="utf-8")
    )
    invalid_article.pop("mediaClosure", None)
    invalid_article.pop("articleRenderProfile", None)
    _write_json(article_manifest_path, invalid_article)
    media_partial = build_pool_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-pool-alpha-media-partial--001",
        target_environment="alpha",
        release_class="research",
    )
    assert media_partial["postCount"] == 2
    assert media_partial["excludedCount"] == 1
    assert media_partial["excluded"][0]["postRef"] == "article/测试实体甲/guide"
    _write_json(article_manifest_path, article_manifest)

    invalid_manifest_path = (
        publish_root / "posts/video/测试实体甲/short/manifest.json"
    )
    invalid_manifest = json.loads(
        invalid_manifest_path.read_text(encoding="utf-8")
    )
    invalid_manifest["admission"]["qualityResult"] = "failed"
    _write_json(invalid_manifest_path, invalid_manifest)
    append_pool_record(
        object_root=invalid_manifest_path.parent,
        record=build_canonical_pool_record(
            object_root=invalid_manifest_path.parent,
            object_type="content",
            object_ref="video/测试实体甲/short",
        ),
    )
    partial_result = build_pool_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id="20260718--travel-pool-alpha-partial--001",
        target_environment="alpha",
        release_class="research",
    )
    assert partial_result["postCount"] == 2
    assert partial_result["excludedCount"] == 1
    assert partial_result["excluded"] == [
        {
            "postRef": "video/测试实体甲/short",
            "category": "quality",
            "code": "DATA.POOL.QUALITY_FAILED",
            "message": "DATA.POOL.QUALITY_FAILED: postRef=video/测试实体甲/short",
        }
    ]
    partial_header = json.loads(
        payload_file(
            release_root / partial_result["releaseId"],
            "release.json",
        ).read_text(encoding="utf-8")
    )
    assert partial_header["counts"] == {
        "article": 1,
        "image": 1,
        "video": 0,
        "total": 2,
    }
