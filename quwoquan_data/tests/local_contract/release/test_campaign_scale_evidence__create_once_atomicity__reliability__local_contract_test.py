from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from content.release.canonical import campaign_scale_contract
from content.release.canonical.campaign_scale_contract import (
    CampaignScaleEvidenceError,
)


def test_campaign_scale_evidence_is_atomic_under_concurrent_identical_writers(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        campaign_scale_contract,
        "assert_valid",
        lambda *_args, **_kwargs: None,
    )
    path = tmp_path / "release-evidence" / "campaign-scale.json"
    stable = {
        "schema": "quwoquan_data.test_campaign_scale_evidence",
        "evidenceId": "evidence-001",
        "sourceDigest": "sha256:" + "a" * 64,
    }

    def write_once(_index: int):
        return campaign_scale_contract._write_create_once(
            path=path,
            stable=stable,
            schema_name="test_campaign_scale_evidence",
        )[0]

    with ThreadPoolExecutor(max_workers=16) as executor:
        documents = list(executor.map(write_once, range(64)))

    frozen = json.loads(path.read_text(encoding="utf-8"))
    assert all(document == frozen for document in documents)
    assert frozen["evidenceDigest"] == campaign_scale_contract._canonical_digest(
        frozen,
        excluded="evidenceDigest",
    )
    assert list(path.parent.glob(".*.tmp")) == []


def test_campaign_scale_evidence_rejects_a_conflicting_second_writer(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        campaign_scale_contract,
        "assert_valid",
        lambda *_args, **_kwargs: None,
    )
    path = tmp_path / "release-evidence" / "campaign-scale.json"
    campaign_scale_contract._write_create_once(
        path=path,
        stable={"schema": "test", "evidenceId": "first"},
        schema_name="test_campaign_scale_evidence",
    )

    with pytest.raises(CampaignScaleEvidenceError, match="create-once.*collision"):
        campaign_scale_contract._write_create_once(
            path=path,
            stable={"schema": "test", "evidenceId": "second"},
            schema_name="test_campaign_scale_evidence",
        )
