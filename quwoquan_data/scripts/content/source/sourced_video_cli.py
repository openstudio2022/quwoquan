"""CLI registration for evidence-backed sourced-video ingestion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def handle_sourced_video_ingest(args: argparse.Namespace) -> None:
    from content.source.sourced_video_unit import (
        write_admitted_sourced_video_unit,
    )
    from core.schema import assert_valid

    source_unit_path = Path(args.source_unit)
    admission_path = Path(args.admission_packet)
    source_unit = json.loads(source_unit_path.read_text(encoding="utf-8"))
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    assert_valid(
        admission,
        "content",
        "sourced_video_admission_packet",
        label="sourced video admission packet",
    )
    source_video_path = Path(str(admission["sourceVideoPath"]))
    if not source_video_path.is_absolute():
        source_video_path = admission_path.parent / source_video_path
    output = write_admitted_sourced_video_unit(
        execution_id=args.execution_id,
        object_ref=args.object_ref,
        source_unit=source_unit,
        source_video_path=source_video_path,
        original_creator_name=str(admission["originalCreatorName"]),
        platform=str(admission["platform"]),
        source_post_url=str(admission["sourcePostUrl"]),
        original_asset_url=str(admission["originalAssetUrl"]),
        attribution_text=str(admission["attributionText"]),
        rights_basis=str(admission["rightsBasis"]),
        commercial_authorization_status=str(
            admission["commercialAuthorizationStatus"]
        ),
        publication_admission=str(admission["publicationAdmission"]),
        authorization_proof_url=admission.get("authorizationProofUrl"),
        terms_url=admission.get("termsUrl"),
        risk_acceptance_id=admission.get("riskAcceptanceId"),
        audio_rights_status=str(admission["audioRightsStatus"]),
        audio_authorization_proof_url=admission.get(
            "audioAuthorizationProofUrl"
        ),
        model_release_status=str(admission["modelReleaseStatus"]),
        property_release_status=str(admission["propertyReleaseStatus"]),
        takedown_policy=str(admission["takedownPolicy"]),
    )
    print(
        json.dumps(
            {"decision": "GO", "sourcedVideoEvidenceRef": str(output)},
            ensure_ascii=False,
        )
    )


def register_sourced_video_ingest_parser(
    commands: argparse._SubParsersAction,
) -> None:
    parser = commands.add_parser(
        "sourced-video-ingest",
        help="以真实媒体探测、水印 OCR 和音频权利证据准入外部视频",
    )
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--object-ref", required=True)
    parser.add_argument("--source-unit", required=True)
    parser.add_argument("--admission-packet", required=True)
    parser.set_defaults(handler=handle_sourced_video_ingest)


__all__ = ["register_sourced_video_ingest_parser"]
