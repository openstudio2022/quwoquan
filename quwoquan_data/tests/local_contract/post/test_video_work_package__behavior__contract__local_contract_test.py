"""Video carrier admits only acquired, playable source video files."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from content.post.video import authoring as video_authoring
from content.post.video.codec import VideoDraftMeta, VideoWritingPack


def _source_video() -> dict[str, object]:
    return {
        "assetRef": "sources/entity__sourced_video/assets/source.mp4",
        "sourceRef": "sources/entity__sourced_video/source.json",
        "rightsRef": "sources/entity__sourced_video/rights.json",
        "mediaProbeRef": "sources/entity__sourced_video/media_probe.json",
        "watermarkEvidenceRef": (
            "sources/entity__sourced_video/watermark_evidence.json"
        ),
        "audioRightsEvidenceRef": (
            "sources/entity__sourced_video/audio_rights_evidence.json"
        ),
        "sha256": "a" * 64,
        "isOriginal": False,
        "originalCreatorName": "Example Creator",
        "platform": "wikimedia_commons",
        "sourcePostUrl": "https://commons.wikimedia.org/wiki/File:Example.webm",
        "originalAssetUrl": "https://upload.wikimedia.org/example.webm",
        "attributionText": "Example Creator, CC BY 4.0",
        "rightsBasis": "cc_by_4_0",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-03T00:00:00Z",
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        "directDownload": True,
        "accessControlBypassed": False,
        "drmDetected": False,
    }


def _brief(**extra: object) -> dict[str, object]:
    return {
        "entityRefs": ["quwoquan://entity/Example"],
        "tagRefs": ["quwoquan://tag/travel", "quwoquan://tag/video"],
        "sourceVideo": _source_video(),
        **extra,
    }


def test_video_writing_pack_accepts_only_sourced_video() -> None:
    pack, issues = VideoWritingPack.from_brief("Example_video", _brief())

    assert issues == ()
    payload = pack.to_dict()
    assert payload["sourceMode"] == "sourced_video"
    assert payload["sourceVideo"]["assetRef"] == _source_video()["assetRef"]
    assert payload["sourceVideo"]["publicationAdmission"] == "research_release"
    assert "sourceFrames" not in payload


def test_image_frame_sequence_cannot_satisfy_video_carrier() -> None:
    pack, issues = VideoWritingPack.from_brief(
        "Example_video",
        {
            "entityRefs": ["quwoquan://entity/Example"],
            "sourceFrames": [{"assetRef": "sources/image.jpg"}],
        },
    )

    assert pack.source_video is None
    assert "sourceVideo must be an admitted sourced video" in issues
    assert "sourceFrames cannot satisfy the video carrier" in issues


def test_compose_contract_has_no_image_sequence_video_mode() -> None:
    data_root = Path(__file__).resolve().parents[3]
    schema = json.loads(
        (data_root / "schema" / "content" / "compose.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert schema["properties"]["sourceMode"] == {"const": "sourced_video"}
    serialized = json.dumps(schema, ensure_ascii=False)
    assert "rights_cleared_image_sequence" not in serialized
    assert "sourceFrames" not in serialized


def test_video_author_finalizer_projects_governed_model_over_sdk_engine_label(
    monkeypatch,
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "4.draft" / "video_script.json"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}
    meta = replace(
        VideoDraftMeta.pending(
            ref="Example_video",
            cited_source_paths=("sources/example/source.json",),
        ),
        model="composer",
    )
    monkeypatch.setattr(video_authoring, "video_script_path", lambda *_args: script_path)
    monkeypatch.setattr(
        video_authoring.VideoScriptDraft,
        "load",
        lambda _path: SimpleNamespace(),
    )
    monkeypatch.setattr(
        video_authoring,
        "load_video_writing_pack",
        lambda *_args: SimpleNamespace(source_paths=("sources/example/source.json",)),
    )
    monkeypatch.setattr(video_authoring, "load_video_draft_meta", lambda *_args: meta)
    monkeypatch.setattr(
        video_authoring,
        "draft_package_dir",
        lambda *_args: script_path.parent,
    )
    monkeypatch.setattr(video_authoring, "prompt_path", lambda *_args: tmp_path / "prompt.md")
    monkeypatch.setattr(
        video_authoring,
        "draft_meta_path",
        lambda *_args: script_path.parent / "draft_meta.json",
    )
    monkeypatch.setattr(video_authoring, "sha256_file", lambda _path: "sha256:" + "a" * 64)
    monkeypatch.setattr(
        video_authoring,
        "write_json",
        lambda _path, payload: captured.update(payload),
    )
    from content.execution import runtime_contract

    monkeypatch.setattr(
        runtime_contract,
        "stage_execution_context",
        lambda _execution_id: {
            "executionId": "execution-1",
            "executionBinding": "frozen",
        },
    )

    assert video_authoring.finalize_video_author_meta(
        "execution-1",
        "Example_video",
        run_id="run-1",
        agent_id="agent-1",
        model="auto",
        provider="cursor_sdk",
    )
    assert captured["model"] == "auto"
    assert captured["provider"] == "cursor_sdk"
