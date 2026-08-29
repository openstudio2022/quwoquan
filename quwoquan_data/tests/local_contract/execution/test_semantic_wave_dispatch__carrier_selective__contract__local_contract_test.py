# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-011
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-024.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-024.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-024.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-024.t4
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.release.canonical.pool_inspection import inspect_pool
from content.release.canonical.pool_source_ready_input import load_source_ready_input
from content.release.canonical.semantic_wave_dispatch import (
    DISPATCH_COLLISION,
    DISPATCH_EMPTY,
    DISPATCH_INVALID,
    SemanticWaveDispatchError,
    build_semantic_wave_dispatch,
    write_create_once_semantic_wave_dispatch,
)
from content.source.research.scale_source_pool import build_scale_source_pool_plan
from content.source.research.scale_source_pool_runtime import (
    frozen_scale_source_pool_targets,
)
from core.io import write_json
from core.schema import assert_valid
from support.capacity_calibration_fixture import write_synthetic_capacity_receipt
from support.scale_source_pool_projection_fixture import _media_admission_row
from support.semantic_preflight_fixture import ready_semantic_preflight

IDENTITY = {
    "sourceRevision": "sha256:" + "a" * 64,
    "sourceDigest": "sha256:" + "b" * 64,
    "entityCatalogDigest": "sha256:" + "c" * 64,
}
EVIDENCE = {
    "sourceUnit": ("shared/source-unit.json", b'{"kind":"source-unit"}\n'),
    "acquisition": ("shared/acquisition.json", b'{"kind":"acquisition"}\n'),
    "rights": ("shared/rights.json", b'{"kind":"rights"}\n'),
    "quality": ("shared/quality.json", b'{"kind":"quality"}\n'),
}


def _sha_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha_text(value: str) -> str:
    return _sha_bytes(value.encode("utf-8"))


def _attribution(carrier: str, index: int) -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": f"source-{index}",
        "platform": f"{carrier}-source",
        "sourcePostUrl": f"https://source.example/{carrier}/{index}",
        "originalAssetUrl": f"https://source.example/{carrier}/{index}.jpg",
        "attributionText": f"source-{index} / {carrier}-source",
        "rightsBasis": "public research reference",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-11T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
        "derivedModifications": [],
    }


def _candidate(
    carrier: str, index: int, *, evidence_root: Path | None = None
) -> dict[str, object]:
    name = f"{carrier}-{index:03d}"
    prefix = {
        "homepage": "entities/地点/景区",
        "article": "posts/article/攻略",
        "image": "posts/image/画报",
    }[carrier]
    row: dict[str, object] = {
        "candidateId": name,
        "carrier": carrier,
        "objectRef": f"{prefix}/{name}/1",
        "entityRef": f"/entity/地点/景区/{name}",
        "observedEntityRef": f"/entity/地点/景区/{name}",
        **IDENTITY,
        "provider": f"{carrier}-source",
        "contentSha256": _sha_text(f"content:{name}"),
        "acquisitionStatus": "acquired",
        "rightsStatus": "unverified",
        "distributionDecision": "research_allowed",
        "qualityStatus": "passed",
        "generated": False,
        "publishMediaMode": "illustrated",
        "videoReadiness": None,
    }
    if carrier in {"homepage", "article"}:
        # homepage/article 走 source-ready evidence 全套件。
        row.update(
            {
                "sourceUnitRef": EVIDENCE["sourceUnit"][0],
                "sourceUnitDigest": _sha_text(f"source:{name}"),
                "sourceUnitFileSha256": _sha_bytes(EVIDENCE["sourceUnit"][1]),
                "acquisitionRef": EVIDENCE["acquisition"][0],
                "acquisitionDigest": _sha_text(f"acquisition:{name}"),
                "acquisitionFileSha256": _sha_bytes(EVIDENCE["acquisition"][1]),
                "rightsRef": EVIDENCE["rights"][0],
                "rightsDigest": _sha_text(f"rights:{name}"),
                "rightsFileSha256": _sha_bytes(EVIDENCE["rights"][1]),
                "qualityRef": EVIDENCE["quality"][0],
                "qualityDigest": _sha_text(f"quality:{name}"),
                "qualityFileSha256": _sha_bytes(EVIDENCE["quality"][1]),
                "playabilityRef": None,
                "playabilityDigest": None,
                "playabilityFileSha256": None,
                "sourceReadyEvidenceRootRef": ".",
                "sourceAttribution": _attribution(carrier, index),
            }
        )
    else:
        # image/video 只声明 source admission 指针，evidence 套件字段禁止出现。
        # 指针必须指向真实铸出的 receipt：池在校验期把 receipt 与引用它的候选逐字段
        # 比对（objectRef/assetKind/contentSha256/rightsStatus/distributionDecision），
        # 因此 receipt 只能按该候选自己的对象形态铸出。
        if evidence_root is None:
            raise AssertionError("media candidate requires an evidence root")
        admission = _media_admission_row(
            evidence_root=evidence_root,
            carrier=carrier,
            index=index,
            provider=f"{carrier}-source",
            candidate_id=name,
            object_ref=str(row["objectRef"]),
        )
        row.update(
            {
                field: admission[field]
                for field in (
                    "sourceAdmissionRef",
                    "sourceAdmissionDigest",
                    "contentSha256",
                    "rightsStatus",
                    "distributionDecision",
                )
            }
        )
    return row


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    output = tmp_path / "output"
    publish = tmp_path / "publish"
    evidence = output / "data/source-pools/evidence"
    for ref, body in EVIDENCE.values():
        path = evidence / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    candidates = [
        *(_candidate("homepage", index) for index in range(24)),
        *(_candidate("article", index) for index in range(12)),
        *(
            _candidate("image", index, evidence_root=evidence)
            for index in range(12)
        ),
    ]
    plan = build_scale_source_pool_plan(
        pool_id="carrier-selective-m100-wave",
        target_scale="M100",
        created_at="2026-08-11T00:00:00Z",
        candidates=candidates,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )
    plan_ref = "data/source-pools/m100-current-wave.json"
    write_json(output / plan_ref, plan)
    source_input, source_candidates = load_source_ready_input(
        output_root=output,
        publish_root=publish,
        milestone="M100",
        source_pool_ref=plan_ref,
        evidence_root_ref=evidence.relative_to(output).as_posix(),
    )
    inspection = inspect_pool(
        publish_root=publish,
        milestone="M100",
        source_ready_backlog={
            carrier: len(rows) for carrier, rows in source_candidates.items()
        },
        source_ready_candidates=source_candidates,
        source_ready_input=source_input,
    )
    inspection_ref = "data/local/pool-inspections/m100-wave.json"
    inspection_path = output / inspection_ref
    write_json(inspection_path, inspection)
    preflight_path, _ = ready_semantic_preflight(
        "cursor_grok", output_root=output
    )
    return output, publish, inspection_path, preflight_path


def _kwargs(
    output: Path,
    publish: Path,
    inspection: Path,
    preflight: Path,
) -> dict[str, object]:
    capacity_ref = "data/local/tests/capacity/wave-capacity.json"
    write_synthetic_capacity_receipt(
        output / capacity_ref,
        provider_tier="cursor_grok",
    )
    return {
        "dispatch_id": "m100-current-wave-001",
        "pool_inspection_ref": inspection.relative_to(output).as_posix(),
        "semantic_preflight_receipt_ref": preflight.relative_to(output).as_posix(),
        "capacity_calibration_receipt_ref": capacity_ref,
        "run_date": "20260811",
        "scope": "china",
        "region_ref": "china",
        "sequence_start": 101,
        "output_root": output,
        "publish_root": publish,
    }


def test_three_active_carriers_dispatch_without_video_or_campaign(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output, publish, inspection, preflight = _inputs(tmp_path)

    manifest = build_semantic_wave_dispatch(
        **_kwargs(output, publish, inspection, preflight)
    )

    assert_valid(
        manifest,
        "execution",
        "semantic_wave_dispatch_manifest",
        label="semantic wave dispatch",
    )
    assert manifest["activeCarriers"] == ["homepage", "article", "image"]
    assert [slot["carrier"] for slot in manifest["slots"]] == [
        "homepage",
        "homepage",
        "article",
        "image",
    ]
    assert all(slot["carrier"] != "video" for slot in manifest["slots"])
    assert all("--campaign-root-execution-id" not in slot["argv"] for slot in manifest["slots"])
    assert all(slot["queueBackend"] == "local_file" for slot in manifest["slots"])
    assert all(
        slot["poolDeliveryBackend"] == "reliabletask"
        for slot in manifest["slots"]
    )
    candidate_ids = [
        candidate_id
        for slot in manifest["slots"]
        for candidate_id in slot["candidateIds"]
    ]
    assert len(candidate_ids) == 48 == len(set(candidate_ids))
    assert all(slot["candidateIds"] for slot in manifest["slots"])
    # 一个 slot 只声明工作单元与容量校准来源：DEC-002 之后 requiredWorkers 退役，
    # 并行上限只由 receipt 的 frozenCapacity 承载，与 slot 的候选数无关。
    assert all(
        slot["taskRequest"]["quota"] == len(slot["candidateIds"])
        for slot in manifest["slots"]
    )
    assert all(
        "requiredWorkers" not in slot["taskRequest"]
        and slot["taskRequest"]["executionAuthority"]["calibration"]
        == manifest["capacityCalibration"]
        for slot in manifest["slots"]
    )

    # The standalone request is itself sufficient runtime authority.  It does
    # not need a campaign capsule or ReliableTask transport to materialize the
    # exact physical candidate set.
    from content.source.research import scale_source_pool_runtime

    monkeypatch.setattr(scale_source_pool_runtime, "OUTPUT_ROOT", output)
    image_slot = next(
        slot for slot in manifest["slots"] if slot["carrier"] == "image"
    )
    targets = frozen_scale_source_pool_targets(
        image_slot["executionId"],
        "image",
        direct_selection=image_slot["taskRequest"],
    )
    assert len(targets) == 12
    assert {row["name"] for row in targets} == {
        f"image-{index:03d}" for index in range(12)
    }


def test_explicit_workload_inspection_and_dispatch_preserve_independent_quotas(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    publish = tmp_path / "publish"
    evidence = output / "data/source-pools/evidence"
    for ref, body in EVIDENCE.values():
        path = evidence / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    workloads = {"homepage": 7, "image": 11}
    candidates = [
        *(_candidate("homepage", index) for index in range(7)),
        *(
            _candidate("image", index, evidence_root=evidence)
            for index in range(11)
        ),
    ]
    plan = build_scale_source_pool_plan(
        pool_id="homepage-image-explicit-workload",
        target_scale=None,
        created_at="2026-08-14T00:00:00Z",
        candidates=candidates,
        workload_targets=workloads,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )
    plan_ref = "data/source-pools/homepage-image-workload.json"
    write_json(output / plan_ref, plan)
    capacity_ref = "data/local/tests/capacity/workload-capacity.json"
    write_synthetic_capacity_receipt(
        output / capacity_ref,
        provider_tier="cursor_grok",
    )
    source_input, source_candidates = load_source_ready_input(
        output_root=output,
        publish_root=publish,
        milestone=None,
        source_pool_ref=plan_ref,
        evidence_root_ref=evidence.relative_to(output).as_posix(),
    )
    inspection = inspect_pool(
        publish_root=publish,
        milestone=None,
        workload_targets=workloads,
        source_ready_backlog={
            carrier: len(rows) for carrier, rows in source_candidates.items()
        },
        source_ready_candidates=source_candidates,
        source_ready_input=source_input,
    )
    assert inspection["milestone"] == "WORKLOAD"
    assert inspection["workloadMode"] == "explicit"
    assert inspection["activeCarriers"] == ["homepage", "image"]
    assert inspection["workloadTargets"] == workloads
    inspection_path = output / "data/local/pool-inspections/workload.json"
    write_json(inspection_path, inspection)
    manifest = build_semantic_wave_dispatch(
        dispatch_id="homepage-image-workload-001",
        pool_inspection_ref=inspection_path.relative_to(output).as_posix(),
        semantic_preflight_receipt_ref=None,
        capacity_calibration_receipt_ref=capacity_ref,
        run_date="20260814",
        scope="china",
        region_ref="china",
        sequence_start=1,
        workload_targets=workloads,
        output_root=output,
        publish_root=publish,
    )
    assert manifest["milestone"] == "WORKLOAD"
    assert manifest["workloadTargets"] == workloads
    assert manifest["activeCarriers"] == ["homepage", "image"]
    assert {
        carrier: sum(
            slot["taskRequest"]["quota"]
            for slot in manifest["slots"]
            if slot["carrier"] == carrier
        )
        for carrier in manifest["activeCarriers"]
    } == workloads


def test_dispatch_fails_when_physical_candidate_evidence_disappears(
    tmp_path: Path,
) -> None:
    output, publish, inspection, preflight = _inputs(tmp_path)
    (output / "data/source-pools/evidence/shared/source-unit.json").unlink()

    with pytest.raises(SemanticWaveDispatchError) as captured:
        build_semantic_wave_dispatch(
            **_kwargs(output, publish, inspection, preflight)
        )

    assert captured.value.code == DISPATCH_INVALID
    assert "sourceUnitRef" in str(captured.value)


def test_dispatch_rejects_wave_digest_tamper_and_empty_wave(
    tmp_path: Path,
) -> None:
    output, publish, inspection, preflight = _inputs(tmp_path)
    document = json.loads(inspection.read_text(encoding="utf-8"))
    document["semanticScheduling"]["waveInput"]["waveInputDigest"] = (
        "sha256:" + "0" * 64
    )
    write_json(inspection, document)
    with pytest.raises(SemanticWaveDispatchError) as tampered:
        build_semantic_wave_dispatch(
            **_kwargs(output, publish, inspection, preflight)
        )
    assert tampered.value.code == DISPATCH_INVALID

    output, publish, inspection, preflight = _inputs(tmp_path / "empty")
    document = json.loads(inspection.read_text(encoding="utf-8"))
    wave = document["semanticScheduling"]["waveInput"]
    wave["candidates"] = []
    stable = {key: value for key, value in wave.items() if key != "waveInputDigest"}
    wave["waveInputDigest"] = "sha256:" + hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    write_json(inspection, document)
    with pytest.raises(SemanticWaveDispatchError) as empty:
        build_semantic_wave_dispatch(
            **_kwargs(output, publish, inspection, preflight)
        )
    assert empty.value.code == DISPATCH_EMPTY


def test_dispatch_is_create_once_replay_and_collision_safe(tmp_path: Path) -> None:
    output, publish, inspection, preflight = _inputs(tmp_path)
    kwargs = _kwargs(output, publish, inspection, preflight)

    first, path = write_create_once_semantic_wave_dispatch(**kwargs)
    replay, replay_path = write_create_once_semantic_wave_dispatch(**kwargs)

    assert replay == first
    assert replay_path == path
    changed = copy.deepcopy(kwargs)
    changed["semantic_preflight_receipt_ref"] = None
    with pytest.raises(SemanticWaveDispatchError) as captured:
        write_create_once_semantic_wave_dispatch(**changed)
    assert captured.value.code == DISPATCH_COLLISION


def test_retry_dispatch_binds_exact_predecessor_slots_and_selection(
    tmp_path: Path,
) -> None:
    output, publish, inspection, preflight = _inputs(tmp_path)
    predecessor, predecessor_path = write_create_once_semantic_wave_dispatch(
        **_kwargs(output, publish, inspection, preflight)
    )
    kwargs = _kwargs(output, publish, inspection, preflight)
    kwargs.update(
        dispatch_id="m100-current-wave-retry-001",
        sequence_start=201,
        predecessor_dispatch_ref=predecessor_path.relative_to(output).as_posix(),
        predecessor_execution_ids={
            slot["slotId"]: slot["executionId"]
            for slot in predecessor["slots"]
        },
    )

    retry = build_semantic_wave_dispatch(**kwargs)

    assert retry["predecessorDispatch"] == {
        "manifestRef": predecessor_path.relative_to(output).as_posix(),
        "manifestFileSha256": _sha_bytes(predecessor_path.read_bytes()),
        "manifestDigest": predecessor["manifestDigest"],
    }
    assert [slot["executionId"] for slot in retry["slots"]] == [
        "20260811--travel-homepage-workload-homepage-24-article-12-image-12--china--scale-201",
        "20260811--travel-homepage-workload-homepage-24-article-12-image-12--china--scale-202",
        "20260811--travel-article-workload-homepage-24-article-12-image-12--china--scale-203",
        "20260811--travel-image-workload-homepage-24-article-12-image-12--china--scale-204",
    ]
    predecessor_by_slot = {
        slot["slotId"]: slot for slot in predecessor["slots"]
    }
    for slot in retry["slots"]:
        frozen = predecessor_by_slot[slot["slotId"]]
        assert slot["retryOf"] == frozen["executionId"]
        assert slot["candidateIds"] == frozen["candidateIds"]
        assert slot["candidateObjectRefs"] == frozen["candidateObjectRefs"]
        assert slot["taskRequest"]["sourcePoolSelection"] == frozen["taskRequest"][
            "sourcePoolSelection"
        ]
        assert slot["argv"][6:8] == ["--retry-of", frozen["executionId"]]
    assert retry["predecessorMappings"] == [
        {
            "slotId": slot["slotId"],
            "executionId": slot["executionId"],
            "retryOf": slot["retryOf"],
            "predecessorSlotDigest": predecessor_by_slot[slot["slotId"]][
                "slotDigest"
            ],
            "selectionDigest": slot["taskRequest"]["sourcePoolSelection"][
                "selectionDigest"
            ],
        }
        for slot in retry["slots"]
    ]


def test_retry_dispatch_selects_only_explicit_failed_predecessor_slots(
    tmp_path: Path,
) -> None:
    output, publish, inspection, preflight = _inputs(tmp_path)
    predecessor, predecessor_path = write_create_once_semantic_wave_dispatch(
        **_kwargs(output, publish, inspection, preflight)
    )
    kwargs = _kwargs(output, publish, inspection, preflight)
    failed_slot = predecessor["slots"][1]
    kwargs.update(
        dispatch_id="m100-current-wave-retry-partial",
        sequence_start=201,
        predecessor_dispatch_ref=predecessor_path.relative_to(output).as_posix(),
        predecessor_execution_ids={
            failed_slot["slotId"]: failed_slot["executionId"]
        },
    )

    retry = build_semantic_wave_dispatch(**kwargs)

    assert len(retry["slots"]) == 1
    assert retry["activeCarriers"] == [failed_slot["carrier"]]
    assert retry["slots"][0]["slotId"] == failed_slot["slotId"]
    assert retry["slots"][0]["retryOf"] == failed_slot["executionId"]
    assert retry["slots"][0]["candidateIds"] == failed_slot["candidateIds"]
    assert retry["slots"][0]["candidateObjectRefs"] == failed_slot[
        "candidateObjectRefs"
    ]


def test_retry_dispatch_can_narrow_one_exhausted_slot_to_exact_unfinished_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output, publish, inspection, preflight = _inputs(tmp_path)
    predecessor, predecessor_path = write_create_once_semantic_wave_dispatch(
        **_kwargs(output, publish, inspection, preflight)
    )
    failed_slot = next(
        slot for slot in predecessor["slots"] if slot["carrier"] == "article"
    )
    failed_candidate_id = failed_slot["candidateIds"][0]
    failed_object_ref = "article-001__source-unit-001"
    from content.release.canonical import semantic_wave_dispatch as dispatch_module

    monkeypatch.setattr(
        dispatch_module,
        "load_retry_unfinished_scope",
        lambda *_args, **_kwargs: SimpleNamespace(
            candidate_ids=(failed_candidate_id,),
        ),
    )
    kwargs = _kwargs(output, publish, inspection, preflight)
    kwargs.update(
        dispatch_id="m100-current-wave-retry-unfinished",
        sequence_start=201,
        predecessor_dispatch_ref=predecessor_path.relative_to(output).as_posix(),
        predecessor_execution_ids={
            failed_slot["slotId"]: failed_slot["executionId"]
        },
        predecessor_unfinished_refs={
            failed_slot["slotId"]: (failed_object_ref,)
        },
    )

    retry = build_semantic_wave_dispatch(**kwargs)

    slot = retry["slots"][0]
    assert slot["candidateIds"] == [failed_candidate_id]
    assert slot["taskRequest"]["targetNames"] == [failed_candidate_id]
    assert slot["taskRequest"]["count"] == 1
    assert slot["taskRequest"]["quota"] == 1
    assert slot["retryUnfinishedRefs"] == [failed_object_ref]
    assert slot["argv"][8:10] == ["--retry-unfinished-ref", failed_object_ref]
    assert retry["predecessorMappings"][0]["unfinishedRefs"] == [failed_object_ref]


def test_retry_dispatch_rejects_wrong_predecessor_mapping(
    tmp_path: Path,
) -> None:
    output, publish, inspection, preflight = _inputs(tmp_path)
    predecessor, predecessor_path = write_create_once_semantic_wave_dispatch(
        **_kwargs(output, publish, inspection, preflight)
    )
    kwargs = _kwargs(output, publish, inspection, preflight)
    kwargs.update(
        dispatch_id="m100-current-wave-retry-invalid",
        sequence_start=201,
        predecessor_dispatch_ref=predecessor_path.relative_to(output).as_posix(),
    )
    kwargs["predecessor_execution_ids"] = {
        slot["slotId"]: slot["executionId"]
        for slot in predecessor["slots"]
    }
    kwargs["predecessor_execution_ids"]["homepage-01"] = predecessor["slots"][1][
        "executionId"
    ]
    with pytest.raises(SemanticWaveDispatchError) as wrong:
        build_semantic_wave_dispatch(**kwargs)
    assert wrong.value.code == DISPATCH_INVALID
    assert "does not match predecessor dispatch slot" in str(wrong.value)
