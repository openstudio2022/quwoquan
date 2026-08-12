from __future__ import annotations

from types import SimpleNamespace

from content.execution.agent.outcome import AgentRunOutcome
from content.execution.controller import homepage_author_evidence
from content.post import object_index
from content.post.article import draft_io
from core.control_types import AgentProvider


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
        "promptSha256": "sha256:prompt",
        "writingPackSha256": "sha256:pack",
        "sourceBundleSha256": "sha256:sources",
        "draftSha256": "sha256:draft",
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
            "promptSha256": "sha256:prompt",
            "writingPackSha256": "sha256:pack",
            "sourceBundleSha256": "sha256:sources",
            "draftSha256": "sha256:draft",
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
    meta["sourceBundleSha256"] = "sha256:stale"
    _arrange(monkeypatch, meta, writes)

    finalized = homepage_author_evidence._finalize_existing_managed_author_outputs(
        SimpleNamespace(execution_id="image-execution", model="grok-4.5"),
        SimpleNamespace(),
    )

    assert finalized == 1
    assert writes[0]["sourceBundleSha256"] == "sha256:sources"
