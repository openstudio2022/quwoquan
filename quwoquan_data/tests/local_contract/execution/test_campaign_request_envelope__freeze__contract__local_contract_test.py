"""Generic campaign request envelopes freeze once and validate schema."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import content.execution.campaign.request_envelope as envelopes
import pytest
from content.execution.campaign import request_envelope_build
from content.execution.campaign.scale import CampaignScaleError, resolve_campaign_scale
from core.io import read_json
from support.campaign_request_envelope_fixture import (
    _expected_count,
    _patch_envelope_deps,
    _pool_kwargs,
    _wave_targets,
)
from support.semantic_preflight_fixture import ready_semantic_preflight


def test_campaign_source_freeze_allows_dirty_tree_when_content_digest_is_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = {
        "algorithm": "sha256",
        "digest": "sha256:" + "a" * 64,
        "inputs": ["quwoquan_data/scripts"],
    }
    monkeypatch.setattr(
        envelopes,
        "current_source_digest",
        lambda **_kwargs: SimpleNamespace(to_document=lambda: dict(frozen)),
    )
    monkeypatch.setattr(
        envelopes.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Git cleanliness must not be queried"),
    )

    envelopes._require_stable_source_inputs(frozen, repo_root=tmp_path)


def test_campaign_source_freeze_blocks_content_digest_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = {
        "algorithm": "sha256",
        "digest": "sha256:" + "a" * 64,
        "inputs": ["quwoquan_data/scripts"],
    }
    observed = {**frozen, "digest": "sha256:" + "b" * 64}
    monkeypatch.setattr(
        envelopes,
        "current_source_digest",
        lambda **_kwargs: SimpleNamespace(to_document=lambda: dict(observed)),
    )

    with pytest.raises(ValueError, match="changed during freeze"):
        envelopes._require_stable_source_inputs(frozen, repo_root=tmp_path)


def test_campaign_request_envelope_freeze__contract__local_contract_test(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    monkeypatch.chdir(repo)
    _patch_envelope_deps(monkeypatch)

    first = envelopes.write_scale_envelopes(
        "M100",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path,
        day="20260731",
        target_names=_wave_targets(),
        **_pool_kwargs(tmp_path),
    )
    assert set(first) == {"homepage", "article", "image", "video"}
    homepage = first["homepage"]
    payload = homepage.read_text(encoding="utf-8")
    assert "submit-only" in payload
    assert "执行实体内容生成" in payload
    assert '"quota": 12' in payload
    assert f'"count": {_expected_count(12)}' in payload
    assert '"vertical": "travel"' in payload
    assert "travel/M100/china/sequence-001/homepage.json" in homepage.as_posix()
    video_payload = read_json(first["video"])
    assert video_payload["quota"] == 10
    assert video_payload["count"] == _expected_count(10)

    second = envelopes.write_scale_envelopes(
        "M100",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path,
        day="20260731",
        target_names=_wave_targets(),
        **_pool_kwargs(tmp_path),
    )
    assert second["homepage"] == homepage

    named = envelopes.write_campaign_envelopes(
        scales=["M1", "M100000"],
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path,
        day="20260731",
    )
    assert set(named) == {"M1", "M100000"}
    first_scope = envelopes.write_scale_envelopes(
        "M1",
        region_ref="china",
        topic="first-scope",
        repo_root=repo,
        output_root=tmp_path,
        day="20260731",
    )
    second_scope = envelopes.write_scale_envelopes(
        "M1",
        region_ref="china",
        topic="second-scope",
        repo_root=repo,
        output_root=tmp_path,
        day="20260731",
    )
    assert first_scope["homepage"] != second_scope["homepage"]
    assert "china-first-scope/sequence-001" in first_scope["homepage"].as_posix()
    assert "china-second-scope/sequence-001" in second_scope["homepage"].as_posix()
    m1 = envelopes.build_envelope(
        scale="M1",
        carrier="homepage",
        region_ref="china",
        repo_root=repo,
        day="20260731",
    )
    assert m1["quota"] == 1
    assert m1["count"] == _expected_count(1)
    assert m1["scale"] == "M1"
    assert m1["executionId"].endswith("--china--scale-001")
    assert "-m1--" in m1["executionId"]

    m100000 = envelopes.build_envelope(
        scale="M100000",
        carrier="video",
        region_ref="china",
        repo_root=repo,
        day="20260731",
    )
    assert m100000["quota"] == 100000
    assert m100000["count"] == _expected_count(100000)

    arbitrary = envelopes.build_envelope(
        scale="M37",
        carrier="article",
        region_ref="china",
        topic="zhejiang",
        repo_root=repo,
        day="20260731",
    )
    assert arbitrary["quota"] == 37
    assert arbitrary["count"] == _expected_count(37)
    assert arbitrary["topic"] == "zhejiang"
    assert arbitrary["regionRef"] == "china"
    assert "--china-zhejiang--" in arbitrary["executionId"]
    assert arbitrary["familyRef"] == "content/travel/article/article"

    by_quota = envelopes.write_campaign_envelopes(
        quota=37,
        region_ref="china",
        topic="zhejiang",
        repo_root=repo,
        output_root=tmp_path / "by-quota",
        day="20260731",
    )
    assert set(by_quota) == {"M37"}

    with pytest.raises(CampaignScaleError, match="GATE_BLOCK"):
        resolve_campaign_scale(quota=0)
    with pytest.raises(CampaignScaleError, match="GATE_BLOCK"):
        resolve_campaign_scale(scale="M100001")
    with pytest.raises(CampaignScaleError, match="GATE_BLOCK"):
        resolve_campaign_scale(quota=100001)
    with pytest.raises(CampaignScaleError, match="GATE_BLOCK"):
        envelopes.build_envelope(
            scale="M100001",
            carrier="homepage",
            region_ref="china",
            repo_root=repo,
            day="20260731",
        )


def test_campaign_envelope_rejects_partial_explicit_target_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    with pytest.raises(ValueError, match="at least the governed quota"):
        envelopes.build_envelope(
            scale="M2",
            carrier="homepage",
            region_ref="china",
            target_names=("杭州西湖",),
            repo_root=repo,
            day="20260807",
        )


def test_campaign_envelope_freeze_rejects_cross_lane_handoff_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    def bind(carrier: str, *_args, **_kwargs):
        return (
            [],
            {
                "handoffId": "local-contract",
                "handoffRevision": 1 if carrier == "homepage" else 2,
                "handoffRef": (
                    "data/local/workspace/content-pre-acquisition-handoffs/"
                    "local-contract/revision-001.json"
                ),
                "handoffDigest": "sha256:" + "9" * 64,
                "handoffFileDigest": "sha256:" + "8" * 64,
            },
        )

    monkeypatch.setattr(
        request_envelope_build,
        "freeze_carrier_pre_acquisition_inputs",
        bind,
    )

    with pytest.raises(ValueError, match="handoff identity changed"):
        envelopes.write_scale_envelopes(
            "M100",
            region_ref="china",
            repo_root=repo,
            output_root=tmp_path,
            day="20260731",
            target_names=_wave_targets(),
            **_pool_kwargs(tmp_path),
        )
    assert not tuple(tmp_path.rglob("*.json"))


def test_campaign_envelope_freeze_rejects_receipt_outside_frozen_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    preflight_root = tmp_path / "semantic-output"
    preflight_path, _binding = ready_semantic_preflight(
        "cursor_auto",
        output_root=preflight_root,
    )
    receipt = read_json(preflight_path)
    outside = (
        datetime.fromisoformat(str(receipt["validUntil"]).replace("Z", "+00:00"))
        + timedelta(seconds=1)
    ).isoformat()
    monkeypatch.setattr(envelopes, "_utc_now", lambda: outside)

    with pytest.raises(ValueError, match="admission timestamp.*validity window"):
        envelopes.build_envelope(
            scale="M3",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260805",
            semantic_selection_id="cursor_auto",
            semantic_preflight_receipt=preflight_path,
            semantic_preflight_output_root=preflight_root,
        )
