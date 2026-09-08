# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t14
"""accessPolicy 只记录不阻断：publish 事务把资产行的 accessPolicy 转录到 canonical rights 记录，
release admission 与 header 把非 open 的资产汇总为 accessRestrictedAssetIds，且不据此排除任何对象。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.release.canonical import release_admission  # noqa: E402
from content.release.canonical.aggregate_release_documents import release_header_document  # noqa: E402
from core.schema import assert_valid  # noqa: E402
from core.source_digest import SourceDefinitionSnapshot, content_source_revision  # noqa: E402
from governance.coverage.distribution import project_asset_admission  # noqa: E402
from tests.support.post_object_transaction_fixture import (  # noqa: E402
    POST_REF,
    _fixture,
    _write_json,
    build_post_object_transaction_package,
)


def _rights_row(asset_id: str, **overrides: object) -> dict:
    row = {
        "assetId": asset_id,
        "contentSha256": "sha256:" + "1" * 64,
        "sourceUrl": "https://tuchong.com/1234567/98765432/",
        "license": "图虫用户协议（版权保留）",
        "termsUrl": "https://tuchong.com/agreement/",
        "authorizationProof": "https://tuchong.com/agreement/",
        "creator": "某摄影师",
        "platform": "tuchong.com",
        "capturedAt": "2026-09-08T00:00:00Z",
        "rightsStatus": "unverified",
        "rightsIssues": ["license outside open-license allowlist: 图虫用户协议（版权保留）"],
        "asset": {"sha256": "sha256:" + "1" * 64, "bytes": 10, "mimeType": "image/jpeg"},
    }
    row.update(overrides)
    return row


def test_projection_transcribes_access_policy_and_leaves_absence_absent() -> None:
    restricted = project_asset_admission(_rights_row("a", accessPolicy="robots_disallowed"), object_ref="posts/image/x/1")
    assert restricted["accessPolicy"] == "robots_disallowed"

    legacy = project_asset_admission(_rights_row("b"), object_ref="posts/image/x/1")
    assert "accessPolicy" not in legacy


def test_admission_and_header_list_access_restricted_assets_without_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _row(asset_id: str, ref: str, **overrides: object) -> dict:
        return {
            "objectRef": ref,
            "carrier": "image",
            "assets": [project_asset_admission(_rights_row(asset_id, **overrides), object_ref=ref)],
            "manifest": {"assets": [{"assetId": asset_id, "kind": "image"}]},
            "contentReviewApproved": True,
        }

    objects = [
        _row("pin", "posts/image/风光/a/1", accessPolicy="robots_disallowed"),
        _row("tuchong", "posts/image/风光/b/1", accessPolicy="tos_restricted"),
        _row("commons", "posts/image/风光/c/1", accessPolicy="open"),
        _row("legacy", "posts/image/风光/d/1"),
    ]
    monkeypatch.setattr(release_admission, "_object_rows", lambda *_args, **_kwargs: objects)

    admission = release_admission.build_release_asset_admission(
        release_id="access-policy-001",
        objects_root=tmp_path,
        desired={"entities": [], "posts": [row["objectRef"].removeprefix("posts/") for row in objects]},
        release_class="production",
    )

    assert admission["accessRestrictedAssetIds"] == ["pin", "tuchong"]
    assert len(admission["assets"]) == 4, "访问政策只记录，不把对象排除出 release"
    assert_valid(admission, "release", "release_asset_admission")

    source_digest, entity_catalog_digest = "sha256:" + "1" * 64, "sha256:" + "5" * 64
    header = release_header_document(
        release_id="access-policy-001",
        execution_ids=["20260908--travel-image-six-step--national--pilot-001"],
        source_revision=content_source_revision(
            source_digest=source_digest, entity_catalog_digest=entity_catalog_digest
        ),
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
        source_digest_documents=[SourceDefinitionSnapshot("sha256:" + "1" * 64).to_document()],
        asset_admission=admission,
        canonical_merkle="sha256:" + "2" * 64,
        release_class="production",
        product_lifecycle_state="production",
    )
    assert header["accessRestrictedAssetIds"] == ["pin", "tuchong"]
    assert header["authorizationRequiredAssetIds"] == ["commons", "legacy", "pin", "tuchong"]


def test_post_transaction_transcribes_access_policy_into_rights_closure(tmp_path: Path) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][0]["accessPolicy"] = "tos_restricted"
    _write_json(manifest_path, manifest)
    source_index_path = execution / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_index["assets"][0]["accessPolicy"] = "tos_restricted"
    _write_json(source_index_path, source_index)

    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    rights = json.loads((package / "object/rights.json").read_text(encoding="utf-8"))
    recorded = rights["assets"][0]
    assert recorded["accessPolicy"] == "tos_restricted"
    assert_valid(rights, "release", "asset_rights_closure")
