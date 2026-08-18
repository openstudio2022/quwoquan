from __future__ import annotations

import hashlib
import io
import shutil
from pathlib import Path

import pytest
from content.execution.context import ExecutionContext
from content.execution.controller.content_plan import _auto_content_plan
from content.execution.controller.content_plan_assets import (
    _canonical_image_asset_issue,
    normalize_article_media_claims,
)
from content.execution.controller.content_plan_prep import (
    _content_capacity_gate_for_entity,
)
from content.execution.controller.stage_download_build import _run_download_fetch
from content.execution.spec_contract import ExecutionSpec
from content.release.canonical.canonical_inventory import canonical_inventory_path
from content.release.canonical.image_identity import canonical_asset_manifest_row
from content.source.source_unit import write_source_unit
from core.control_types import ExecutionStage, StageStatus
from core.data_issue import DataIssueCode
from core.image_deduplication import perceptual_hash, perceptual_hash_distance
from core.io import read_json, write_json
from core.paths import execution_entity_object_dir, execution_root
from core.source_digest import SourceDefinitionSnapshot
from PIL import Image, ImageDraw
from support.execution_manifest_fixture import ExecutionFixtureBuilder

EXECUTION_ID = (
    "20260810--travel-image-m1--test-canonical-admission--scale-901"
)
ENTITY = "图片去重测试景区"


def test_article_media_claims_downgrade_atomically_to_text_only() -> None:
    single = normalize_article_media_claims(
        (["assets/cover.jpg"], ["cover-sha"], ["source"], ["assets/cover.jpg"])
    )
    illustrated = normalize_article_media_claims(
        (
            ["assets/cover.jpg", "assets/body.jpg"],
            ["cover-sha", "body-sha"],
            ["source"],
            ["assets/cover.jpg", "assets/body.jpg"],
        )
    )

    assert single == ([], [], [], [], "text_only")
    assert illustrated[-1] == "illustrated"
    assert illustrated[3] == ["assets/cover.jpg", "assets/body.jpg"]


@pytest.fixture(autouse=True)
def _clean_execution() -> None:
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    yield
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def _pattern_bytes(pattern: str, *, image_format: str) -> bytes:
    image = Image.new("RGB", (96, 96), "white")
    draw = ImageDraw.Draw(image)
    if pattern == "split":
        draw.rectangle((0, 0, 47, 95), fill="black")
        draw.ellipse((56, 20, 88, 52), fill="gray")
    elif pattern == "checker":
        for y in range(0, 96, 12):
            for x in range(0, 96, 12):
                if (x // 12 + y // 12) % 2 == 0:
                    draw.rectangle((x, y, x + 11, y + 11), fill="black")
    else:
        raise ValueError(f"unknown image pattern: {pattern}")
    buffer = io.BytesIO()
    save_kwargs = {"quality": 92} if image_format == "JPEG" else {}
    image.save(buffer, format=image_format, **save_kwargs)
    return buffer.getvalue()


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_candidate(
    root: Path,
    *,
    payload: bytes,
    suffix: str,
) -> tuple[Path, dict[str, str]]:
    source_dir = root / "candidate-source"
    file_name = f"candidate{suffix}"
    path = source_dir / "assets" / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return source_dir, {
        "fileName": file_name,
        "sourceAssetId": "candidate-image",
        "sha256": _sha256(payload),
    }


def _write_canonical(
    publish_root: Path,
    *,
    payload: bytes,
) -> Path:
    source = publish_root.parent / "canonical-source.jpg"
    source.write_bytes(payload)
    asset = canonical_asset_manifest_row(
        {
            "assetId": "existing-image",
            "kind": "image",
            "sha256": _sha256(payload),
        },
        asset_source=source,
        mime_type="image/jpeg",
        object_key="media/objects/sha256/existing.jpg",
    )
    write_json(
        publish_root / "posts/image/画报/既有图片/1/manifest.json",
        {"contentType": "image", "assets": [asset]},
    )
    return source


@pytest.fixture
def canonical_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    publish_root = tmp_path / "publish"
    canonical = _write_canonical(
        publish_root,
        payload=_pattern_bytes("split", image_format="JPEG"),
    )
    monkeypatch.setattr("core.paths.PUBLISH_ROOT", publish_root)
    yield publish_root, canonical
    canonical_inventory_path(publish_root).unlink(missing_ok=True)


def test_shared_image_candidate_admission_rejects_exact_sha(
    tmp_path: Path,
    canonical_publish,
) -> None:
    _publish_root, canonical = canonical_publish
    payload = canonical.read_bytes()
    source_dir, row = _write_candidate(
        tmp_path,
        payload=payload,
        suffix=".jpg",
    )

    issue = _canonical_image_asset_issue(source_dir, row)

    assert "duplicated by sha256" in issue


def test_shared_image_candidate_admission_rejects_phash_with_distinct_sha(
    tmp_path: Path,
    canonical_publish,
) -> None:
    _publish_root, canonical = canonical_publish
    payload = _pattern_bytes("split", image_format="PNG")
    source_dir, row = _write_candidate(
        tmp_path,
        payload=payload,
        suffix=".png",
    )
    candidate = source_dir / "assets" / str(row["fileName"])
    assert row["sha256"] != _sha256(canonical.read_bytes())
    assert perceptual_hash_distance(
        perceptual_hash(canonical),
        perceptual_hash(candidate),
    ) <= 5

    issue = _canonical_image_asset_issue(source_dir, row)

    assert "duplicated by perceptualHash" in issue


def test_shared_image_candidate_admission_accepts_distinct_replacement(
    tmp_path: Path,
    canonical_publish,
) -> None:
    _publish_root, canonical = canonical_publish
    payload = _pattern_bytes("checker", image_format="PNG")
    source_dir, row = _write_candidate(
        tmp_path,
        payload=payload,
        suffix=".png",
    )
    candidate = source_dir / "assets" / str(row["fileName"])
    assert perceptual_hash_distance(
        perceptual_hash(canonical),
        perceptual_hash(candidate),
    ) > 5

    assert _canonical_image_asset_issue(source_dir, row) == ""


def test_capacity_gate_calls_shared_admission_and_rejects_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "execution"
    source_dir = root / "sources" / "duplicate-image"
    asset_path = source_dir / "assets" / "duplicate.jpg"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"canonical-duplicate")
    row = {
        "fileName": asset_path.name,
        "sourceAssetId": "duplicate-image",
        "sourceCollectionId": "duplicate-collection",
        "sha256": _sha256(asset_path.read_bytes()),
    }
    write_json(
        source_dir / "meta.json",
        {
            "sourceId": "duplicate-image-source",
            "researchLane": "image",
        },
    )
    (source_dir / "source.md").write_text(f"# {ENTITY}\n", encoding="utf-8")
    write_json(source_dir / "assets/index.json", {"assets": [row]})

    calls: list[tuple[Path, dict[str, str]]] = []

    def _reject_duplicate(
        candidate_source_dir: Path,
        candidate_row: dict[str, str],
    ) -> str:
        calls.append((candidate_source_dir, candidate_row))
        return "canonical image identity duplicated by sha256"

    monkeypatch.setattr(
        "content.execution.controller.content_plan_prep.execution_root",
        lambda _execution_id: root,
    )
    monkeypatch.setattr(
        "content.execution.controller.content_plan_prep.relative_execution_ref",
        lambda path, _execution_id: path.relative_to(root).as_posix(),
    )
    monkeypatch.setattr(
        "content.source.source_unit.resolve_entity_object_dir",
        lambda *_args, **_kwargs: root,
    )
    monkeypatch.setattr(
        "content.source.source_unit.iter_source_units",
        lambda _object_dir: [source_dir],
    )
    monkeypatch.setattr(
        "content.execution.controller.content_plan_assets._canonical_image_asset_issue",
        _reject_duplicate,
    )

    fixture = ExecutionFixtureBuilder(
        EXECUTION_ID,
        targets=({"entityType": "地点/景区", "name": ENTITY},),
        approved_quota=1,
    )
    spec = fixture.spec_payload()
    spec["content"]["research"]["imageCountPolicy"] = "hard_quota"
    context = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=(ENTITY,),
        spec=ExecutionSpec.from_mapping(spec),
    )

    passed, issues, diagnostics = _content_capacity_gate_for_entity(
        context,
        ENTITY,
    )

    assert calls == [(source_dir, row)]
    assert not passed
    assert any("image source shortfall" in issue for issue in issues)
    assert diagnostics["qualifiedImageAssets"] == 0
    assert diagnostics["pickedImageSources"] == 0
    assert diagnostics["imageRejects"] == {"canonical_duplicate": 1}


def _write_image_source(
    payload: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> ExecutionContext:
    fixture = ExecutionFixtureBuilder(
        EXECUTION_ID,
        targets=({"entityType": "地点/景区", "name": ENTITY},),
        approved_quota=1,
    )
    manifest = fixture.build()
    frozen_source_digest = SourceDefinitionSnapshot.from_document(
        manifest["sourceDigest"]
    )
    monkeypatch.setattr(
        "content.execution.workspace.current_source_definition_snapshot",
        lambda: frozen_source_digest,
    )
    write_source_unit(
        execution_entity_object_dir(EXECUTION_ID, "地点", "景区", ENTITY),
        ordinal=1,
        source_id="canonical_duplicate_image",
        source_md=f"# {ENTITY}\n",
        quality={
            "sourceId": "canonical_duplicate_image",
            "quality": "A-story",
            "score": 9,
        },
        platform="Wikimedia Commons",
        source_category="image_collection",
        source_kind="image_collection",
        source_role="base",
        research_lane="image",
        license_value="CC BY-SA 4.0",
        url="https://commons.wikimedia.org/wiki/File:Duplicate.jpg",
        title=f"{ENTITY}图片",
        target_ref=f"/entity/地点/景区/{ENTITY}",
        images=[
            {
                "bytes": payload,
                "ext": ".jpg",
                "slug": "duplicate",
                "url": "https://example.invalid/duplicate.jpg",
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:Duplicate.jpg",
                "caption": f"{ENTITY}图片",
                "relevance": f"画面直接呈现{ENTITY}",
                "visualSubject": ENTITY,
                "pageResolvedTitle": ENTITY,
                "sourceCollectionId": "canonical-duplicate-collection",
                "license": "CC BY-SA 4.0",
                "credit": "Test Creator",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": (
                    "https://commons.wikimedia.org/wiki/File:Duplicate.jpg"
                ),
                "usageScope": "app_publish",
            }
        ],
        execution_id=EXECUTION_ID,
        build_variants=False,
    )
    spec = fixture.spec_payload()
    spec["content"]["research"]["imageCountPolicy"] = "hard_quota"
    return ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=(ENTITY,),
        spec=ExecutionSpec.from_mapping(spec),
    )


def test_image_duplicate_blocks_prepare_content_plan_and_resume_before_publish_job(
    canonical_publish,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _publish_root, canonical = canonical_publish
    context = _write_image_source(canonical.read_bytes(), monkeypatch)
    from content.execution.recovery import download_unresolved

    monkeypatch.setattr(
        download_unresolved,
        "_write_download_availability",
        lambda *_args, **_kwargs: {
            "readyTargets": [ENTITY],
            "readyTargetCount": 1,
            "ineligibleTargets": [],
            "ineligibleTargetCount": 0,
        },
    )

    passed, issues, diagnostics = _content_capacity_gate_for_entity(
        context,
        ENTITY,
    )
    content_plan_issues = _auto_content_plan(
        context,
        context.spec.to_dict(),
    )
    first = _run_download_fetch(context)
    resumed = _run_download_fetch(context)

    assert not passed
    assert any("image source shortfall" in issue for issue in issues)
    assert diagnostics["qualifiedImageAssets"] == 0
    assert diagnostics["pickedImageSources"] == 0
    assert diagnostics["imageRejects"] == {"canonical_duplicate": 1}
    assert [issue.code for issue in content_plan_issues] == [
        DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL
    ]
    for result in (first, resumed):
        assert result.status is StageStatus.FAILED
        assert result.fallback_stage is ExecutionStage.DOWNLOAD_PLAN
        assert [issue.code for issue in result.issue_records] == [
            DataIssueCode.SOURCE_RETAINED_SHORTFALL
        ]
    queue_root = execution_root(EXECUTION_ID) / "_shared/object_queue"
    publish_jobs = [
        read_json(path)
        for path in queue_root.glob("*.json")
        if read_json(path).get("stage") == "publish"
    ]
    assert publish_jobs == []
    assert not (
        execution_root(EXECUTION_ID) / "0.plan/reliabletask_job_sets/publish"
    ).exists()
