from __future__ import annotations

from types import SimpleNamespace

from content.execution.agent.outcome import AgentRunOutcome
from content.execution.controller import homepage_author_evidence
from content.post import object_index
from content.post.article import draft_io
from core.control_types import AgentProvider

# 对种子 token 计算的真实 sha256，保持 canonical digest 形态。
_PROMPT_DIGEST = (  # sha256("prompt")
    "sha256:cf07194ee232eb531e15f690000d19846dea69cf05504782658afcfacb9228a2"
)
_PACK_DIGEST = (  # sha256("pack")
    "sha256:4862f447f2c7f272fa2f4aaf89dadb3b1ac09105bd5864f8d1a0c9452bb0a226"
)
_SOURCES_DIGEST = (  # sha256("sources")
    "sha256:878a52fc5ff6a57d50b7b870aa51637a3dfd38fc22352a39f95a3c292eb976d5"
)
_DRAFT_DIGEST = (  # sha256("draft")
    "sha256:7743ce348d9284d677a185f33295b92266cc435a5b5f775029b300066d26693a"
)
_STALE_DIGEST = (  # sha256("stale")：格式合法但与当前 provenance 漂移的旧摘要
    "sha256:a03f2386ae06b21109577020844df367857b72c2fcce384c1896fed98a89c82b"
)


def _finalized_meta() -> dict[str, object]:
    return {
        "ref": "乌镇_image",
        "generator": "image_evidence_pack",
        "status": "completed",
        "provider": "cursor_sdk",
        "model": "grok-4.5",
        "agentRunId": "run-image-one",
        "agentId": "agent-image-one",
        "title": "",
        "caption": "Wuzhen Old City, Shanghai, China",
        "creativePlan": {
            "concepts": [{"planId": "one"}, {"planId": "two"}],
            "selectedPlanId": "one",
            "selectionReason": "preserve frozen caption",
        },
        "selfCritique": {
            "readerPromise": "visual",
            "titlePromise": "blank",
            "informationDensity": "single image",
            "evidenceBoundary": "frozen source",
            "personaBoundary": "editorial",
        },
        "citedSourcePaths": ["sources/openverse/source.md"],
        "promptSha256": _PROMPT_DIGEST,
        "writingPackSha256": _PACK_DIGEST,
        "sourceBundleSha256": _SOURCES_DIGEST,
        "draftSha256": _DRAFT_DIGEST,
        "selfCheck": {"status": "passed", "issues": []},
        "finalizedFromAgentRunHistory": True,
        "updatedAt": "2026-08-12T00:00:00Z",
    }


def _arrange(monkeypatch, meta: dict[str, object], writes: list[dict[str, object]]) -> None:
    outcome = AgentRunOutcome.finished(
        provider=AgentProvider.CURSOR_SDK,
        run_id="run-image-one",
        agent_id="agent-image-one",
    )
    monkeypatch.setattr(
        homepage_author_evidence,
        "_managed_finished_author_outcomes_by_ref",
        lambda _state: {"乌镇_image": outcome},
    )
    monkeypatch.setattr(object_index, "iter_content_refs", lambda _execution_id: ["乌镇_image"])
    monkeypatch.setattr(draft_io, "read_draft_meta", lambda *_args: dict(meta))
    monkeypatch.setattr(
        draft_io,
        "read_writing_pack",
        lambda *_args: {
            "carrier": "image",
            "title": "",
            "caption": "Wuzhen Old City, Shanghai, China",
            "sourcePaths": ["sources/openverse/source.md"],
        },
    )
    monkeypatch.setattr(
        draft_io,
        "compute_draft_provenance_facts",
        lambda *_args, **_kwargs: {
            "promptSha256": _PROMPT_DIGEST,
            "writingPackSha256": _PACK_DIGEST,
            "sourceBundleSha256": _SOURCES_DIGEST,
            "draftSha256": _DRAFT_DIGEST,
        },
    )
    monkeypatch.setattr(draft_io, "draft_meta_path", lambda *_args: "draft_meta.json")
    monkeypatch.setattr(
        homepage_author_evidence,
        "write_json",
        lambda _path, document: writes.append(dict(document)),
    )


def test_finalized_image_meta_is_not_rewritten(monkeypatch) -> None:
    writes: list[dict[str, object]] = []
    _arrange(monkeypatch, _finalized_meta(), writes)

    finalized = homepage_author_evidence._finalize_existing_managed_author_outputs(
        SimpleNamespace(execution_id="image-execution", model="grok-4.5"),
        SimpleNamespace(),
    )

    assert finalized == 0
    assert writes == []


def test_finalized_image_meta_is_rewritten_when_provenance_drifts(monkeypatch) -> None:
    writes: list[dict[str, object]] = []
    meta = _finalized_meta()
    meta["sourceBundleSha256"] = _STALE_DIGEST
    _arrange(monkeypatch, meta, writes)

    finalized = homepage_author_evidence._finalize_existing_managed_author_outputs(
        SimpleNamespace(execution_id="image-execution", model="grok-4.5"),
        SimpleNamespace(),
    )

    assert finalized == 1
    assert writes[0]["sourceBundleSha256"] == _SOURCES_DIGEST
