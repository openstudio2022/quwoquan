"""三步产物唯一契约：acquire(1.download) → author(4.draft) → review(5.review) → final。"""

from __future__ import annotations

from typing import Final

from core.control_types import AUTHOR_ARTIFACT_BY_CARRIER, OBJECT_STAGE_SEQUENCE


STAGES: Final[tuple[str, ...]] = tuple(
    stage.value for stage in OBJECT_STAGE_SEQUENCE
)
LANES: Final[tuple[str, ...]] = ("homepage", "article", "image", "video")

COMMON_STAGE_ARTIFACTS: Final[dict[str, tuple[str, ...]]] = {
    "1.download": ("source_refs.json",),
    "5.review": ("content_review.json",),
}

LANE_ADAPTERS: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "homepage": {
        "4.draft": (AUTHOR_ARTIFACT_BY_CARRIER["homepage"],),
        "final": ("_entity.json", "page.md", "manifest.json"),
    },
    "article": {
        "4.draft": (AUTHOR_ARTIFACT_BY_CARRIER["article"],),
        "final": ("article.md", "manifest.json"),
    },
    "image": {
        "4.draft": (AUTHOR_ARTIFACT_BY_CARRIER["image"],),
        "final": ("manifest.json",),
    },
    "video": {
        "4.draft": (AUTHOR_ARTIFACT_BY_CARRIER["video"],),
        "final": ("manifest.json",),
    },
}

# 媒体来源的字节就是快照本身（摘要记在 meta.rawSha256），只有页面来源另落 snapshot.raw。
SOURCE_UNIT_ARTIFACTS: Final[tuple[str, ...]] = (
    "meta.json",
    "source.md",
    "assets/index.json",
)

# canonical publish/release 不得含 execution 过程文件。
CANONICAL_FORBIDDEN_PROCESS_ARTIFACT_NAMES: Final[frozenset[str]] = frozenset(
    {
        "quality_analysis.json",
        "writing_pack.json",
        "entity_page_input.json",
        "author_self_check.json",
        "agent_result_envelope.json",
        "draft_meta.json",
        "rubric_review.json",
        "reviewer_result.json",
        "media_ref_review.json",
        "attestation.json",
        "repair_report.json",
        "failure.json",
        "deterministic_gate.json",
        "runbook.md",
        "rollout.json",
        "rollback.json",
        "slo.json",
        "import-content.json",
        "import-homepage.json",
    }
)


def required_stage_artifacts(lane: str) -> dict[str, tuple[str, ...]]:
    if lane not in LANE_ADAPTERS:
        raise ValueError(f"unsupported lane: {lane}")
    adapter = LANE_ADAPTERS[lane]
    return {
        stage: (
            *COMMON_STAGE_ARTIFACTS.get(stage, ()),
            *adapter.get(stage, ()),
        )
        for stage in STAGES
    }


def required_final_artifacts(lane: str) -> tuple[str, ...]:
    if lane not in LANE_ADAPTERS:
        raise ValueError(f"unsupported lane: {lane}")
    return LANE_ADAPTERS[lane]["final"]
