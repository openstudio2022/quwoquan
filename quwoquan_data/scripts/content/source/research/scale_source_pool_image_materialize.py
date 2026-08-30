"""image lane 冻结候选的 source unit 物化（拆分自 scale_source_pool_runtime）。"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

from content.source.media_source_admission import (
    MediaSourceAdmissionQuery,
    canonical_digest,
)
from content.source.research.scale_source_pool_evidence_path import (
    compute_evidence_file_sha256,
    resolve_evidence_file,
)
from content.source.research.scale_source_pool_runtime_blockers import _fail


def _materialize_frozen_image_source_unit(
    *,
    execution_id: str,
    entity_id: str,
    entity_type: str,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """Project one source-admitted professional image without provider rediscovery."""

    # 对象目录解析与 source unit 写入必须经 scale_source_pool_runtime 命名空间
    # 延迟查找：既有 local_contract 测试通过 patch runtime 模块属性隔离文件系统
    # 副作用，拆分不得改变该 patch 语义。
    from content.source.research import scale_source_pool_runtime as _runtime

    evidence_root = row.get("sourcePoolEvidenceRoot")
    if not isinstance(evidence_root, Path):
        raise _fail("selected image candidate lacks frozen evidence root")
    try:
        admission_result = MediaSourceAdmissionQuery(evidence_root).require_accepted(
            str(row["sourceAdmissionRef"])
        )
        admission = admission_result["receipt"]
        if (
            admission_result["receiptDigest"] != row["sourceAdmissionDigest"]
            or admission["assetKind"] != "image"
            or admission["objectRef"] != row["objectRef"]
        ):
            raise ValueError("image source admission projection drift")
        acquisition_bindings = [
            binding
            for binding in admission["evidenceBindings"]
            if binding.get("role") == "acquisition"
        ]
        if len(acquisition_bindings) != 1:
            raise ValueError("image source admission lacks one acquisition binding")
        acquisition_binding = acquisition_bindings[0]
        receipt_path = resolve_evidence_file(
            evidence_root,
            acquisition_binding["ref"],
            label="image acquisition receipt",
        )
        if (
            compute_evidence_file_sha256(receipt_path)
            != acquisition_binding["fileSha256"]
        ):
            raise ValueError("image acquisition receipt file SHA drift")
        receipt = read_json(receipt_path)
        if not isinstance(receipt, Mapping):
            raise TypeError("image acquisition receipt must be one object")
        assert_valid(
            receipt,
            "source",
            "professional_image_acquisition_receipt",
            label="frozen image acquisition receipt",
        )
        if canonical_digest(receipt) != acquisition_binding["documentDigest"]:
            raise ValueError("image acquisition receipt document digest drift")
        asset_id = str(admission["assetSnapshot"]["assetId"])
        assets = [
            asset
            for asset in receipt.get("assets") or []
            if isinstance(asset, Mapping) and asset.get("assetId") == asset_id
        ]
        if len(assets) != 1:
            raise ValueError("image candidate must bind exactly one acquisition asset")
        asset = assets[0]
        if (
            asset.get("entityId") != entity_id
            or asset.get("contentSha256") != row.get("contentSha256")
            or asset.get("sourceAttribution") != row.get("sourceAttribution")
            or asset.get("acquisitionStatus") != "acquired"
            or asset.get("distributionDecision") not in {
                "research_allowed",
                "commercial_allowed",
            }
        ):
            raise ValueError("image candidate acquisition binding drift")
        asset_path = resolve_evidence_file(
            evidence_root,
            asset["assetRef"],
            label="image acquisition CAS asset",
        )
        if compute_evidence_file_sha256(asset_path) != asset["contentSha256"]:
            raise ValueError("image acquisition CAS bytes drift")
        plan_spec = asset.get("planImageSpec")
        if not isinstance(plan_spec, Mapping):
            raise TypeError("image acquisition asset lacks planImageSpec")
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise _fail(f"frozen image acquisition is invalid: {exc}") from exc

    collection_id = f"acquisition:{receipt['manifestId']}:{asset_id}"
    acquisition_ref = Path(str(acquisition_binding["ref"]))
    acquisition_prefix = ("local", "workspace", "source-acquisition")
    if acquisition_ref.parts[: len(acquisition_prefix)] == acquisition_prefix:
        acquisition_ref = Path(*acquisition_ref.parts[len(acquisition_prefix) :])
    if (
        acquisition_ref.is_absolute()
        or ".." in acquisition_ref.parts
        or len(acquisition_ref.parts) < 2
        or acquisition_ref.parts[-2] != "receipts"
        or acquisition_ref.suffix != ".json"
    ):
        raise _fail("frozen image acquisition receiptRef is non-canonical")
    image = {
        **dict(plan_spec),
        "sourcePath": asset_path,
        "sourceCollectionId": collection_id,
        "acquisitionReceiptRef": acquisition_ref.as_posix(),
        "professionalAssetId": asset_id,
        "professionalContentSha256": str(asset["contentSha256"]),
        "researchLane": "image",
    }
    source_attribution = dict(asset["sourceAttribution"])
    source_body = (
        "---\n"
        "researchLane: image\n"
        f"sourceCollectionId: {collection_id}\n"
        f"creator: {asset['creator']}\n"
        f"url: {asset['sourceUrl']}\n"
        f"license: {asset['license']}\n"
        "---\n\n"
        f"{entity_id} 专业图片来源集合，仅供结构化资产与授权链使用。\n"
    )
    object_dir = _runtime.resolve_entity_object_dir(
        execution_id,
        entity_id,
        etype_hint=entity_type,
    )
    return _runtime.write_source_unit(
        object_dir,
        ordinal=1,
        source_id=str(asset.get("provider") or "professional_image"),
        source_md=source_body,
        clean_md=source_body,
        quality={
            "sourceId": str(asset.get("provider") or "professional_image"),
            "entity": entity_id,
            "quality": "High",
            "score": 100,
            "reasons": ["frozen_scale_source_pool", "media_source_admission"],
            "url": str(asset["sourceUrl"]),
            "statusCode": 200,
            "fetchSucceeded": True,
        },
        platform=str(asset["platform"]),
        source_category="image_collection",
        source_kind="image_collection",
        extractor="frozen_professional_image_acquisition",
        policy_revision="scale-source-pool-image-v1",
        source_use_mode=(
            "licensed_adaptation"
            if asset.get("rightsStatus") == "verified"
            else "rights_audit_only"
        ),
        research_lane="image",
        license_value=str(asset["license"]),
        url=str(asset["sourceUrl"]),
        title=str(asset["displayName"]),
        target_ref=str(row["entityRef"]),
        relevance=str(asset["relevance"]),
        images=[image],
        execution_id=execution_id,
        build_variants=False,
        source={"sourceAttribution": source_attribution},
        frozen_source_unit_id="image-pool-" + str(row["candidateId"]).split("-", 1)[-1],
    )
