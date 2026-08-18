# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.campaign import external_input_runtime as campaign_external_input_runtime
from content.execution.controller.execute import materialization
from content.execution.controller.execute.materialization import (
    _video_source_qualification_binding,
    _video_source_qualifier,
)
from content.execution.planning.source_selection import TargetSourceCandidate
from content.source import professional_video_spec_index
from content.source.research import auto_plan_video


class _VideoContext:
    def has_kind(self, _kind: str) -> bool:
        return True

    def receipt_refs(self, _kind: str) -> list[str]:
        return ["receipts/frozen-video.json"]

    def acquisition_root(self, _kind: str) -> Path:
        return Path("/capsule/external-inputs/video")


def _target(name: str = "西湖") -> TargetSourceCandidate:
    return TargetSourceCandidate(
        name=name,
        aliases=("杭州西湖",),
        geo_tag_ref="Topic/地理/中国/浙江/杭州",
    )


def test_frozen_professional_video_qualifier_bypasses_commons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        campaign_external_input_runtime,
        "bound_runtime_external_input_context",
        lambda *_args, **_kwargs: _VideoContext(),
    )
    observed: dict[str, object] = {}

    def acquired(
        receipt_refs: list[str],
        *,
        entity_id: str,
        root: Path,
    ) -> list[dict[str, object]]:
        observed.update(
            receipt_refs=receipt_refs,
            entity_id=entity_id,
            root=root,
        )
        return [
            {
                "title": "西湖热门旅行实拍",
                "assetUrl": "cas://sha256/" + "a" * 64,
            }
        ]

    monkeypatch.setattr(
        professional_video_spec_index,
        "acquired_video_specs_for_entity",
        acquired,
    )
    monkeypatch.setattr(
        auto_plan_video,
        "discover_commons_sourced_videos",
        lambda *_args, **_kwargs: pytest.fail(
            "Commons must not preempt a frozen professional-video receipt"
        ),
    )
    result = _video_source_qualifier(
        "20260805--travel-video-m100--china--scale-301",
        _target(),
    )
    assert result.accepted is True
    assert result.qualified_source is not None
    assert result.qualified_source.to_dict()["url"].startswith("cas://sha256/")
    assert observed == {
        "receipt_refs": ["receipts/frozen-video.json"],
        "entity_id": "西湖",
        "root": Path("/capsule/external-inputs/video"),
    }


def test_frozen_professional_video_missing_entity_fails_closed_without_commons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        campaign_external_input_runtime,
        "bound_runtime_external_input_context",
        lambda *_args, **_kwargs: _VideoContext(),
    )
    monkeypatch.setattr(
        professional_video_spec_index,
        "acquired_video_specs_for_entity",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        auto_plan_video,
        "discover_commons_sourced_videos",
        lambda *_args, **_kwargs: pytest.fail(
            "Commons fallback is forbidden after an external receipt is frozen"
        ),
    )
    result = _video_source_qualifier(
        "20260805--travel-video-m100--china--scale-302",
        _target("未覆盖实体"),
    )
    assert result.accepted is False
    assert result.rejection_code is not None


def test_video_qualifier_keeps_commons_fallback_without_external_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        campaign_external_input_runtime,
        "bound_runtime_external_input_context",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        auto_plan_video,
        "discover_commons_sourced_videos",
        lambda *_args, **_kwargs: [
            {"assetUrl": "https://upload.wikimedia.org/video.webm"}
        ],
    )
    result = _video_source_qualifier(
        "20260805--travel-video-m100--china--scale-303",
        _target(),
    )
    assert result.accepted is True


def test_video_binding_builds_one_verified_index_for_all_qualifier_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        campaign_external_input_runtime,
        "bound_runtime_external_input_context",
        lambda *_args, **_kwargs: _VideoContext(),
    )
    builds: list[tuple[tuple[str, ...], Path]] = []
    lookups: list[tuple[str, ...]] = []

    class FakeIndex:
        entity_names = ("西湖", "都江堰")
        accepted_asset_count = 3
        work_unit_candidates = ()

        def specs_for_names(self, entity_names: tuple[str, ...]):
            lookups.append(entity_names)
            if "西湖" not in entity_names:
                return []
            return [
                {
                    "title": "西湖热门旅行实拍",
                    "assetUrl": "cas://sha256/" + "a" * 64,
                }
            ]

    def build(receipt_refs, *, root, work_unit_bindings):
        assert work_unit_bindings == {}
        builds.append((tuple(receipt_refs), root))
        return FakeIndex()

    monkeypatch.setattr(
        professional_video_spec_index,
        "build_acquired_video_spec_index",
        build,
    )
    monkeypatch.setattr(
        materialization,
        "_video_work_unit_bindings",
        lambda *_args, **_kwargs: {},
    )

    binding = _video_source_qualification_binding(
        "20260814--travel-video-workload-video-15--china--scale-002"
    )
    assert binding.candidate_names == ("西湖", "都江堰")
    assert binding.available_supply_count == 3
    assert binding.qualifier(_target()).accepted is True
    assert binding.qualifier(
        TargetSourceCandidate(
            name="未覆盖实体",
            aliases=(),
            geo_tag_ref="Topic/地理/中国",
        )
    ).accepted is False
    assert builds == [
        (
            ("receipts/frozen-video.json",),
            Path("/capsule/external-inputs/video"),
        )
    ]
    assert lookups == [("西湖", "杭州西湖"), ("未覆盖实体",)]
