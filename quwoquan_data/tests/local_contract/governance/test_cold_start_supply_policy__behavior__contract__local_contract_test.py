"""Cold-start supply is a typed, master-list-backed launch contract."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from core.control_types import RolloutMilestone
from core.source_digest import current_source_digest
from governance.coverage import cold_start_supply
from governance.coverage.cold_start_supply import (
    cold_start_execution_parameters,
    load_cold_start_supply_policy,
)


def test_cold_start_supply_policy_closes_twenty_targets_and_sixty_posts() -> None:
    policy = load_cold_start_supply_policy()
    counts = Counter(target.province for target in policy.targets)

    assert counts == {"浙江省": 10, "四川省": 10}
    assert policy.content_mix.total_per_entity == 3
    assert policy.expected_post_count == 60
    assert policy.feed_minimum_posts == 20


def test_cold_start_video_delivery_is_vertical_h264_with_required_evidence() -> None:
    video = load_cold_start_supply_policy().video_delivery

    assert (video.width, video.height, video.aspect_ratio) == (1080, 1920, "9:16")
    assert (video.container, video.codec, video.pixel_format) == ("mp4", "h264", "yuv420p")
    assert (
        video.frames_per_second,
        video.segment_duration_seconds,
        video.minimum_duration_seconds,
        video.maximum_duration_seconds,
    ) == (24, 2, 6, 30)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_homepage_binding(
    tmp_path: Path,
    monkeypatch,
    *,
    execution_id: str,
    refs: tuple[str, ...],
) -> None:
    publish_root = tmp_path / "publish"
    for ref in refs:
        object_root = publish_root / "entities" / ref
        object_root.mkdir(parents=True, exist_ok=True)
        (object_root / "page.md").write_text("正文", encoding="utf-8")
        _write_json(
            object_root / "manifest.json",
            {
                "schema": "quwoquan_data.entity_object",
                "executionId": execution_id,
                "entityRef": f"/entity/{ref}",
                "sourceDigest": current_source_digest().to_document(),
            },
        )
    monkeypatch.setattr(cold_start_supply, "PUBLISH_ROOT", publish_root)


def test_cold_start_execution_accepts_m1_and_m2_homepage_batches(monkeypatch) -> None:
    bindings: list[tuple[RolloutMilestone, str]] = []

    monkeypatch.setattr(
        cold_start_supply,
        "_homepage_execution_target_names",
        lambda *, identity, homepage_execution_id, contract: (
            bindings.append((identity.milestone, homepage_execution_id))
            or ("批次对象一", "批次对象二")
        ),
    )

    for milestone in ("m1", "m2"):
        parameters = cold_start_execution_parameters(
            execution_id=(
                f"20260718--travel-video-cold-start--cn-zhejiang--{milestone}-001"
            ),
            homepage_execution_id=(
                f"20260718--travel-homepage-coverage--cn-zhejiang--{milestone}-901"
            ),
        )
        assert parameters.target_names == ("批次对象一", "批次对象二")

    assert bindings == [
        (
            RolloutMilestone.M1,
            "20260718--travel-homepage-coverage--cn-zhejiang--m1-901",
        ),
        (
            RolloutMilestone.M2,
            "20260718--travel-homepage-coverage--cn-zhejiang--m2-901",
        ),
    ]


def test_canary_cold_start_uses_contract_canary_targets_after_homepage_publish(
    monkeypatch, tmp_path
) -> None:
    """canary 三载体入口：目标锁定金丝雀实体，前置为主页已 canonical。"""
    from content.release.canonical.rollout_contract import load_rollout_contract

    contract = load_rollout_contract()
    zhejiang = contract.province_for_scope("cn-zhejiang")
    homepage_execution_id = (
        "20260719--travel-homepage-coverage--cn-zhejiang--canary-901"
    )
    _write_homepage_binding(
        tmp_path,
        monkeypatch,
        execution_id=homepage_execution_id,
        refs=zhejiang.canary_entity_refs,
    )

    parameters = cold_start_execution_parameters(
        execution_id="20260719--travel-article-cold-start--cn-zhejiang--canary-001",
        homepage_execution_id=homepage_execution_id,
    )

    assert parameters.province == "浙江省"
    assert parameters.target_names == zhejiang.canary_targets
    assert parameters.limit == len(zhejiang.canary_targets)


def test_cold_start_blocks_without_explicit_homepage_execution_binding() -> None:
    try:
        cold_start_execution_parameters(
            execution_id="20260719--travel-image-cold-start--cn-sichuan--canary-001",
        )
    except ValueError as exc:
        assert "--homepage-execution-id" in str(exc)
    else:
        raise AssertionError("cold-start without homepage execution binding must block")


def test_canary_cold_start_blocks_when_bound_homepages_are_not_canonical(
    monkeypatch, tmp_path
) -> None:
    homepage_execution_id = (
        "20260719--travel-homepage-coverage--cn-sichuan--canary-901"
    )
    monkeypatch.setattr(cold_start_supply, "PUBLISH_ROOT", tmp_path / "publish")
    try:
        cold_start_execution_parameters(
            execution_id="20260719--travel-image-cold-start--cn-sichuan--canary-001",
            homepage_execution_id=homepage_execution_id,
        )
    except ValueError as exc:
        assert "canonical homepage" in str(exc)
    else:
        raise AssertionError("cold-start without bound canonical homepages must block")
