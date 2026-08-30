from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest
from content.source.professional_image_discovery_governed import (
    ProfessionalImageGovernedDiscoveryError,
    build_professional_image_governed_candidate_catalog,
    write_professional_image_governed_candidate_catalog,
)

PLAN_DIGEST = "sha256:" + "d" * 64
_MANUAL_BYTES: dict[str, bytes] = {}


def _digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _write(root: Path, ref: str, payload: dict) -> None:
    manual_ref = str(payload.get("manualFile") or "")
    if manual_ref:
        manual_path = root / manual_ref
        manual_path.parent.mkdir(parents=True, exist_ok=True)
        manual_path.write_bytes(_MANUAL_BYTES[manual_ref])
    attribution_ref = str(payload.get("sourceAttributionFile") or "")
    if attribution_ref:
        attribution_path = root / attribution_ref
        attribution_path.parent.mkdir(parents=True, exist_ok=True)
        attribution_path.write_bytes(
            json.dumps(payload["sourceAttribution"], ensure_ascii=False).encode("utf-8")
        )
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _evidence(
    *, provider: str, path: str, ordinal: int, content: str | None = None,
) -> dict:
    is_manual = path == "manual_file"
    if provider == "pinterest":
        source_url = f"https://www.pinterest.com/pin/{ordinal}/"
        asset_url = f"https://i.pinimg.com/originals/aa/bb/image-{ordinal}.jpg"
    elif provider == "tuchong":
        source_url = f"https://tuchong.com/{ordinal}/"
        asset_url = f"https://photo.tuchong.com/original/image-{ordinal}.jpg"
    elif provider == "wikimedia_commons":
        source_url = f"https://commons.wikimedia.org/wiki/File:Image-{ordinal}.jpg"
        asset_url = f"https://upload.wikimedia.org/wikipedia/commons/image-{ordinal}.jpg"
    else:
        source_url = f"https://openverse.org/image/{ordinal}"
        asset_url = f"https://images.example.org/original/image-{ordinal}.jpg"
    api_hosts = {
        "pinterest": "https://api.pinterest.com/v5/pins",
        "tuchong": "https://open.tuchong.com/api/images",
        "wikimedia_commons": "https://commons.wikimedia.org/w/api.php",
        "openverse": "https://api.openverse.org/v1/images",
    }
    creator = f"Creator {ordinal}"
    observed_at = "2026-08-08T00:00:00Z"
    manual_ref = f"manual/{provider}-image-{ordinal}.jpg" if is_manual else ""
    seed = content or f"{provider}:{ordinal}"
    manual_body = (seed.encode("utf-8") * 4096)[:4096]
    content_sha = "sha256:" + hashlib.sha256(manual_body).hexdigest()
    if is_manual:
        _MANUAL_BYTES[manual_ref] = manual_body
    evidence = {
        "schema": (
            "quwoquan_data.professional_image_manual_file_evidence"
            if is_manual
            else "quwoquan_data.professional_image_supported_api_evidence"
        ),
        "provider": provider,
        "acquisitionPath": path,
        "discoveryCandidateId": f"{provider}:{ordinal:016x}",
        "sourcePageUrl": source_url,
        "assetUrl": "" if is_manual else asset_url,
        "manualFile": manual_ref,
        "apiEvidence": "" if is_manual else api_hosts[provider],
        "creator": creator,
        "title": f"Original {ordinal}",
        "observedAt": observed_at,
        "contentSha256": content_sha,
        "originalAssetCandidate": True,
        "generated": False,
    }
    if not is_manual:
        return evidence
    platform = {
        "pinterest": "Pinterest",
        "tuchong": "图虫",
        "wikimedia_commons": "Wikimedia Commons",
        "openverse": "Openverse",
    }[provider]
    attribution = {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": creator,
        "originalCreatorProfileUrl": None,
        "platform": platform,
        "sourcePostUrl": source_url,
        "originalAssetUrl": source_url,
        "attributionText": f"{creator} / {platform}",
        "rightsBasis": "CC BY-SA 4.0",
        "commercialAuthorizationStatus": "verified",
        "publicationAdmission": "commercial_release",
        "authorizationProofUrl": source_url,
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "riskAcceptanceId": None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": observed_at,
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        "derivedModifications": [],
    }
    stable = {
        **evidence,
        "evidenceId": f"professional-image-manual-{ordinal:016x}",
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "3" * 64,
            "inputs": ["test-input"],
        },
        "entityCatalogDigest": "sha256:" + "4" * 64,
        "handoffId": "test-handoff",
        "handoffRevision": 1,
        "handoffDigest": "sha256:" + "5" * 64,
        "assetBytes": len(manual_body),
        "dimensions": {"width": 64, "height": 64},
        "rightsStatus": "verified",
        "license": "CC BY-SA 4.0",
        "licenseSnapshot": "Creative Commons Attribution-ShareAlike 4.0",
        "usageScope": "app_publish",
        "modelReleaseStatus": "not_required",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": source_url,
        "rightsIssues": [],
        "sourceAttributionFile": f"manual/{provider}-attribution-{ordinal}.json",
        "sourceAttributionFileSha256": "",
        "sourceAttribution": attribution,
    }
    attribution_body = json.dumps(attribution, ensure_ascii=False).encode("utf-8")
    stable["sourceAttributionFileSha256"] = (
        "sha256:" + hashlib.sha256(attribution_body).hexdigest()
    )
    return {**stable, "evidenceDigest": _digest(stable)}


def _build(root: Path, refs: list[str]) -> dict:
    return build_professional_image_governed_candidate_catalog(
        discovery_plan_id="professional-image-discovery-1111111111111111",
        discovery_plan_digest=PLAN_DIGEST,
        created_at="2026-08-08T00:01:00Z",
        evidence_root=root,
        evidence_refs=refs,
    )


def test_governed_catalog_freezes_pinterest_manual_api_and_tuchong_api_evidence(
    tmp_path: Path,
) -> None:
    rows = [
        ("evidence/pinterest-manual.json", _evidence(provider="pinterest", path="manual_file", ordinal=1)),
        ("evidence/pinterest-api.json", _evidence(provider="pinterest", path="supported_api", ordinal=2)),
        ("evidence/tuchong-api.json", _evidence(provider="tuchong", path="supported_api", ordinal=3)),
    ]
    for ref, row in rows:
        _write(tmp_path, ref, row)

    first = _build(tmp_path, [ref for ref, _row in rows])
    second = _build(tmp_path, list(reversed([ref for ref, _row in rows])))

    assert first == second
    assert first["candidateCount"] == 3
    assert {row["acquisitionPath"] for row in first["candidates"]} == {
        "manual_file",
        "supported_api",
    }
    assert all(row["pathEvidence"]["digest"].startswith("sha256:") for row in first["candidates"])
    assert all(row["pathEvidence"]["fileSha256"].startswith("sha256:") for row in first["candidates"])
    destination = write_professional_image_governed_candidate_catalog(
        first, output_root=tmp_path / "catalogs"
    )
    assert write_professional_image_governed_candidate_catalog(
        first, output_root=tmp_path / "catalogs"
    ) == destination


def test_governed_catalog_allows_wikimedia_and_openverse_as_supplements(
    tmp_path: Path,
) -> None:
    rows = [
        ("evidence/wikimedia.json", _evidence(
            provider="wikimedia_commons", path="manual_file", ordinal=8
        )),
        ("evidence/openverse.json", _evidence(
            provider="openverse", path="supported_api", ordinal=9
        )),
    ]
    for ref, row in rows:
        _write(tmp_path, ref, row)
    catalog = _build(tmp_path, [ref for ref, _row in rows])
    assert [row["provider"] for row in catalog["candidates"]] == [
        "openverse", "wikimedia_commons"
    ]


def test_governed_catalog_rejects_public_direct_thumbnail_generated_and_duplicates(
    tmp_path: Path,
) -> None:
    public = _evidence(provider="pinterest", path="manual_file", ordinal=1)
    public.update(
        schema="quwoquan_data.professional_image_public_response",
        acquisitionPath="public_direct",
    )
    _write(tmp_path, "evidence/public.json", public)
    with pytest.raises(ProfessionalImageGovernedDiscoveryError, match="public_direct"):
        _build(tmp_path, ["evidence/public.json"])

    thumbnail = _evidence(provider="pinterest", path="supported_api", ordinal=2)
    thumbnail["assetUrl"] = "https://i.pinimg.com/236x/aa/bb/image.jpg"
    _write(tmp_path, "evidence/thumbnail.json", thumbnail)
    with pytest.raises(ProfessionalImageGovernedDiscoveryError, match="thumbnail"):
        _build(tmp_path, ["evidence/thumbnail.json"])

    generated = _evidence(provider="tuchong", path="manual_file", ordinal=3)
    generated["generated"] = True
    generated["evidenceDigest"] = _digest(
        {key: value for key, value in generated.items() if key != "evidenceDigest"}
    )
    _write(tmp_path, "evidence/generated.json", generated)
    with pytest.raises(ProfessionalImageGovernedDiscoveryError, match="generated"):
        _build(tmp_path, ["evidence/generated.json"])

    shared = "sha256:" + "f" * 64
    first = _evidence(provider="pinterest", path="manual_file", ordinal=4, content=shared)
    second = _evidence(provider="tuchong", path="manual_file", ordinal=5, content=shared)
    _write(tmp_path, "evidence/duplicate-a.json", first)
    _write(tmp_path, "evidence/duplicate-b.json", second)
    with pytest.raises(ProfessionalImageGovernedDiscoveryError, match="duplicate original"):
        _build(tmp_path, ["evidence/duplicate-a.json", "evidence/duplicate-b.json"])


def test_governed_catalog_rejects_unsafe_evidence_path_and_create_once_drift(
    tmp_path: Path,
) -> None:
    with pytest.raises(ProfessionalImageGovernedDiscoveryError, match="safe relative"):
        _build(tmp_path, ["../outside.json"])

    ref = "evidence/manual.json"
    _write(tmp_path, ref, _evidence(provider="pinterest", path="manual_file", ordinal=6))
    catalog = _build(tmp_path, [ref])
    catalog["candidates"][0]["creator"] = "Drifted Creator"
    with pytest.raises(ProfessionalImageGovernedDiscoveryError, match="digest drift"):
        write_professional_image_governed_candidate_catalog(
            catalog, output_root=tmp_path / "catalogs"
        )


def test_source_pool_cli_freezes_governed_professional_image_catalog(
    tmp_path: Path, capsys,
) -> None:
    import content.source.research.handler_cli as handler

    evidence_root = tmp_path / "evidence-root"
    ref = "evidence/manual.json"
    _write(evidence_root, ref, _evidence(provider="pinterest", path="manual_file", ordinal=7))
    parser = argparse.ArgumentParser()
    handler.register_parser(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(
        [
            "source-pool",
            "freeze-professional-image-catalog",
            "--discovery-plan-id",
            "professional-image-discovery-1111111111111111",
            "--discovery-plan-digest",
            PLAN_DIGEST,
            "--created-at",
            "2026-08-08T00:01:00Z",
            "--evidence-root",
            str(evidence_root),
            "--evidence-ref",
            ref,
            "--output-root",
            str(tmp_path / "output"),
        ]
    )
    args.handler(args)
    result = json.loads(capsys.readouterr().out)
    assert result["candidateCount"] == 1
    assert result["catalogRef"].startswith(
        "professional-image-candidate-catalogs/governed/"
    )
    assert (tmp_path / "output" / result["catalogRef"]).is_file()
