"""把已取得的专业媒体资产绑定进 receipt 协议 execution 的来源单元（1.download）。

acquisition CLI（task acquire-videos / acquire-images）只落 acquisition 工作区的
immutable receipt + CAS 字节；receipt 协议 execution 的 video/image 对象根在
`posts/<carrier>/**`（载体分根布局）。本 CLI 是两者之间唯一确定性绑定步骤：
从 acquisition receipt 的 exact asset 行冻结 workUnit（DEC-022 的 manifest/receipt
exact pair），写入 execution `sources/{sourceUnitId}/`，不重新发现、不升级权利。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core import ops_governance as og
from core.io import read_json
from core.paths import SOURCE_ACQUISITION_ROOT, execution_root

_ADMISSIBLE_DISTRIBUTIONS = {"research_allowed", "commercial_allowed"}
_ACQUISITION_PREFIX = ("local", "workspace", "source-acquisition")


class MediaUnitBindError(ValueError):
    """Acquisition evidence cannot be bound into this execution."""


def _resolve_object_dir(execution_id: str, object_path: str, *, carrier: str) -> Path:
    relative = Path(str(object_path or "").strip())
    parts = relative.parts
    if (
        relative.is_absolute()
        or ".." in parts
        or len(parts) != 5
        or parts[0] != "posts"
        or parts[1] != carrier
    ):
        raise MediaUnitBindError(
            f"object path must be posts/{carrier}/<angle>/<title>/<seq>: {object_path}"
        )
    return execution_root(execution_id) / relative


def _load_receipt_asset(
    receipt_path: Path, asset_id: str
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    if not receipt_path.is_file():
        raise FileNotFoundError(receipt_path)
    receipt = read_json(receipt_path)
    if not isinstance(receipt, dict):
        raise MediaUnitBindError("acquisition receipt must be one JSON object")
    rows = [
        row
        for row in receipt.get("assets") or []
        if isinstance(row, dict) and row.get("assetId") == asset_id
    ]
    if len(rows) != 1:
        raise MediaUnitBindError(
            f"acquisition receipt must contain exactly one asset {asset_id!r}, "
            f"found {len(rows)}"
        )
    asset = rows[0]
    if asset.get("acquisitionStatus") != "acquired":
        raise MediaUnitBindError(
            f"asset {asset_id} is not acquired: {asset.get('acquisitionStatus')!r}"
        )
    if asset.get("distributionDecision") not in _ADMISSIBLE_DISTRIBUTIONS:
        raise MediaUnitBindError(
            f"asset {asset_id} distributionDecision is not admissible: "
            f"{asset.get('distributionDecision')!r}"
        )
    asset_ref = str(asset.get("assetRef") or "").strip()
    if not asset_ref:
        raise MediaUnitBindError(f"asset {asset_id} lacks CAS assetRef")
    # receipt 布局契约：<acquisition root>/receipts/<sha>.json，CAS ref 相对 root。
    if receipt_path.parent.name != "receipts":
        raise MediaUnitBindError(
            f"acquisition receipt path is non-canonical: {receipt_path}"
        )
    cas_path = receipt_path.parent.parent / asset_ref
    if not cas_path.is_file():
        raise FileNotFoundError(cas_path)
    return receipt, asset, cas_path


def _acquisition_relative_ref(receipt_path: Path) -> str:
    """acquisition receipt 相对 source-acquisition 根的 canonical ref。"""
    try:
        return receipt_path.resolve().relative_to(
            SOURCE_ACQUISITION_ROOT.resolve()
        ).as_posix()
    except ValueError as exc:
        raise MediaUnitBindError(
            "acquisition receipt must live under the source-acquisition root: "
            f"{receipt_path}"
        ) from exc


def handle_bind_sourced_video_unit(args: argparse.Namespace) -> None:
    try:
        receipt_path = Path(str(args.receipt)).expanduser().resolve()
        _receipt, asset, cas_path = _load_receipt_asset(
            receipt_path, str(args.asset_id)
        )
        spec = asset.get("planVideoSpec")
        if not isinstance(spec, dict):
            raise MediaUnitBindError("acquired video asset lacks frozen planVideoSpec")
        object_dir = _resolve_object_dir(
            str(args.execution_id), str(args.object_path), carrier="video"
        )
        entity_name = str(asset.get("entityId") or "").strip()
        source_unit = {
            "sourceId": str(spec.get("sourceId") or ""),
            "sourceKind": str(spec.get("sourceKind") or ""),
            "ordinal": int(spec.get("ordinal") or 1),
            "title": str(spec.get("title") or ""),
            "relevance": str(spec.get("relevance") or ""),
            "rightsStatus": str(spec.get("rightsStatus") or "unverified"),
            "rightsIssues": list(spec.get("rightsIssues") or []),
            "professionalAcquisitionReceiptRef": str(
                spec.get("professionalAcquisitionReceiptRef") or ""
            ),
            "professionalAssetId": str(spec.get("professionalAssetId") or ""),
            "professionalContentSha256": str(
                spec.get("professionalContentSha256") or ""
            ),
            "premiumPlayableEligible": spec.get("premiumPlayableEligible") is True,
            "mediaProbe": spec.get("mediaProbe"),
            "popularitySignals": spec.get("popularitySignals"),
        }
        frozen_source_unit_id = og.source_unit_id(
            canonical_url=str(spec.get("sourcePostUrl") or ""),
            entity_name=entity_name,
            source_kind=str(spec.get("sourceKind") or ""),
        )
        from content.source.sourced_video_unit import (
            write_admitted_sourced_video_unit,
        )

        evidence_path = write_admitted_sourced_video_unit(
            execution_id=str(args.execution_id),
            object_ref=str(args.target_ref),
            source_unit=source_unit,
            source_video_path=cas_path,
            original_creator_name=str(spec.get("originalCreatorName") or ""),
            platform=str(spec.get("platform") or ""),
            source_post_url=str(spec.get("sourcePostUrl") or ""),
            original_asset_url=str(spec.get("originalAssetUrl") or ""),
            attribution_text=str(spec.get("attributionText") or ""),
            rights_basis=str(spec.get("rightsBasis") or ""),
            commercial_authorization_status=str(
                spec.get("commercialAuthorizationStatus") or ""
            ),
            distribution_decision=str(spec.get("distributionDecision") or ""),
            authorization_proof_url=(
                str(spec.get("authorizationProofUrl") or "").strip() or None
            ),
            terms_url=str(spec.get("termsUrl") or "").strip() or None,
            audio_rights_status=str(args.audio_rights_status),
            audio_authorization_proof_url=(
                str(args.audio_authorization_proof_url or "").strip() or None
            ),
            model_release_status=str(spec.get("modelReleaseStatus") or ""),
            property_release_status=str(spec.get("propertyReleaseStatus") or ""),
            takedown_policy=str(spec.get("takedownPolicy") or ""),
            object_dir=object_dir,
            frozen_source_unit_id=frozen_source_unit_id,
        )
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "[task bind-sourced-video-unit] GATE_BLOCK "
            "DATA.SOURCE.VIDEO_PROBE_DEPENDENCY_MISSING "
            f"dependency={exc.name or 'unknown'}"
        ) from exc
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task bind-sourced-video-unit] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {
                "schema": "quwoquan_data.sourced_video_unit_binding_result",
                "executionId": str(args.execution_id),
                "sourceUnitId": frozen_source_unit_id,
                "objectPath": str(args.object_path),
                "evidencePath": evidence_path.resolve().as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_bind_sourced_image_unit(args: argparse.Namespace) -> None:
    try:
        receipt_path = Path(str(args.receipt)).expanduser().resolve()
        receipt, asset, cas_path = _load_receipt_asset(
            receipt_path, str(args.asset_id)
        )
        spec = asset.get("planImageSpec")
        if not isinstance(spec, dict):
            raise MediaUnitBindError("acquired image asset lacks frozen planImageSpec")
        object_dir = _resolve_object_dir(
            str(args.execution_id), str(args.object_path), carrier="image"
        )
        asset_id = str(args.asset_id)
        entity_name = str(asset.get("entityId") or "").strip()
        acquisition_ref = _acquisition_relative_ref(receipt_path)
        collection_id = f"acquisition:{receipt.get('manifestId')}:{asset_id}"
        image = {
            **dict(spec),
            "sourcePath": cas_path,
            "sourceCollectionId": collection_id,
            "acquisitionReceiptRef": acquisition_ref,
            "professionalAssetId": asset_id,
            "professionalContentSha256": str(asset.get("contentSha256") or ""),
            "researchLane": "image",
        }
        source_attribution = dict(asset.get("sourceAttribution") or {})
        source_body = (
            "---\n"
            "researchLane: image\n"
            f"sourceCollectionId: {collection_id}\n"
            f"creator: {asset.get('creator')}\n"
            f"url: {asset.get('sourceUrl')}\n"
            f"license: {asset.get('license')}\n"
            "---\n\n"
            f"{entity_name} 专业图片来源集合，仅供结构化资产与授权链使用。\n"
        )
        frozen_source_unit_id = og.source_unit_id(
            canonical_url=str(asset.get("sourceUrl") or ""),
            entity_name=entity_name,
            source_kind="image_collection",
        )
        from content.source.source_unit_writer import write_source_unit
        from core.source_layout import build_layout

        manifest = write_source_unit(
            object_dir,
            ordinal=int(args.ordinal),
            source_id=str(asset.get("provider") or "professional_image"),
            source_md=source_body,
            clean_md=source_body,
            layout=build_layout(
                source_kind="image_collection",
                extractor="frozen_professional_image_acquisition",
                title=str(asset.get("displayName") or asset.get("title") or entity_name),
                blocks=[
                    {
                        "type": "paragraph",
                        "text": source_body,
                        "sectionSlug": "",
                    }
                ],
            ),
            quality={
                "sourceId": str(asset.get("provider") or "professional_image"),
                "entity": entity_name,
                "quality": "High",
                "score": 100,
                "reasons": [
                    "professional_image_acquisition",
                    "receipt_protocol_binding",
                ],
                "url": str(asset.get("sourceUrl") or ""),
                "statusCode": 200,
                "fetchSucceeded": True,
            },
            platform=str(asset.get("platform") or ""),
            source_category="image_collection",
            source_kind="image_collection",
            extractor="frozen_professional_image_acquisition",
            policy_revision="receipt-protocol-image-v1",
            source_use_mode=(
                "licensed_adaptation"
                if asset.get("rightsStatus") == "verified"
                else "rights_audit_only"
            ),
            research_lane="image",
            license_value=str(asset.get("license") or ""),
            url=str(asset.get("sourceUrl") or ""),
            title=str(asset.get("displayName") or asset.get("title") or ""),
            target_ref=str(args.target_ref),
            relevance=str(asset.get("relevance") or ""),
            images=[image],
            execution_id=str(args.execution_id),
            build_variants=False,
            source={"sourceAttribution": source_attribution},
            frozen_source_unit_id=frozen_source_unit_id,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task bind-sourced-image-unit] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {
                "schema": "quwoquan_data.sourced_image_unit_binding_result",
                "executionId": str(args.execution_id),
                "sourceUnitId": str(manifest["sourceUnitId"]),
                "objectPath": str(args.object_path),
                "assetCount": int(manifest.get("assetCount") or 0),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def register_bind_acquired_media_unit_parsers(
    sub: argparse._SubParsersAction,
) -> None:
    video = sub.add_parser(
        "bind-sourced-video-unit",
        help="把 acquisition receipt 的 exact video asset 绑定为 execution 来源单元",
    )
    video.add_argument("--execution-id", required=True)
    video.add_argument(
        "--object-path",
        required=True,
        help="execution 内对象根相对路径：posts/video/<angle>/<title>/<seq>",
    )
    video.add_argument(
        "--target-ref",
        required=True,
        help="对象绑定的实体 ref：<域>/<类型>/<名称>",
    )
    video.add_argument("--receipt", required=True)
    video.add_argument("--asset-id", required=True)
    video.add_argument(
        "--audio-rights-status",
        required=True,
        choices=(
            "no_audio",
            "licensed",
            "original_authorized",
            "replaced_with_licensed_track",
            "unverified",
        ),
    )
    video.add_argument("--audio-authorization-proof-url")
    video.set_defaults(handler=handle_bind_sourced_video_unit)

    image = sub.add_parser(
        "bind-sourced-image-unit",
        help="把 acquisition receipt 的 exact image asset 绑定为 execution 来源单元",
    )
    image.add_argument("--execution-id", required=True)
    image.add_argument(
        "--object-path",
        required=True,
        help="execution 内对象根相对路径：posts/image/<angle>/<title>/<seq>",
    )
    image.add_argument(
        "--target-ref",
        required=True,
        help="对象绑定的实体 ref：<域>/<类型>/<名称>",
    )
    image.add_argument("--receipt", required=True)
    image.add_argument("--asset-id", required=True)
    image.add_argument("--ordinal", type=int, default=1)
    image.set_defaults(handler=handle_bind_sourced_image_unit)


__all__ = [
    "MediaUnitBindError",
    "handle_bind_sourced_image_unit",
    "handle_bind_sourced_video_unit",
    "register_bind_acquired_media_unit_parsers",
]
