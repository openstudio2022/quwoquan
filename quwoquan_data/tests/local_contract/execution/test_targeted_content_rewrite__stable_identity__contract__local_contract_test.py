from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from core.control_types import TargetSelector
from content.execution.request import RuntimeExecutionRequest
from content.execution.planning.rewrite import (
    RewriteBinding,
    apply_rewrite_identity,
    resolve_rewrite_binding,
    resolve_rewrite_from_args,
    rewrite_target_rows,
)
from support.capacity_calibration_fixture import synthetic_capacity_source_binding


PREDECESSOR = "20260809--travel-article-m1--china-rewrite-source--scale-001"
CONTENT_ID = "qwq_data_stable_content_001"
DIGEST = "sha256:" + "a" * 64


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _source_object(publish_root: Path, *, version: int = 3) -> None:
    object_root = publish_root / "posts/article/攻略/测试景区攻略" / str(version)
    _write_json(
        object_root / "manifest.json",
        {
            "contentId": CONTENT_ID,
            "version": version,
            "contentType": "article",
            "topicId": "测试景区",
            "executionId": PREDECESSOR,
            "variantPurpose": "original",
            "authorId": "builtin_travel_blogger",
            "entityRefs": ["/entity/地点/景区/测试景区"],
            "tagRefs": ["Topic/旅行/玩法/观光游览"],
            "assets": [{"assetId": "cover", "sha256": DIGEST}],
        },
    )
    _write_json(
        object_root / "_pool/versions" / f"{version}.json",
        {
            "schema": "quwoquan_data.pool_object_record",
            "objectType": "content",
            "objectId": CONTENT_ID,
            "objectRef": f"article/攻略/测试景区攻略/{version}",
            "version": version,
            "processResult": "completed",
            "qualityResult": "passed",
            "eligibilityResult": "passed",
            "usageScope": "research",
            "status": "active",
            "evidenceRef": "attestation.json",
            "evidenceDigest": DIGEST,
            "payloadDigest": DIGEST,
        },
    )


def test_rewrite_binding_freezes_exact_current_version_and_target(tmp_path: Path) -> None:
    publish_root = tmp_path / "publish"
    _source_object(publish_root)

    binding = resolve_rewrite_binding(
        content_id=CONTENT_ID,
        expected_version=3,
        reason="quality",
        retry_of=PREDECESSOR,
        content_type="article",
        publish_root=publish_root,
    )

    assert binding.to_document() == {
        "contentId": CONTENT_ID,
        "expectedVersion": 3,
        "nextVersion": 4,
        "reason": "quality",
        "sourceObjectRef": "article/攻略/测试景区攻略/3",
        "sourceTaskId": PREDECESSOR,
        "sourcePayloadDigest": DIGEST,
        "targetName": "测试景区",
        "contentType": "article",
        "variantPurpose": "original",
    }


def test_rewrite_binding_rejects_stale_expected_version(tmp_path: Path) -> None:
    publish_root = tmp_path / "publish"
    _source_object(publish_root, version=4)

    with pytest.raises(ValueError, match="DATA.POOL.VERSION_CONFLICT"):
        resolve_rewrite_binding(
            content_id=CONTENT_ID,
            expected_version=3,
            reason="metadata",
            retry_of=PREDECESSOR,
            content_type="article",
            publish_root=publish_root,
        )


def test_rewrite_request_round_trip_uses_existing_request_track() -> None:
    rewrite = RewriteBinding(
        content_id=CONTENT_ID,
        expected_version=3,
        next_version=4,
        reason="rights",
        source_object_ref="article/攻略/测试景区攻略/3",
        source_task_id=PREDECESSOR,
        source_payload_digest=DIGEST,
        target_name="测试景区",
        content_type="article",
        variant_purpose="original",
    )
    request = RuntimeExecutionRequest(
        family_ref="control_plane/families/travel/article/example.yaml",
        region_ref="china",
        selector=TargetSelector.ALL,
        count=1,
        quota=1,
        capacity_calibration=synthetic_capacity_source_binding(),
        topic="测试景区攻略",
        source_providers=(),
        target_names=("测试景区",),
        rewrite=rewrite.to_document(),
    )

    assert RuntimeExecutionRequest.from_document(request.to_document()) == request
    assert request.to_document()["rewrite"] == rewrite.to_document()


def test_rewrite_identity_is_stable_and_cannot_touch_another_object() -> None:
    binding = RewriteBinding(
        content_id=CONTENT_ID,
        expected_version=3,
        next_version=4,
        reason="duplicate",
        source_object_ref="article/攻略/测试景区攻略/3",
        source_task_id=PREDECESSOR,
        source_payload_digest=DIGEST,
        target_name="测试景区",
        content_type="article",
        variant_purpose="original",
    )
    manifest = {
        "contentType": "article",
        "topicId": "测试景区",
        "authorId": "builtin_travel_blogger",
        "entityRefs": ["/entity/地点/景区/测试景区"],
        "tagRefs": ["Topic/旅行/玩法/观光游览"],
        "assets": [{"assetId": "cover"}],
    }

    rewritten = apply_rewrite_identity(manifest, ref="测试景区", binding=binding)
    assert rewritten["contentId"] == CONTENT_ID
    assert rewritten["version"] == 4
    assert rewritten["variantPurpose"] == "original"
    assert rewritten["sourceType"] == "data"
    assert rewritten["status"] == "active"

    with pytest.raises(ValueError, match="only target object"):
        apply_rewrite_identity(manifest, ref="另一个景区", binding=binding)


def test_task_execute_parser_exposes_complete_rewrite_triad() -> None:
    from content.execution.planning.recipe.parser import register_recipe_parser

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    register_recipe_parser(sub, handler=lambda _args: None)
    args = parser.parse_args(
        [
            "execute",
            "--execution-id",
            "next",
            "--rewrite-content-id",
            CONTENT_ID,
            "--expected-version",
            "3",
            "--rewrite-reason",
            "rights",
        ]
    )
    assert args.rewrite_content_id == CONTENT_ID
    assert args.expected_version == 3
    assert args.rewrite_reason == "rights"


def test_rewrite_cli_requires_the_three_user_facing_facts(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="must be provided together"):
        resolve_rewrite_from_args(
            argparse.Namespace(
                rewrite_content_id=CONTENT_ID,
                expected_version=None,
                rewrite_reason=None,
            ),
            publish_root=tmp_path,
        )


def test_rewrite_selects_only_one_predecessor_target() -> None:
    binding = RewriteBinding(
        content_id=CONTENT_ID,
        expected_version=3,
        next_version=4,
        reason="metadata",
        source_object_ref="article/攻略/测试景区攻略/3",
        source_task_id=PREDECESSOR,
        source_payload_digest=DIGEST,
        target_name="测试景区",
        content_type="article",
        variant_purpose="original",
    )
    rows = rewrite_target_rows(
        binding,
        retry_of=PREDECESSOR,
        load_frozen_target_set=lambda _execution_id: {
            "targets": [
                {"name": "另一个景区", "entityType": "地点/景区"},
                {"name": "测试景区", "entityType": "地点/景区"},
            ]
        },
    )
    assert rows == ({"name": "测试景区", "entityType": "地点/景区"},)
