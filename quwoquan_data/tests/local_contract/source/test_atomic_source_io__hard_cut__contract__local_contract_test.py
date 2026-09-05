# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t4
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from content.source.atomic_source_io import materialize_source_candidate
from core.io import read_json
from core.schema import assert_valid
from verify import stage_artifacts

EXECUTION_ID = "20260903--travel-article-atomic--test--pilot-001"
TARGET_REF = "entities/地点/景区/西湖"
DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
CLI = DATA_ROOT / "scripts/cli.py"


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _candidate(body: bytes, *, source_id: str = "explicit-text") -> dict[str, object]:
    return {
        "schema": "quwoquan_data.source_candidate",
        "sourcePlanRef": "sources/plans/" + "a" * 64 + ".json",
        "sourcePlanDigest": "sha256:" + "b" * 64,
        "sourceId": source_id,
        "title": "西湖显式来源",
        "sourceClass": "manual_text_snapshot",
        "sourceUseMode": "factual_reference_only",
        "purpose": "正文事实底稿",
        "rightsClue": "人工提供，仅作事实参考",
        "manualFile": "west-lake.txt",
        "contentSha256": "sha256:" + hashlib.sha256(body).hexdigest(),
        "fetchedAt": "2026-09-03T00:00:00Z",
    }


def _bind_candidate_to_plan(execution: Path, candidate: dict[str, object], *, target_ref: str = TARGET_REF) -> dict[str, object]:
    planned = {key: value for key, value in candidate.items() if key not in {"schema", "sourcePlanRef", "sourcePlanDigest", "fetchedAt"}}
    plan = {
        "schema": "quwoquan_data.source_plan",
        "executionId": EXECUTION_ID,
        "targetRef": target_ref,
        "carrier": "article",
        "candidates": [planned],
    }
    ref = "sources/plans/" + hashlib.sha256(target_ref.encode()).hexdigest() + ".json"
    path = _write(execution / ref, plan)
    return {**candidate, "sourcePlanRef": ref, "sourcePlanDigest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}


def _target_set() -> dict[str, object]:
    return {
        "schema": "quwoquan_data.target_set",
        "executionId": EXECUTION_ID,
        "carrier": "article",
        "selectionPolicy": "frozen",
        "entityCatalogDigest": "sha256:" + "a" * 64,
        "candidateBinding": {"scope": "output", "ref": "data/local/candidates.json", "digest": "sha256:" + "b" * 64, "candidateCount": 1},
        "targetCount": 1,
        "targetRefs": [TARGET_REF],
        "targets": [{"name": "西湖", "entityType": "地点/景区"}],
    }


def test_source_plan_is_schema_valid_and_create_once(tmp_path: Path) -> None:
    plan = {
        "schema": "quwoquan_data.source_plan",
        "executionId": EXECUTION_ID,
        "targetRef": TARGET_REF,
        "carrier": "article",
        "candidates": [{
            "sourceId": "west-lake-gov", "title": "西湖资料",
            "url": "https://example.invalid/west-lake",
            "purpose": "事实底稿", "sourceClass": "official",
            "sourceUseMode": "factual_reference_only",
            "rightsClue": "公开网页，事实引用",
        }],
    }
    assert_valid(plan, "source", "source_plan")
    without_mode = {**plan["candidates"][0]}
    without_mode.pop("sourceUseMode")
    with pytest.raises(ValueError, match="schema violation"):
        assert_valid({**plan, "candidates": [without_mode]}, "source", "source_plan")
    with pytest.raises(ValueError, match="schema violation"):
        assert_valid(
            {
                **plan,
                "candidates": [
                    {**plan["candidates"][0], "sourceUseMode": "inferred"}
                ],
            },
            "source",
            "source_plan",
        )
    with pytest.raises(ValueError):
        assert_valid({**plan, "candidates": [{**plan["candidates"][0], "url": "http://example.invalid"}]}, "source", "source_plan")


def test_one_manual_candidate_materializes_cas_unit_and_ref_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "output"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    from content.source import atomic_source_io
    monkeypatch.setattr(atomic_source_io, "execution_root", lambda _execution_id: output / "data/tasks" / EXECUTION_ID)
    monkeypatch.setattr(atomic_source_io, "execution_source_unit_dir", lambda _execution_id, unit_id: output / "data/tasks" / EXECUTION_ID / "sources" / unit_id)
    body = "西湖是明确提供的本地来源。".encode()
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "west-lake.txt").write_bytes(body)
    candidate = _bind_candidate_to_plan(output / "data/tasks" / EXECUTION_ID, _candidate(body))
    candidate_path = _write(tmp_path / "candidate.json", candidate)
    meta, unit = materialize_source_candidate(candidate_path, execution_id=EXECUTION_ID, target_ref=TARGET_REF, manual_root=manual)
    repeated, repeated_unit = materialize_source_candidate(candidate_path, execution_id=EXECUTION_ID, target_ref=TARGET_REF, manual_root=manual)
    assert repeated_unit == unit and repeated == meta
    assert meta["sourceUseMode"] == "factual_reference_only"
    assert read_json(unit / "meta.json")["sourceUseMode"] == "factual_reference_only"
    assert (unit / "snapshot.raw").read_bytes() == body
    assert (unit / "source.md").read_bytes() == body
    assert os.stat(unit / "snapshot.raw").st_ino == os.stat(output / "content_library/_source_cas" / hashlib.sha256(body).hexdigest()[:2] / hashlib.sha256(body).hexdigest()[2:4] / hashlib.sha256(body).hexdigest()).st_ino
    refs = read_json(output / "data/tasks" / EXECUTION_ID / TARGET_REF / "1.download/source_refs.json")
    assert len(refs["sources"]) == 1
    assert refs["sources"][0]["sourceUnitId"] == meta["sourceUnitId"]
    assert not (unit / "source.clean.md").exists()
    assert not (unit / "source.layout.json").exists()
    assert not (unit / "source.quality.json").exists()


def test_candidate_requires_explicit_legal_source_use_mode(tmp_path: Path) -> None:
    body = b"explicit"
    missing = _candidate(body)
    missing.pop("sourceUseMode")
    with pytest.raises(ValueError, match="schema violation"):
        materialize_source_candidate(
            _write(tmp_path / "missing-mode.json", missing),
            execution_id=EXECUTION_ID,
            target_ref=TARGET_REF,
            manual_root=tmp_path,
        )
    invalid = {**_candidate(body), "sourceUseMode": "derived_from_source_class"}
    with pytest.raises(ValueError, match="schema violation"):
        materialize_source_candidate(
            _write(tmp_path / "invalid-mode.json", invalid),
            execution_id=EXECUTION_ID,
            target_ref=TARGET_REF,
            manual_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("execution_id", "target_ref", "source_use_mode", "carrier"),
    (
        (
            "20260903--travel-homepage-atomic--test--pilot-001",
            "entities/地点/景区/西湖",
            "factual_reference_only",
            "homepage",
        ),
        (
            EXECUTION_ID,
            "posts/article/攻略/西湖攻略/1",
            "factual_reference_only",
            "article",
        ),
        (
            "20260903--travel-image-atomic--test--pilot-001",
            "posts/image/画报/西湖光影/1",
            "licensed_adaptation",
            "image",
        ),
        (
            "20260903--travel-video-atomic--test--pilot-001",
            "posts/video/体验/西湖泛舟/1",
            "rights_audit_only",
            "video",
        ),
    ),
)
def test_atomic_meta_preserves_ai_mode_for_every_carrier(
    execution_id: str,
    target_ref: str,
    source_use_mode: str,
    carrier: str,
) -> None:
    from content.source.atomic_source_io import _build_meta

    candidate = {
        **_candidate(b"explicit"),
        "sourceUseMode": source_use_mode,
    }
    assert_valid(candidate, "source", "source_candidate")
    meta = _build_meta(
        execution_id=execution_id,
        target_ref=target_ref,
        candidate=candidate,
        source_unit_id="explicit-text__0123456789abcdef",
        raw_sha="sha256:" + "1" * 64,
        source_sha="sha256:" + "2" * 64,
        canonical_url="https://example.com/west-lake",
        receipt_row=None,
        receipt_ref="",
        asset_ref="",
    )

    assert meta["sourceUseMode"] == source_use_mode
    assert meta["carrier"] == carrier
    assert_valid(meta, "source", "atomic_source_unit_meta")


def test_atomic_meta_schema_requires_legal_source_use_mode() -> None:
    body = b"explicit"
    candidate = _candidate(body)
    from content.source.atomic_source_io import _build_meta

    meta = _build_meta(
        execution_id=EXECUTION_ID,
        target_ref=TARGET_REF,
        candidate=candidate,
        source_unit_id="explicit-text__0123456789abcdef",
        raw_sha="sha256:" + "1" * 64,
        source_sha="sha256:" + "2" * 64,
        canonical_url="https://example.com/west-lake",
        receipt_row=None,
        receipt_ref="",
        asset_ref="",
    )
    assert meta["sourceUseMode"] == candidate["sourceUseMode"]
    assert_valid(meta, "source", "atomic_source_unit_meta")
    with pytest.raises(ValueError, match="schema violation"):
        assert_valid({key: value for key, value in meta.items() if key != "sourceUseMode"}, "source", "atomic_source_unit_meta")


def test_existing_atomic_meta_rejects_source_use_mode_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    from content.source import atomic_source_io

    monkeypatch.setattr(
        atomic_source_io,
        "execution_root",
        lambda _execution_id: output / "data/tasks" / EXECUTION_ID,
    )
    monkeypatch.setattr(
        atomic_source_io,
        "execution_source_unit_dir",
        lambda _execution_id, unit_id: output / "data/tasks" / EXECUTION_ID / "sources" / unit_id,
    )
    body = b"explicit"
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "west-lake.txt").write_bytes(body)
    candidate = _bind_candidate_to_plan(output / "data/tasks" / EXECUTION_ID, _candidate(body))
    candidate_path = _write(tmp_path / "candidate.json", candidate)
    original, unit = materialize_source_candidate(
        candidate_path,
        execution_id=EXECUTION_ID,
        target_ref=TARGET_REF,
        manual_root=manual,
    )
    changed = {**candidate, "sourceUseMode": "licensed_adaptation"}
    _write(candidate_path, changed)

    with pytest.raises(ValueError, match="not exactly one source plan candidate"):
        materialize_source_candidate(
            candidate_path,
            execution_id=EXECUTION_ID,
            target_ref=TARGET_REF,
            manual_root=manual,
        )
    assert read_json(unit / "meta.json")["sourceUseMode"] == original["sourceUseMode"]


def test_manual_candidate_requires_rights_and_digest(tmp_path: Path) -> None:
    body = b"explicit"
    candidate = _candidate(body)
    candidate.pop("rightsClue")
    path = _write(tmp_path / "candidate.json", candidate)
    with pytest.raises(ValueError, match="schema violation"):
        materialize_source_candidate(path, execution_id=EXECUTION_ID, target_ref=TARGET_REF, manual_root=tmp_path)




def test_binary_manual_file_cannot_bypass_atomic_acquisition(tmp_path: Path) -> None:
    body = b"\x00\x00binary-media"
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "west-lake.txt").write_bytes(body)
    execution = tmp_path / "execution"
    candidate = _bind_candidate_to_plan(execution, _candidate(body))
    path = _write(tmp_path / "candidate.json", candidate)
    from content.source import atomic_source_io
    original_root = atomic_source_io.execution_root
    atomic_source_io.execution_root = lambda _execution_id: execution
    try:
        with pytest.raises(ValueError, match="image/video require atomic acquisition"):
            materialize_source_candidate(path, execution_id=EXECUTION_ID, target_ref=TARGET_REF, manual_root=manual)
    finally:
        atomic_source_io.execution_root = original_root

def test_video_cli_exposes_manifest_only() -> None:
    completed = subprocess.run([sys.executable, str(CLI), "task", "acquire-videos", "--help"], cwd=DATA_ROOT.parent, text=True, capture_output=True, check=False)
    assert completed.returncode == 0
    assert "--manifest" in completed.stdout
    assert "--commons-entity" not in completed.stdout
    assert "--stock-entity" not in completed.stdout
    assert "--handoff-ref" not in completed.stdout


def test_image_cli_exposes_manifest_only() -> None:
    completed = subprocess.run([sys.executable, str(CLI), "task", "acquire-images", "--help"], cwd=DATA_ROOT.parent, text=True, capture_output=True, check=False)
    assert completed.returncode == 0
    assert "--manifest" in completed.stdout
    assert "--handoff-ref" not in completed.stdout


def test_source_unit_identity_includes_acquisition_receipt() -> None:
    from content.source.atomic_source_io import _source_unit_id

    candidate = {"sourceId": "commons", "url": "https://commons.wikimedia.org/wiki/File:X.jpg"}
    first = _source_unit_id(
        EXECUTION_ID, TARGET_REF, candidate, "sha256:" + "1" * 64,
        acquisition_identity="receipts/first.json#asset-a",
    )
    second = _source_unit_id(
        EXECUTION_ID, TARGET_REF, candidate, "sha256:" + "1" * 64,
        acquisition_identity="receipts/second.json#asset-a",
    )
    assert first != second


def test_stage_artifacts_accepts_atomic_source_unit_through_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / EXECUTION_ID
    _write(root / "0.plan/target_set.json", _target_set())
    body = b"explicit local source"
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "west-lake.txt").write_bytes(body)
    candidate = _bind_candidate_to_plan(root, _candidate(body))
    candidate_path = _write(tmp_path / "candidate.json", candidate)
    from content.source import atomic_source_io
    monkeypatch.setattr(atomic_source_io, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(atomic_source_io, "execution_source_unit_dir", lambda _execution_id, unit_id: root / "sources" / unit_id)
    materialize_source_candidate(candidate_path, execution_id=EXECUTION_ID, target_ref=TARGET_REF, manual_root=manual)
    monkeypatch.setattr(stage_artifacts, "execution_root", lambda _execution_id: root)
    report = stage_artifacts.verify_stage_artifacts(execution_id=EXECUTION_ID, publish_root=tmp_path / "publish", release_root=tmp_path / "release", commercial=False, through="1.download")
    assert report["passed"], report["issues"]



def _video_receipt(root: Path) -> tuple[Path, bytes, bytes, dict[str, object]]:
    from content.source.professional_video_receipt import document_digest

    video_body = b"frozen-video-body"
    poster_body = bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
        "0000000c4944415408d763f8cfc000000301010018dd8db10000000049454e44ae426082"
    )
    video_digest = "sha256:" + hashlib.sha256(video_body).hexdigest()
    poster_digest = "sha256:" + hashlib.sha256(poster_body).hexdigest()
    video_ref = f"cas/sha256/{video_digest[7:9]}/{video_digest[7:]}.mp4"
    poster_ref = f"cas/sha256/{poster_digest[7:9]}/{poster_digest[7:]}.png"
    (root / video_ref).parent.mkdir(parents=True, exist_ok=True)
    (root / video_ref).write_bytes(video_body)
    (root / poster_ref).parent.mkdir(parents=True, exist_ok=True)
    (root / poster_ref).write_bytes(poster_body)
    rights = {
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Atomic.webm",
        "license": "CC BY 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Atomic.webm",
        "rightsStatus": "verified",
        "authorizationRequired": False,
        "distributionDecision": "commercial_allowed",
        "rightsIssues": [],
    }
    row = {
        "assetId": "commons-video-1",
        "entityId": "西湖",
        "observedEntityId": "西湖",
        "provider": "wikimedia_commons_video",
        "platform": "Wikimedia Commons",
        "displayName": "Wikimedia Commons",
        "sourceKind": "tourism_video_site",
        "acquisitionPath": "public_direct",
        "sourceUrl": rights["sourceUrl"],
        "assetUrl": "https://upload.wikimedia.org/example.webm",
        "manualFile": "",
        "apiEvidence": "",
        "accessEvidence": {
            "anonymousAssetAccess": True,
            "loginRequired": False,
            "captchaRequired": False,
            "paywallRequired": False,
            "drmProtected": False,
            "accessControlBypass": False,
        },
        "title": "西湖视频",
        "relevance": "西湖视频",
        "creator": "Commons creator",
        "capturedAt": "2026-09-03T00:00:00Z",
        "acquisitionStatus": "acquired",
        **rights,
        "contentSha256": video_digest,
        "assetRef": video_ref,
        "bytes": len(video_body),
        "mimeType": "video/mp4",
        "posterAssetRef": poster_ref,
        "posterContentSha256": poster_digest,
        "posterBytes": len(poster_body),
        "posterMimeType": "image/png",
        "posterRights": {
            "derivation": "frame_from_licensed_video",
            "sourceAssetId": "commons-video-1",
            **rights,
        },
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "safetyReview": {
            "status": "passed",
            "entityMatch": "matched",
            "privacyRisk": "none",
            "minorRisk": "none",
            "maliciousMediaRisk": "none",
            "watermarkStatus": "absent",
            "reviewedAt": "2026-09-03T00:00:00Z",
            "reviewer": "reviewer",
            "evidenceRef": "evidence/video.json",
            "safetyEvidenceFileSha256": "sha256:" + "a" * 64,
        },
        "mediaProbe": dict(_PLAYABLE_PROBE_FOR_ATOMIC),
        "duplicateOf": "",
        "failureCode": "",
        "failure": "",
        "popularitySignals": dict(_POPULARITY_FOR_ATOMIC),
        "planVideoSpec": dict(_PLAN_SPEC_FOR_ATOMIC),
    }
    row["planVideoSpec"].update(
        professionalContentSha256=video_digest,
        assetUrl=f"cas://sha256/{video_digest[7:]}",
        sizeBytes=len(video_body),
        mediaProbe=dict(_PLAYABLE_PROBE_FOR_ATOMIC),
        popularitySignals=dict(_POPULARITY_FOR_ATOMIC),
    )
    manifest_digest = "sha256:" + "b" * 64
    stable = {
        "schema": "quwoquan_data.professional_video_acquisition_receipt",
        "manifestId": "atomic-video",
        "manifestDigest": manifest_digest,
        "sourceRevision": "fresh",
        "sourceDigest": "sha256:" + "c" * 64,
        "entityCatalogDigest": "sha256:" + "d" * 64,
        "posterPolicy": {
            "required": True,
            "format": "image/png",
            "rightsInheritance": "licensed_video_derivative",
        },
        "plannedAssetCount": 1,
        "discoveredAssetCount": 1,
        "downloadedAssetCount": 1,
        "acceptedAssetCount": 1,
        "rejectedAssetCount": 0,
        "providerAssetCounts": [{
            "displayName": "Wikimedia Commons",
            "provider": "wikimedia_commons_video",
            "platform": "Wikimedia Commons",
            "plannedAssetCount": 1,
            "discoveredAssetCount": 1,
            "downloadedAssetCount": 1,
            "acceptedAssetCount": 1,
            "rejectedAssetCount": 0,
            "verifiedAssetCount": 1,
            "unverifiedAssetCount": 0,
            "restrictedAssetCount": 0,
            "unknownAssetCount": 0,
            "rankingEligibleAssetCount": 0,
        }],
        "assets": [row],
    }
    receipt = {**stable, "receiptDigest": document_digest(stable)}
    receipt_path = root / f"receipts/{manifest_digest[7:]}.json"
    _write(receipt_path, receipt)
    return receipt_path, video_body, poster_body, row


_PLAYABLE_PROBE_FOR_ATOMIC = {
    "width": 320, "height": 180, "frameCount": 40, "framesPerSecond": 10.0,
    "durationMs": 4000, "codec": "h264", "hasAudio": False,
    "sampleCount": 18, "distinctFrameCount": 18, "movingTransitionCount": 17,
    "meanTransitionDelta": 0.1, "playable": True, "motionVideo": True,
    "staticImageSequence": False, "premiumPlayableEligible": True,
}
_POPULARITY_FOR_ATOMIC = {
    "playCount": None, "likeCount": None, "commentCount": None,
    "shareCount": None, "favoriteCount": None,
    "observedAt": "2026-09-03T00:00:00Z",
    "provider": "wikimedia_commons_video", "topic": "西湖",
    "timeBucket": "commons-unranked", "popularityScore": None,
    "popularityPercentile": None, "rankingEligible": False,
    "ineligibleReason": "incomplete_popularity_signals", "comparisonCandidateCount": 0,
}
_PLAN_SPEC_FOR_ATOMIC = {
    "sourceId": "wikimedia_commons_video", "sourceKind": "tourism_video_site",
    "ordinal": 1, "title": "西湖视频", "relevance": "西湖视频",
    "platform": "Wikimedia Commons", "assetUrl": "cas://sha256/" + "0" * 64,
    "originalAssetUrl": "https://upload.wikimedia.org/example.webm",
    "sourcePostUrl": "https://commons.wikimedia.org/wiki/File:Atomic.webm",
    "authorizationProofUrl": "https://commons.wikimedia.org/wiki/File:Atomic.webm",
    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
    "rightsBasis": "CC BY 4.0", "originalCreatorName": "Commons creator",
    "attributionText": "西湖视频 — Commons creator — CC BY 4.0",
    "commercialAuthorizationStatus": "verified", "rightsStatus": "verified",
    "rightsIssues": [], "distributionDecision": "commercial_allowed",
    "modelReleaseStatus": "not_required", "propertyReleaseStatus": "not_required",
    "takedownPolicy": "quwoquan_standard_notice_and_takedown", "durationSeconds": 4.0,
    "sizeBytes": 1, "mediaProbe": _PLAYABLE_PROBE_FOR_ATOMIC,
    "popularitySignals": _POPULARITY_FOR_ATOMIC,
    "professionalAcquisitionReceiptRef": "receipts/" + "b" * 64 + ".json",
    "professionalAssetId": "commons-video-1",
    "professionalContentSha256": "sha256:" + "0" * 64,
    "premiumPlayableEligible": True,
}


def test_video_receipt_materializes_video_and_poster_with_explicit_rights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    execution = output / "data/tasks" / EXECUTION_ID
    from content.source import atomic_source_io

    monkeypatch.setattr(atomic_source_io, "execution_root", lambda _execution_id: execution)
    monkeypatch.setattr(
        atomic_source_io,
        "execution_source_unit_dir",
        lambda _execution_id, unit_id: execution / "sources" / unit_id,
    )
    acquisition = output / "data/local/workspace/source-acquisition/video"
    receipt_path, video_body, poster_body, receipt_row = _video_receipt(acquisition)
    candidate = {
        "schema": "quwoquan_data.source_candidate",
        "sourcePlanRef": "sources/plans/" + "a" * 64 + ".json",
        "sourcePlanDigest": "sha256:" + "b" * 64,
        "sourceId": "commons-video",
        "title": "西湖 Commons 视频",
        "sourceClass": "open_license_media",
        "sourceUseMode": "licensed_adaptation",
        "purpose": "视频与 poster 媒体",
        "rightsClue": "CC BY 4.0",
        "url": "https://commons.wikimedia.org/wiki/File:Atomic.webm",
        "fetchedAt": "2026-09-03T00:00:00Z",
    }
    candidate = _bind_candidate_to_plan(execution, candidate)
    meta, unit = materialize_source_candidate(
        _write(tmp_path / "candidate-video.json", candidate),
        execution_id=EXECUTION_ID,
        target_ref=TARGET_REF,
        receipt_path=receipt_path,
        receipt_asset_id="commons-video-1",
        acquisition_root=acquisition,
    )
    index = read_json(unit / "assets/index.json")
    assert [row["assetRole"] for row in index["assets"]] == ["video", "poster"]
    assert (unit / "assets" / index["assets"][0]["fileName"]).read_bytes() == video_body
    assert (unit / "assets" / index["assets"][1]["fileName"]).read_bytes() == poster_body
    assert index["assets"][1]["contentSha256"] == receipt_row["posterContentSha256"]
    assert index["assets"][1]["sourceUrl"] == receipt_row["sourceUrl"]
    assert index["assets"][1]["license"] == receipt_row["license"]
    assert meta["acquisition"]["posterContentSha256"] == receipt_row["posterContentSha256"]



def test_video_review_asset_set_derives_selected_video_and_exact_poster(
    tmp_path: Path,
) -> None:
    from content.release.canonical.post_transaction_assets import source_assets
    from verify.stage_artifacts import _review_asset_refs

    execution = tmp_path / EXECUTION_ID
    object_root = execution / TARGET_REF
    unit = execution / "sources/commons-video"
    video_ref = "sources/commons-video/assets/video.webm"
    poster_ref = "sources/commons-video/assets/poster.png"
    unused_ref = "sources/commons-video/assets/unused.jpg"
    _write(
        object_root / "1.download/source_refs.json",
        {
            "sources": [{
                "sourceUnitId": "commons-video",
                "sourceRef": "sources/commons-video/source.md",
                "metaRef": "sources/commons-video/meta.json",
            }]
        },
    )
    _write(
        unit / "meta.json",
        {"acquisition": {"posterAssetRef": "assets/poster.png"}},
    )
    rights = {
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Atomic.webm",
        "license": "CC BY 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Atomic.webm",
    }
    _write(
        unit / "assets/index.json",
        {
            "assets": [
                {
                    "fileName": "video.webm",
                    "assetRole": "video",
                    "sourceAssetId": "source-video:video",
                    **rights,
                },
                {
                    "fileName": "poster.png",
                    "assetRole": "poster",
                    "sourceAssetId": "source-video:poster",
                    "derivedFromSourceAssetId": "source-video:video",
                    **rights,
                },
                {"fileName": "unused.jpg", "assetRole": "image", **rights},
            ]
        },
    )
    for name in ("video.webm", "poster.png", "unused.jpg"):
        asset_path = unit / "assets" / name
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(name.encode())

    assert _review_asset_refs(
        root=execution,
        obj=object_root,
        lane="video",
        draft={},
        compose={"sourceVideo": {"assetRef": video_ref}},
        source_assets=source_assets(execution),
    ) == (video_ref, poster_ref)
    assert unused_ref not in _review_asset_refs(
        root=execution,
        obj=object_root,
        lane="video",
        draft={},
        compose={"sourceVideo": {"assetRef": video_ref}},
        source_assets=source_assets(execution),
    )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027
def test_download_budget_uses_shared_policy_and_typed_over_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from content.source import atomic_source_io

    monkeypatch.setattr(atomic_source_io, "source_unit_asset_budget_bytes", lambda lane: 8)
    body = b"0123456789"
    with pytest.raises(ValueError, match="DATA.MEDIA.ASSET_OVER_BUDGET"):
        atomic_source_io._budget_media_body(
            body,
            acquisition_kind="video",
            research_lane="video",
        )
    assert atomic_source_io._budget_media_body(
        b"1234", acquisition_kind="video", research_lane="video"
    ) == (b"1234", None)


def test_download_budget_rebinds_deterministic_image_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    from content.source import atomic_source_io

    derived = b"small"
    monkeypatch.setattr(atomic_source_io, "source_unit_asset_budget_bytes", lambda lane: 8)
    monkeypatch.setattr(
        atomic_source_io,
        "derive_budget_compliant_variant",
        lambda _body, *, budget_bytes: {
            "bytes": derived,
            "width": 640,
            "height": 480,
            "mimeType": "image/webp",
        },
    )
    result, evidence = atomic_source_io._budget_media_body(
        b"0123456789", acquisition_kind="image", research_lane="image"
    )
    assert result == derived
    assert evidence == {
        "operation": "policy_declared_image_rendition",
        "sourceSha256": "sha256:" + hashlib.sha256(b"0123456789").hexdigest(),
        "sourceBytes": 10,
        "resultSha256": "sha256:" + hashlib.sha256(derived).hexdigest(),
        "resultBytes": 5,
        "width": 640,
        "height": 480,
        "mimeType": "image/webp",
        "budgetBytes": 8,
    }


def test_professional_image_transport_limit_comes_from_media_policy() -> None:
    from content.source import professional_image_acquisition
    from core.media_processing_policy import MEDIA_PROCESSING_POLICY

    assert professional_image_acquisition._MAX_IMAGE_BYTES == MEDIA_PROCESSING_POLICY.source_asset_max_bytes


def test_image_derivative_preserves_original_receipt_identity_and_mime_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source import atomic_source_io

    original = b"original-large-image"
    derived = b"small-webp"
    receipt_row = {
        "assetId": "image-1",
        "assetRef": "cas/original.jpg",
        "contentSha256": "sha256:" + hashlib.sha256(original).hexdigest(),
        "bytes": len(original),
        "mimeType": "image/jpeg",
        "sourceUrl": "https://example.test/image",
        "license": "CC BY 4.0",
        "termsUrl": "https://example.test/terms",
        "authorizationProof": "https://example.test/proof",
        "rightsStatus": "verified",
        "authorizationRequired": False,
        "distributionDecision": "commercial_allowed",
        "rightsIssues": [],
        "_receiptRef": "receipts/image.json",
    }
    execution = tmp_path / "output/data/tasks" / EXECUTION_ID
    monkeypatch.setattr(atomic_source_io, "execution_root", lambda _execution_id: execution)
    monkeypatch.setattr(atomic_source_io, "execution_source_unit_dir", lambda _execution_id, unit_id: execution / "sources" / unit_id)
    monkeypatch.setattr(
        atomic_source_io,
        "_candidate_bytes",
        lambda *args, **kwargs: (original, receipt_row["sourceUrl"], dict(receipt_row), "image", {}),
    )
    monkeypatch.setattr(atomic_source_io, "source_unit_asset_budget_bytes", lambda _lane: 10)
    monkeypatch.setattr(
        atomic_source_io,
        "derive_budget_compliant_variant",
        lambda _body, *, budget_bytes: {"bytes": derived, "width": 10, "height": 10, "mimeType": "image/webp"},
    )
    candidate = _bind_candidate_to_plan(execution, {
        "schema": "quwoquan_data.source_candidate", "sourcePlanRef": "sources/plans/" + "a" * 64 + ".json",
        "sourcePlanDigest": "sha256:" + "b" * 64, "sourceId": "image", "title": "image",
        "sourceClass": "open_license_media", "sourceUseMode": "licensed_adaptation", "purpose": "image",
        "rightsClue": "CC BY 4.0", "url": "https://example.test/image", "fetchedAt": "2026-09-03T00:00:00Z",
    })
    meta, unit = materialize_source_candidate(
        _write(tmp_path / "candidate-image.json", candidate), execution_id=EXECUTION_ID,
        target_ref=TARGET_REF, receipt_path=tmp_path / "receipt.json", receipt_asset_id="image-1",
        acquisition_root=tmp_path,
    )
    acquisition = meta["acquisition"]
    binding = acquisition["derivativeBinding"]
    assert acquisition["contentSha256"] == receipt_row["contentSha256"]
    assert acquisition["bytes"] == receipt_row["bytes"]
    assert acquisition["mimeType"] == "image/jpeg"
    assert binding["derivedSha256"] == "sha256:" + hashlib.sha256(derived).hexdigest()
    assert binding["derivedMimeType"] == "image/webp"
    assert binding["derivedExtension"] == ".webp"
    assert Path(acquisition["assetRef"]).suffix == ".webp"
    assert (unit / acquisition["assetRef"]).read_bytes() == derived
