# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t2
"""历史专业视频证据只能以「精确身份 + 原字节」被采纳，不得被就地改写。

`GWT-003`：「adoption ref 与 receipt 同时绑定精确 source release tuple……任一
digest、ref、字节或归属不一致即 `GATE_BLOCK`」，且「重放同一 adoption 只能读取同
digest receipt，不得覆盖或变造历史证据」。

因此在任何字节被复用之前，历史 manifest/receipt 这一对不可变证据必须先自证：

1. 身份信封完整（schema、manifestId、三个 canonical digest、非空资产列表）；
2. `receiptDigest` 自洽，任何篡改都 fail closed；
3. 这份 receipt 确实是为这份 manifest 签发的（`manifestDigest` 精确匹配且四项身份
   一致），而不是另一批次的 receipt 被拿来顶替；
4. receipt 落在它自己 create-once 的 canonical 路径上，换个路径的副本不算证据；
5. 历史文档按当时的 schema 冻结，不因今天的 item 契约变化而失效；
6. 单个资产歧义只作废它自己，不作废整份历史证据。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from content.source.professional_video_rebind_historical import (
    HISTORICAL_PROVENANCE_FIELDS,
    HistoricalVideoEvidenceError,
    index_historical_video_assets,
    validate_historical_video_manifest,
    validate_historical_video_pair,
    validate_historical_video_receipt,
    validate_historical_video_receipt_path,
)
from content.source.professional_video_receipt import document_digest

_REVISION = "sha256:" + "c" * 64
_SOURCE_DIGEST = "sha256:" + "a" * 64
_CATALOG_DIGEST = "sha256:" + "b" * 64


def _legacy_item(asset_id: str = "legacy-1") -> dict[str, Any]:
    """A historical item frozen under a retired shape, not today's item schema."""
    return {
        "assetId": asset_id,
        "entityId": "西湖",
        "retiredLegacyField": "kept as frozen evidence",
    }


def _manifest(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema": "quwoquan_data.professional_video_acquisition_manifest",
        "manifestId": "video-legacy-history",
        "sourceRevision": _REVISION,
        "sourceDigest": _SOURCE_DIGEST,
        "entityCatalogDigest": _CATALOG_DIGEST,
        "items": items if items is not None else [_legacy_item()],
    }


def _receipt(
    manifest: dict[str, Any],
    *,
    assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    stable = {
        "schema": "quwoquan_data.professional_video_acquisition_receipt",
        "manifestId": manifest["manifestId"],
        "manifestDigest": document_digest(manifest),
        "sourceRevision": manifest["sourceRevision"],
        "sourceDigest": manifest["sourceDigest"],
        "entityCatalogDigest": manifest["entityCatalogDigest"],
        "assets": assets if assets is not None else [dict(manifest["items"][0])],
    }
    return {**stable, "receiptDigest": document_digest(stable)}


def test_a_legacy_item_shape_is_still_admissible_historical_evidence() -> None:
    """历史文档是证据而不是待迁移文档，今天的 item 契约不得追溯作废它。"""

    manifest = _manifest()

    assert validate_historical_video_manifest(manifest) is manifest
    assert manifest["items"][0]["retiredLegacyField"] == "kept as frozen evidence"


@pytest.mark.parametrize(
    "field",
    ["manifestId", "sourceRevision", "sourceDigest", "entityCatalogDigest", "items"],
)
def test_a_manifest_missing_any_identity_field_fails_closed(field: str) -> None:
    """身份信封不完整的历史 manifest 不能作为复用来源。"""

    manifest = _manifest()
    del manifest[field]

    with pytest.raises(HistoricalVideoEvidenceError, match=field):
        validate_historical_video_manifest(manifest)


def invalid_sha256_fixture(payload: str) -> str:
    """一个刻意不是 canonical sha256 的摘要值，只用于反证拒绝。"""

    return f"sha256:{payload}"


def test_a_manifest_with_a_non_canonical_digest_fails_closed() -> None:
    """三个身份字段必须是 canonical sha256，短摘要与别名都不得通过。"""

    manifest = _manifest()
    manifest["sourceDigest"] = invalid_sha256_fixture("abc")

    with pytest.raises(
        HistoricalVideoEvidenceError, match="must be one canonical sha256 digest"
    ):
        validate_historical_video_manifest(manifest)


def test_a_manifest_without_items_is_not_present_and_empty_but_invalid() -> None:
    """空资产列表不是「在场为空」的合法历史证据，而是无法自证的输入。"""

    manifest = _manifest(items=[])

    with pytest.raises(HistoricalVideoEvidenceError, match="must be a non-empty list"):
        validate_historical_video_manifest(manifest)


def test_a_foreign_schema_document_is_never_read_as_historical_evidence() -> None:
    """schema 不匹配的文档不得被当作专业视频历史证据读取。"""

    manifest = _manifest()
    manifest["schema"] = "quwoquan_data.professional_image_acquisition_manifest"

    with pytest.raises(HistoricalVideoEvidenceError, match="schema is invalid"):
        validate_historical_video_manifest(manifest)

    receipt = _receipt(_manifest())
    receipt["schema"] = "quwoquan_data.professional_image_acquisition_receipt"

    with pytest.raises(HistoricalVideoEvidenceError, match="schema is invalid"):
        validate_historical_video_receipt(receipt)


def test_a_self_consistent_receipt_is_admissible() -> None:
    """自洽的历史 receipt 原样通过，不被改写。"""

    manifest = _manifest()
    receipt = _receipt(manifest)

    assert validate_historical_video_receipt(receipt) is receipt


def test_a_tampered_receipt_body_fails_closed_on_its_own_digest() -> None:
    """篡改任何字段都会破坏 receiptDigest 自洽性，必须 fail closed。"""

    receipt = _receipt(_manifest())
    receipt["assets"] = [{**receipt["assets"][0], "assetId": "rewritten"}]

    with pytest.raises(HistoricalVideoEvidenceError, match="receiptDigest mismatch"):
        validate_historical_video_receipt(receipt)


def test_a_receipt_issued_for_another_manifest_cannot_stand_in() -> None:
    """receipt 必须精确绑定被提供的这份 manifest。"""

    manifest = _manifest()
    other = _manifest(items=[_legacy_item("legacy-2")])
    receipt = _receipt(other)

    with pytest.raises(
        HistoricalVideoEvidenceError, match="does not bind the supplied manifest"
    ):
        validate_historical_video_pair(manifest, receipt)


def test_a_matching_pair_is_admissible() -> None:
    """digest 与四项身份都一致时这一对证据成立。"""

    manifest = _manifest()

    assert validate_historical_video_pair(manifest, _receipt(manifest)) is None


@pytest.mark.parametrize(
    "field",
    ["manifestId", "sourceRevision", "sourceDigest", "entityCatalogDigest"],
)
def test_pair_identity_drift_names_the_drifted_field(field: str) -> None:
    """身份漂移必须指名具体字段，运营者才知道对不上的是哪一项。"""

    manifest = _manifest()
    receipt = _receipt(manifest)
    receipt[field] = (
        "video-other-history" if field == "manifestId" else "sha256:" + "9" * 64
    )
    receipt["manifestDigest"] = document_digest(manifest)

    with pytest.raises(HistoricalVideoEvidenceError, match=field):
        validate_historical_video_pair(manifest, receipt)


def test_the_canonical_receipt_path_is_derived_from_the_manifest_digest(
    tmp_path: Path,
) -> None:
    """create-once receipt 只认由 manifestDigest 派生的路径。"""

    manifest_digest = document_digest(_manifest())
    token = manifest_digest.removeprefix("sha256:")

    assert (
        validate_historical_video_receipt_path(
            tmp_path / "receipts" / f"{token}.json",
            manifest_digest=manifest_digest,
        )
        is None
    )
    assert (
        validate_historical_video_receipt_path(
            tmp_path / "receipts" / f"{token}-attempt-002.json",
            manifest_digest=manifest_digest,
        )
        is None
    )


@pytest.mark.parametrize(
    "relative",
    [
        "{token}.json",
        "archive/{token}.json",
        "receipts/copy-of-{token}.json",
        "receipts/{token}-attempt-2.json",
        "receipts/{token}.backup.json",
    ],
)
def test_a_receipt_outside_its_canonical_path_is_not_evidence(
    tmp_path: Path,
    relative: str,
) -> None:
    """搬走或改名的 receipt 副本不得冒充历史证据。"""

    manifest_digest = document_digest(_manifest())
    token = manifest_digest.removeprefix("sha256:")
    path = tmp_path / relative.format(token=token)

    with pytest.raises(HistoricalVideoEvidenceError, match="path is not canonical"):
        validate_historical_video_receipt_path(path, manifest_digest=manifest_digest)


def test_a_receipt_path_for_another_manifest_digest_is_not_evidence(
    tmp_path: Path,
) -> None:
    """路径 token 必须是本 manifest 的摘要，不是任意 64 位十六进制。"""

    foreign = "sha256:" + "5" * 64

    with pytest.raises(HistoricalVideoEvidenceError, match="path is not canonical"):
        validate_historical_video_receipt_path(
            tmp_path / "receipts" / f"{foreign.removeprefix('sha256:')}.json",
            manifest_digest=document_digest(_manifest()),
        )


def test_addressable_assets_keep_their_manifest_order() -> None:
    """可寻址资产按历史声明顺序索引，顺序本身也是证据。"""

    rows = [_legacy_item("a"), _legacy_item("b"), _legacy_item("c")]

    indexed, ordered, ambiguous = index_historical_video_assets(rows)

    assert ordered == ("a", "b", "c")
    assert set(indexed) == {"a", "b", "c"}
    assert ambiguous == frozenset()


def test_one_ambiguous_asset_id_is_dropped_without_failing_the_batch() -> None:
    """一个重复 assetId 只作废它自己，其余历史资产仍可采纳。"""

    rows = [
        _legacy_item("a"),
        _legacy_item("duplicated"),
        _legacy_item("b"),
        _legacy_item("duplicated"),
    ]

    indexed, ordered, ambiguous = index_historical_video_assets(rows)

    assert ambiguous == frozenset({"duplicated"})
    assert "duplicated" not in indexed
    assert set(indexed) == {"a", "b"}
    assert "duplicated" in ordered


def test_unaddressable_rows_are_skipped_instead_of_being_guessed() -> None:
    """没有可用 assetId 的行不得被推断出一个身份。"""

    rows: list[Any] = [
        _legacy_item("a"),
        {"entityId": "西湖"},
        {"assetId": "   "},
        "not-an-object",
    ]

    indexed, ordered, ambiguous = index_historical_video_assets(rows)

    assert set(indexed) == {"a"}
    assert ordered == ("a",)
    assert ambiguous == frozenset()


def test_provenance_fields_are_a_frozen_closed_set() -> None:
    """历史与当前 item 的比对字段集合是显式闭集，不由调用点各自拼装。"""

    assert HISTORICAL_PROVENANCE_FIELDS[0] == "assetId"
    assert len(HISTORICAL_PROVENANCE_FIELDS) == len(set(HISTORICAL_PROVENANCE_FIELDS))
    assert {
        "entityId",
        "provider",
        "platform",
        "sourceUrl",
        "rightsStatus",
        "license",
        "termsUrl",
        "authorizationProof",
        "rightsIssues",
    } <= set(HISTORICAL_PROVENANCE_FIELDS)
    assert "safetyReview" not in HISTORICAL_PROVENANCE_FIELDS
    assert "distributionDecision" not in HISTORICAL_PROVENANCE_FIELDS


@pytest.mark.parametrize("value", [None, [], "manifest", 7])
def test_a_non_object_document_is_a_typed_failure(value: Any) -> None:
    """非对象输入是 typed 失败，不得退化为空结果。"""

    with pytest.raises(HistoricalVideoEvidenceError, match="must be an object"):
        validate_historical_video_manifest(value)
    with pytest.raises(HistoricalVideoEvidenceError, match="must be an object"):
        validate_historical_video_receipt(value)
