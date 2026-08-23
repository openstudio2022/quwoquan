from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from content.execution.campaign.scale import campaign_workload_targets
from content.execution.controller.execute.pre_acquisition_handoff import (
    write_pre_acquisition_handoff,
)
from content.source.professional_image_discovery_governed import (
    build_professional_image_governed_candidate_catalog,
)
from content.source.professional_image_manual_file_evidence import (
    MANUAL_EVIDENCE_INVALID,
    MANUAL_EVIDENCE_SHA_DRIFT,
    ProfessionalImageManualEvidenceError,
    prepare_professional_image_manual_evidence,
)
from core.source_digest import ExecutionBundleIdentity, SourceDefinitionSnapshot

SOURCE_DIGEST = "sha256:" + "a" * 64
ENTITY_CATALOG_DIGEST = "sha256:" + "b" * 64
PLAN_DIGEST = "sha256:" + "c" * 64
OBSERVED_AT = "2026-08-12T01:02:03Z"
SOURCE_PAGE = "https://commons.wikimedia.org/wiki/File:Example.jpg"
LICENSE_TERMS = "https://creativecommons.org/licenses/by-sa/4.0/"


def _sha256(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _image_bytes() -> bytes:
    pixels = bytes((index * 37 + index // 17) % 256 for index in range(160 * 120 * 3))
    image = Image.frombytes("RGB", (160, 120), pixels)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=97)
    body = buffer.getvalue()
    assert len(body) >= 3000
    return body


def _handoff(output_root: Path) -> Path:
    _document, path = write_pre_acquisition_handoff(
        handoff_id="travel-m100-image-manual-writer-test",
        handoff_revision=1,
        supersedes_handoff=None,
        scale="M100",
        vertical="travel",
        lifecycle="research",
        scope_type="region",
        region_ref="china",
        primary_topic_ref=None,
        related_topic_refs=(),
        source_selection={
            "homepage": {"mode": "site_primary", "providers": ["wikipedia"]},
            "article": {"mode": "site_primary", "providers": ["mafengwo"]},
            "image": {"mode": "search_supplement", "providers": ["adobe_stock"]},
            "video": {"mode": "site_primary", "providers": ["bilibili"]},
        },
        run_date="20260812",
        campaign_sequence=1,
        campaign_retry_of=None,
        source_digest=SourceDefinitionSnapshot(digest=SOURCE_DIGEST).to_document(),
        execution_bundle=ExecutionBundleIdentity(
            digest="sha256:" + "d" * 64
        ).to_document(),
        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
        workload_targets=campaign_workload_targets("M100"),
        output_root=output_root,
    )
    return path


def _attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": "Example Photographer",
        "originalCreatorProfileUrl": None,
        "platform": "Wikimedia Commons",
        "sourcePostUrl": SOURCE_PAGE,
        "originalAssetUrl": SOURCE_PAGE,
        "attributionText": "Example Photographer / Wikimedia Commons",
        "rightsBasis": "CC BY-SA 4.0",
        "commercialAuthorizationStatus": "verified",
        "publicationAdmission": "commercial_release",
        "authorizationProofUrl": SOURCE_PAGE,
        "termsUrl": LICENSE_TERMS,
        "riskAcceptanceId": None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": OBSERVED_AT,
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
    }


def _inputs(tmp_path: Path) -> dict[str, object]:
    source_root = tmp_path / "operator-input"
    attribution_root = tmp_path / "operator-attribution"
    source_root.mkdir(parents=True)
    attribution_root.mkdir(parents=True)
    body = _image_bytes()
    (source_root / "original.jpg").write_bytes(body)
    attribution_body = (
        json.dumps(_attribution(), ensure_ascii=False, indent=2).encode("utf-8")
        + b"\n"
    )
    (attribution_root / "source-attribution.json").write_bytes(attribution_body)
    return {
        "source_root": source_root,
        "source_ref": "original.jpg",
        "source_sha256": _sha256(body),
        "source_attribution_root": attribution_root,
        "source_attribution_ref": "source-attribution.json",
        "source_attribution_sha256": _sha256(attribution_body),
        "handoff_ref": _handoff(tmp_path / "handoff-output"),
        "output_root": tmp_path / "source-acquisition",
        "provider": "wikimedia_commons",
        "discovery_candidate_id": "wikimedia_commons:0123456789abcdef",
        "source_page_url": SOURCE_PAGE,
        "creator": "Example Photographer",
        "title": "Example landscape",
        "observed_at": OBSERVED_AT,
        "rights_status": "verified",
        "license_name": "CC BY-SA 4.0",
        "license_snapshot": "Creative Commons Attribution-ShareAlike 4.0",
        "usage_scope": "app_publish",
        "model_release_status": "not_required",
        "terms_url": LICENSE_TERMS,
        "authorization_proof": SOURCE_PAGE,
    }


def test_manual_writer_binds_exact_bytes_attribution_handoff_and_catalog(
    tmp_path: Path,
) -> None:
    arguments = _inputs(tmp_path)
    evidence, path = prepare_professional_image_manual_evidence(**arguments)

    assert evidence["sourceAttributionFileSha256"] == arguments[
        "source_attribution_sha256"
    ]
    assert path.is_file()
    copied = arguments["output_root"] / evidence["manualFile"]
    assert _sha256(copied.read_bytes()) == evidence["contentSha256"]
    attribution_copy = arguments["output_root"] / evidence["sourceAttributionFile"]
    assert _sha256(attribution_copy.read_bytes()) == evidence[
        "sourceAttributionFileSha256"
    ]
    replay, replay_path = prepare_professional_image_manual_evidence(**arguments)
    assert (replay, replay_path) == (evidence, path)

    ref = path.relative_to(arguments["output_root"]).as_posix()
    catalog = build_professional_image_governed_candidate_catalog(
        discovery_plan_id="professional-image-discovery-1111111111111111",
        discovery_plan_digest=PLAN_DIGEST,
        created_at="2026-08-12T01:03:00Z",
        evidence_root=arguments["output_root"],
        evidence_refs=[ref],
    )
    assert catalog["candidateCount"] == 1
    assert catalog["candidates"][0]["originalAssetIdentity"]["manualFile"] == evidence[
        "manualFile"
    ]


def test_manual_writer_rejects_sha_drift_symlinks_and_attribution_drift(
    tmp_path: Path,
) -> None:
    sha_arguments = _inputs(tmp_path / "sha")
    sha_arguments["source_sha256"] = "sha256:" + "e" * 64
    with pytest.raises(ProfessionalImageManualEvidenceError) as sha_error:
        prepare_professional_image_manual_evidence(**sha_arguments)
    assert sha_error.value.code == MANUAL_EVIDENCE_SHA_DRIFT

    link_arguments = _inputs(tmp_path / "link")
    linked = link_arguments["source_root"] / "linked.jpg"
    linked.symlink_to(link_arguments["source_root"] / "original.jpg")
    link_arguments["source_ref"] = "linked.jpg"
    with pytest.raises(ProfessionalImageManualEvidenceError) as link_error:
        prepare_professional_image_manual_evidence(**link_arguments)
    assert link_error.value.code == MANUAL_EVIDENCE_INVALID

    attribution_arguments = _inputs(tmp_path / "attribution")
    attribution = _attribution()
    attribution["originalCreatorName"] = "Someone Else"
    attribution_body = json.dumps(attribution, indent=2).encode("utf-8") + b"\n"
    attribution_path = (
        attribution_arguments["source_attribution_root"] / "source-attribution.json"
    )
    attribution_path.write_bytes(attribution_body)
    attribution_arguments["source_attribution_sha256"] = _sha256(attribution_body)
    with pytest.raises(ProfessionalImageManualEvidenceError, match="binding drift"):
        prepare_professional_image_manual_evidence(**attribution_arguments)


def test_manual_writer_rejects_output_symlink_traversal(tmp_path: Path) -> None:
    arguments = _inputs(tmp_path)
    output_root = arguments["output_root"]
    outside = tmp_path / "outside"
    output_root.mkdir()
    outside.mkdir()
    (output_root / "manual-image-inputs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ProfessionalImageManualEvidenceError, match="outputRef"):
        prepare_professional_image_manual_evidence(**arguments)
    assert list(outside.iterdir()) == []


def test_source_pool_cli_registers_manual_image_writer(capsys) -> None:
    import content.source.research.handler_cli as handler

    parser = argparse.ArgumentParser()
    handler.register_parser(parser.add_subparsers(dest="command", required=True))
    help_text = parser.format_help()
    with pytest.raises(SystemExit) as help_exit:
        parser.parse_args(
            ["source-pool", "prepare-professional-image-manual-evidence", "--help"]
        )
    assert help_exit.value.code == 0
    assert help_text
    assert "--source-attribution-sha256" in capsys.readouterr().out


def test_source_pool_cli_writes_manual_image_evidence(
    tmp_path: Path, capsys,
) -> None:
    import content.source.research.handler_cli as handler

    arguments = _inputs(tmp_path)
    parser = argparse.ArgumentParser()
    handler.register_parser(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(
        [
            "source-pool",
            "prepare-professional-image-manual-evidence",
            "--source-root",
            str(arguments["source_root"]),
            "--source-ref",
            str(arguments["source_ref"]),
            "--source-sha256",
            str(arguments["source_sha256"]),
            "--source-attribution-root",
            str(arguments["source_attribution_root"]),
            "--source-attribution-ref",
            str(arguments["source_attribution_ref"]),
            "--source-attribution-sha256",
            str(arguments["source_attribution_sha256"]),
            "--handoff-ref",
            str(arguments["handoff_ref"]),
            "--output-root",
            str(arguments["output_root"]),
            "--provider",
            str(arguments["provider"]),
            "--discovery-candidate-id",
            str(arguments["discovery_candidate_id"]),
            "--source-page-url",
            str(arguments["source_page_url"]),
            "--creator",
            str(arguments["creator"]),
            "--title",
            str(arguments["title"]),
            "--observed-at",
            str(arguments["observed_at"]),
            "--rights-status",
            str(arguments["rights_status"]),
            "--license",
            str(arguments["license_name"]),
            "--license-snapshot",
            str(arguments["license_snapshot"]),
            "--usage-scope",
            str(arguments["usage_scope"]),
            "--model-release-status",
            str(arguments["model_release_status"]),
            "--terms-url",
            str(arguments["terms_url"]),
            "--authorization-proof",
            str(arguments["authorization_proof"]),
        ]
    )
    args.handler(args)
    result = json.loads(capsys.readouterr().out)
    assert result["evidenceDigest"].startswith("sha256:")
    assert (arguments["output_root"] / result["evidenceRef"]).is_file()
    assert (arguments["output_root"] / result["sourceAttributionFile"]).is_file()
