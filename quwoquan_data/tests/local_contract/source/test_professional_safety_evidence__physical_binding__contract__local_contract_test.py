from __future__ import annotations

import io
from pathlib import Path

import pytest
from content.source.professional_safety_evidence import (
    bytes_sha256,
    file_sha256,
    load_bound_safety_evidence,
    validate_image_safety_payload,
    validate_video_safety_payload,
)
from core.io import write_json
from PIL import Image


def _review(evidence_ref: str) -> dict[str, object]:
    return {
        "status": "passed",
        "entityMatch": "matched",
        "privacyRisk": "none",
        "minorRisk": "none",
        "maliciousMediaRisk": "none",
        "watermarkStatus": "absent",
        "reviewedAt": "2026-08-10T08:00:00Z",
        "reviewer": "contract-reviewer",
        "evidenceRef": evidence_ref,
        "safetyEvidenceFileSha256": "sha256:" + "0" * 64,
    }


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (800, 640), color=(32, 96, 160)).save(output, format="JPEG")
    return output.getvalue()


def _image_item(evidence_ref: str) -> dict[str, object]:
    return {
        "assetId": "image-a",
        "entityId": "都江堰",
        "observedEntityId": "都江堰",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Image_A.jpg",
        "safetyReview": _review(evidence_ref),
    }


def _image_evidence(item: dict[str, object], body: bytes) -> dict[str, object]:
    review = item["safetyReview"]
    assert isinstance(review, dict)
    return {
        "schema": "quwoquan_data.professional_image_safety_review_evidence",
        "assetId": item["assetId"],
        "entityId": item["entityId"],
        "observedEntityId": item["observedEntityId"],
        "sourceUrl": item["sourceUrl"],
        "contentSha256": bytes_sha256(body),
        "bytes": len(body),
        "dimensions": {"width": 800, "height": 640},
        **{key: review[key] for key in (
            "status", "entityMatch", "privacyRisk", "minorRisk",
            "maliciousMediaRisk", "watermarkStatus", "reviewedAt", "reviewer",
        )},
    }


def _write_bound_evidence(
    root: Path,
    item: dict[str, object],
    evidence: dict[str, object],
) -> Path:
    review = item["safetyReview"]
    assert isinstance(review, dict)
    path = root / str(review["evidenceRef"])
    write_json(path, evidence)
    review["safetyEvidenceFileSha256"] = file_sha256(path)
    return path


def test_image_evidence_binds_file_payload_entity_and_review(tmp_path: Path) -> None:
    body = _image_bytes()
    item = _image_item("evidence/image-a.json")
    _write_bound_evidence(tmp_path, item, _image_evidence(item, body))
    evidence = load_bound_safety_evidence(
        item,
        evidence_root=tmp_path,
        kind="image",
    )
    validate_image_safety_payload(
        evidence,
        item,
        body=body,
        width=800,
        height=640,
    )


def test_evidence_missing_tamper_symlink_and_entity_drift_fail_closed(
    tmp_path: Path,
) -> None:
    body = _image_bytes()
    missing = _image_item("evidence/missing.json")
    with pytest.raises(ValueError, match="missing or escapes"):
        load_bound_safety_evidence(missing, evidence_root=tmp_path, kind="image")

    tampered = _image_item("evidence/tampered.json")
    tampered_path = _write_bound_evidence(
        tmp_path,
        tampered,
        _image_evidence(tampered, body),
    )
    tampered_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="file SHA-256 drift"):
        load_bound_safety_evidence(tampered, evidence_root=tmp_path, kind="image")

    target = _image_item("evidence/target.json")
    target_path = _write_bound_evidence(
        tmp_path,
        target,
        _image_evidence(target, body),
    )
    linked = _image_item("evidence/linked.json")
    linked_review = linked["safetyReview"]
    assert isinstance(linked_review, dict)
    linked_review["safetyEvidenceFileSha256"] = file_sha256(target_path)
    (tmp_path / "evidence/linked.json").symlink_to(target_path.name)
    with pytest.raises(ValueError, match="must not traverse a symlink"):
        load_bound_safety_evidence(linked, evidence_root=tmp_path, kind="image")

    drift = _image_item("evidence/drift.json")
    drift_evidence = _image_evidence(drift, body)
    drift_evidence["entityId"] = "西湖"
    _write_bound_evidence(tmp_path, drift, drift_evidence)
    with pytest.raises(ValueError, match="identity/review drift"):
        load_bound_safety_evidence(drift, evidence_root=tmp_path, kind="image")


def _video_probe() -> dict[str, object]:
    return {
        "width": 1080,
        "height": 1080,
        "frameCount": 504,
        "framesPerSecond": 29.97,
        "durationMs": 16817,
        "codec": "h264",
        "hasAudio": True,
        "sampleCount": 18,
        "distinctFrameCount": 18,
        "movingTransitionCount": 17,
        "meanTransitionDelta": 0.084256,
        "motionVideo": True,
        "staticImageSequence": False,
        "playable": True,
        "premiumPlayableEligible": True,
    }


def test_video_evidence_binds_manual_file_probe_and_contact_sheet(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "acquisition"
    manual_root = tmp_path / "manual"
    media = manual_root / "panda.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"motion-video-fixture" * 1024)
    contact = evidence_root / "evidence/panda-contact.jpg"
    contact.parent.mkdir(parents=True)
    contact.write_bytes(_image_bytes())
    item = {
        "assetId": "video-a",
        "entityId": "都江堰",
        "observedEntityId": "都江堰",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Panda.webm",
        "acquisitionPath": "manual_file",
        "manualFile": "panda.mp4",
        "safetyReview": _review("evidence/video-a.json"),
    }
    review = item["safetyReview"]
    assert isinstance(review, dict)
    evidence = {
        "schema": "quwoquan_data.manual_asset_safety_evidence",
        "assetId": item["assetId"],
        "entityId": item["entityId"],
        "observedEntityId": item["observedEntityId"],
        "sourcePageUrl": item["sourceUrl"],
        "fileRef": item["manualFile"],
        "fileSha256": file_sha256(media),
        "bytes": media.stat().st_size,
        "contactSheetRef": "evidence/panda-contact.jpg",
        "contactSheetSha256": file_sha256(contact),
        "mediaProbe": _video_probe(),
        **{key: review[key] for key in (
            "status", "entityMatch", "privacyRisk", "minorRisk",
            "maliciousMediaRisk", "watermarkStatus", "reviewedAt", "reviewer",
        )},
    }
    _write_bound_evidence(evidence_root, item, evidence)
    loaded = load_bound_safety_evidence(
        item,
        evidence_root=evidence_root,
        kind="video",
        manual_root=manual_root,
    )
    validate_video_safety_payload(
        loaded,
        item,
        content_sha256=file_sha256(media),
        size_bytes=media.stat().st_size,
        media_probe=_video_probe(),
    )
    contact.write_bytes(b"tampered-contact-sheet")
    with pytest.raises(ValueError, match="contact-sheet SHA-256 drift"):
        load_bound_safety_evidence(
            item,
            evidence_root=evidence_root,
            kind="video",
            manual_root=manual_root,
        )
