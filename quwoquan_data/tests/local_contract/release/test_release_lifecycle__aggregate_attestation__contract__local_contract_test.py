"""Immutable release lifecycle is anchored by one aggregate attestation."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.release_layout import payload_digest
from core.source_digest import current_source_digest
from content.release.canonical.baseline_release import build_empty_baseline_release
from verify import verify_release_lifecycle as lifecycle


RELEASE_ID = "20260715--travel-homepage-coverage--cn-zhejiang-sichuan--canary-003"
EXECUTION_IDS = [
    "20260715--travel-homepage-coverage--cn-sichuan--canary-007",
    "20260715--travel-homepage-coverage--cn-zhejiang--canary-004",
]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _fixture(tmp_path: Path) -> Path:
    release = tmp_path / RELEASE_ID
    _write_json(
        release / "payload/release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": RELEASE_ID,
            "releaseKind": "content",
            "canonicalMerkle": "sha256:" + "a" * 64,
            "executionIds": EXECUTION_IDS,
            "rolloutMilestone": "canary",
            "sourceDigest": current_source_digest().to_document(),
        },
    )
    _write_json(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": RELEASE_ID,
            "desiredRefs": {
                "creators": [],
                "entities": ["地点/景区/普陀山"],
                "posts": [],
                "tags": ["Topic/旅行"],
            },
        },
    )
    _write_json(
        release / "attestations/aggregate.json",
        {
            "schema": "quwoquan_data.aggregate_release_attestation",
            "releaseId": RELEASE_ID,
            "releaseKind": "content",
            "executionIds": EXECUTION_IDS,
            "rolloutMilestone": "canary",
            "entityCount": 1,
            "postCount": 0,
            "creatorCount": 0,
            "tagCount": 1,
            "canonicalMerkle": "sha256:" + "a" * 64,
            "sourceDigest": current_source_digest().to_document(),
            "payloadSha256": payload_digest(release),
            "recordedAt": "2026-07-15T00:00:00Z",
        },
    )
    return release


def test_release_lifecycle__accepts_schema_bound_aggregate_attestation__local_contract(
    monkeypatch, tmp_path: Path
) -> None:
    _fixture(tmp_path)
    monkeypatch.setattr(lifecycle, "RELEASE_ROOT", tmp_path)

    assert lifecycle.release_lifecycle_issues(RELEASE_ID) == []


def test_release_lifecycle__rejects_attestation_payload_drift__local_contract(
    monkeypatch, tmp_path: Path
) -> None:
    release = _fixture(tmp_path)
    monkeypatch.setattr(lifecycle, "RELEASE_ROOT", tmp_path)
    path = release / "attestations/aggregate.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["payloadSha256"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert lifecycle.release_lifecycle_issues(RELEASE_ID) == [
        f"{path}: payloadSha256 drift from immutable payload"
    ]


def test_release_lifecycle__accepts_create_once_empty_baseline__local_contract(
    tmp_path: Path,
) -> None:
    publish_root = tmp_path / "publish"
    publish_root.mkdir()
    release_root = tmp_path / "releases"
    baseline_id = "20260715--travel-homepage-coverage--cn-zhejiang-sichuan--baseline-001"

    created = build_empty_baseline_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=baseline_id,
    )
    repeated = build_empty_baseline_release(
        publish_root=publish_root,
        release_root=release_root,
        release_id=baseline_id,
    )

    assert created["releaseKind"] == "empty_baseline"
    assert created["idempotent"] is False
    assert repeated["idempotent"] is True
    assert lifecycle.release_lifecycle_issues(baseline_id, release_root=release_root) == []

    desired = json.loads(
        (release_root / baseline_id / "payload/desired_state.json").read_text(encoding="utf-8")
    )
    assert desired["desiredRefs"] == {
        "creators": [],
        "entities": [],
        "posts": [],
        "tags": [],
    }
