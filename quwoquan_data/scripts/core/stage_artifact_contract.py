"""五阶段产物唯一契约：common contract → lane adapter。"""

from __future__ import annotations

from typing import Final

from core.control_types import OBJECT_STAGE_SEQUENCE


STAGES: Final[tuple[str, ...]] = tuple(
    stage.value for stage in OBJECT_STAGE_SEQUENCE
)
LANES: Final[tuple[str, ...]] = ("homepage", "article", "image", "video")

COMMON_STAGE_ARTIFACTS: Final[dict[str, tuple[str, ...]]] = {
    "1.download": ("source_refs.json",),
    "2.quality": ("quality_analysis.json",),
    "4.draft": (
        "author_job_packet.json",
        "prompt.md",
        "prompt_snapshot.json",
        "draft_meta.json",
        "author_self_check.json",
        "agent_result_envelope.json",
    ),
    "5.review": (
        "deterministic_gate.json",
        "reviewer_result.json",
        "media_ref_review.json",
        "finalization_report.json",
        "attestation.json",
        "evidence_index.json",
    ),
}

LANE_ADAPTERS: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "homepage": {
        "3.compose": ("entity_page_input.json",),
        "4.draft": ("page.md",),
        "final": ("_entity.json", "page.md", "manifest.json"),
    },
    "article": {
        "3.compose": ("writing_pack.json",),
        "4.draft": ("draft.article.md",),
        "final": ("article.md", "manifest.json"),
    },
    "image": {
        "3.compose": ("writing_pack.json",),
        "4.draft": (),
        "final": ("manifest.json",),
    },
    "video": {
        "3.compose": ("writing_pack.json",),
        "4.draft": (),
        "final": ("manifest.json",),
    },
}

SOURCE_UNIT_ARTIFACTS: Final[tuple[str, ...]] = (
    "meta.json",
    "source.md",
    "source.clean.md",
    "source.layout.json",
    "source.quality.json",
    "assets/index.json",
)

PROCESS_ARTIFACT_NAMES: Final[frozenset[str]] = frozenset(
    {
        "prompt.md",
        "prompt_snapshot.json",
        "author_job_packet.json",
        "author_self_check.json",
        "agent_result_envelope.json",
        "draft_meta.json",
        "repair_report.json",
        "failure.json",
        "reviewer_result.json",
        "deterministic_gate.json",
        "media_ref_review.json",
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
