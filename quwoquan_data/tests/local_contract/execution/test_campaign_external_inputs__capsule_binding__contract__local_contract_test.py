# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from content.execution.campaign.external_input_runtime import (
    freeze_execution_external_input_envelope,
    resolve_runtime_external_input_context,
)
from content.execution.source_pool.external_inputs import (
    CampaignExternalInputError,
    external_inputs_digest,
    lane_acquisition_root,
    materialize_external_input_bundle,
    payload_digest,
)
from content.execution.campaign import plan as campaign_plan
from content.execution.campaign import source_capsule_store
from content.execution.campaign.plan import freeze_plan
from content.execution.campaign.submission import write_submission
from content.execution.campaign.workspace import (
    CampaignLaneWorkspace,
    CampaignRuntimePaths,
    SourceCapsule,
)
from content.execution.request import RuntimeExecutionRequest
from content.source import source_inputs
from core import paths as core_paths
from core.control_types import TargetSelector
from core.io import read_json, write_json
from support.capacity_calibration_fixture import (
    synthetic_capacity_source_binding,
    synthetic_governed_execution_authority,
)
from support.campaign_external_inputs_fixture import (  # noqa: F401
    CATALOG_DIGEST,
    EXECUTION_IDS,
    ROOT_ID,
    SOURCE_DIGEST,
    SOURCE_REVISION,
    _acquisition,
    _governed_acquisition_handoff,
)
from support.semantic_preflight_fixture import ready_semantic_preflight


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    output = tmp_path / "output"
    return CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=output,
        publish_root=tmp_path / "publish",
        campaigns_root=output / "data/local/workspace/content-campaign-submissions",
        workspaces_root=output / "data/local/cache/content-campaign-workspaces",
    )




def _submission(
    carrier: str,
    refs: list[dict[str, object]],
    *,
    semantic_preflight_binding: dict[str, str],
    scale_source_pool: dict[str, object],
    source_pool_evidence_root_ref: str,
    source_pool_selection: dict[str, object],
) -> dict[str, object]:
    active_carriers = list(EXECUTION_IDS)
    workloads = {active: 100 for active in active_carriers}
    stable: dict[str, object] = {
        "schema": "quwoquan_data.content_execution_submission",
        "scale": "M100",
        "workloadMode": "milestone_preset",
        "activeCarriers": active_carriers,
        "workloads": workloads,
        "rootExecutionId": ROOT_ID,
        "executionId": EXECUTION_IDS[carrier],
        "operation": f"{carrier}.generate",
        "carrier": carrier,
        "familyRef": f"content/travel/{carrier}/{carrier}",
        "regionRef": "china",
        "selector": "source-ready-priority"
        if carrier in {"homepage", "video"}
        else "priority",
        "quota": 100,
        "count": 150,
        "executionAuthority": synthetic_governed_execution_authority(),
        "workerHostSetBinding": None,
        "topic": None,
        "targetNames": [],
        "sourceProviders": [],
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": semantic_preflight_binding,
        "retryUnfinishedRefs": [],
        "scaleSourcePool": scale_source_pool,
        "sourcePoolEvidenceRootRef": source_pool_evidence_root_ref,
        "sourcePoolSelection": source_pool_selection,
        "retryOf": None,
        "gitBranch": "dev1.0",
        "gitCommitSha": "c" * 40,
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": SOURCE_DIGEST,
            "inputs": ["quwoquan_data/schema"],
        },
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "f" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": CATALOG_DIGEST,
        "externalInputRefs": refs,
        "externalInputsDigest": external_inputs_digest(refs),
    }
    if refs:
        stable["acquisitionRootRef"] = "data/local/workspace/source-acquisition"
    return {
        **stable,
        "requestDigest": payload_digest(stable),
        "submittedAt": "2026-08-05T00:00:00Z",
    }




def _scale_source_pool(
    runtime: CampaignRuntimePaths,
) -> tuple[dict[str, object], str, dict[str, dict[str, object]]]:
    pool_stable: dict[str, object] = {
        "schema": "quwoquan_data.scale_source_pool",
        "poolId": "external-input-m100-pool",
        "targetScale": "M100",
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "candidates": [
            {
                "candidateId": f"{carrier}-candidate-001",
                "carrier": carrier,
                "objectRef": f"{carrier}/candidate-001",
            }
            for carrier in EXECUTION_IDS
        ],
    }
    pool = {**pool_stable, "planDigest": payload_digest(pool_stable)}
    pool_path = runtime.output_root / "data/local/workspace/scale-source-pool/plan.json"
    write_json(pool_path, pool)
    evidence_root = runtime.output_root / "data/local/workspace/scale-source-pool/evidence"
    evidence_root.mkdir(parents=True)
    binding = {
        "poolId": pool["poolId"],
        "targetScale": pool["targetScale"],
        "workloadMode": "milestone_preset",
        "activeCarriers": list(EXECUTION_IDS),
        "workloadTargets": {carrier: 100 for carrier in EXECUTION_IDS},
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "planRef": pool_path.relative_to(runtime.output_root).as_posix(),
        "planDigest": pool["planDigest"],
        "planFileSha256": "sha256:" + hashlib.sha256(pool_path.read_bytes()).hexdigest(),
    }
    selections: dict[str, dict[str, object]] = {}
    for carrier in EXECUTION_IDS:
        stable = {
            "carrier": carrier,
            "candidateIds": [f"{carrier}-candidate-001"],
            "candidateCount": 1,
        }
        selections[carrier] = {**stable, "selectionDigest": payload_digest(stable)}
    return binding, evidence_root.relative_to(runtime.output_root).as_posix(), selections




def _frozen_documents(
    runtime: CampaignRuntimePaths,
    image_refs: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    _preflight_path, semantic_preflight_binding = ready_semantic_preflight(
        "default",
        output_root=runtime.output_root,
    )
    pool_binding, pool_evidence_ref, pool_selections = _scale_source_pool(runtime)
    submissions = {
        carrier: _submission(
            carrier,
            image_refs if carrier == "image" else [],
            semantic_preflight_binding=semantic_preflight_binding,
            scale_source_pool=pool_binding,
            source_pool_evidence_root_ref=pool_evidence_ref,
            source_pool_selection=pool_selections[carrier],
        )
        for carrier in EXECUTION_IDS
    }
    submissions_root = runtime.campaigns_root / ROOT_ID / "submissions"
    for document in submissions.values():
        write_json(submissions_root / f"{document['executionId']}.json", document)
    lane_external = {
        carrier: {
            "executionId": EXECUTION_IDS[carrier],
            "externalInputRefs": list(document["externalInputRefs"]),
            "externalInputsDigest": document["externalInputsDigest"],
            # ref 只带 kind 子根，基准根必须与 ref 同行传到 capsule 物化面。
            **(
                {"acquisitionRootRef": document["acquisitionRootRef"]}
                if document.get("externalInputRefs")
                else {}
            ),
        }
        for carrier, document in submissions.items()
    }
    stable: dict[str, object] = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": ROOT_ID,
        "executionMode": "central",
        "scale": "M100",
        "workloadMode": "milestone_preset",
        "activeCarriers": list(EXECUTION_IDS),
        "workloads": {carrier: 100 for carrier in EXECUTION_IDS},
        "gitBranch": "dev1.0",
        "gitCommitSha": "c" * 40,
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "f" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": CATALOG_DIGEST,
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": semantic_preflight_binding,
        "executionAuthority": synthetic_governed_execution_authority(),
        "scaleSourcePool": pool_binding,
        "sourcePoolEvidenceRootRef": pool_evidence_ref,
        "laneSourcePoolSelections": pool_selections,
        "laneExternalInputs": lane_external,
        "externalInputsDigest": payload_digest(
            {
                "schema": "quwoquan_data.campaign_external_input_lanes",
                "lanes": lane_external,
            }
        ),
        "submissionDigests": {
            carrier: document["requestDigest"]
            for carrier, document in submissions.items()
        },
        "executionIds": EXECUTION_IDS,
        "frozenAt": "2026-08-05T00:00:00Z",
    }
    plan = {**stable, "planDigest": payload_digest(stable)}
    write_json(runtime.campaigns_root / ROOT_ID / "campaign_plan.json", plan)
    return plan, submissions




def _capsule(
    runtime: CampaignRuntimePaths,
    plan: dict[str, object],
    image_refs: list[dict[str, object]],
) -> SourceCapsule:
    capsule_path = runtime.workspaces_root / "content-addressed-capsules/test"
    lane_payload: dict[str, dict[str, object]] = {}
    for carrier in EXECUTION_IDS:
        refs = image_refs if carrier == "image" else []
        root_ref = f"external-inputs/{carrier}"
        materialize_external_input_bundle(
            capsule_path / root_ref,
            refs,
            acquisition_root=runtime.acquisition_root,
            carrier=carrier,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
            library_root=capsule_path.parent / "content_library",
        )
        lane_payload[carrier] = {
            "rootRef": root_ref,
            "externalInputRefs": refs,
            "externalInputsDigest": external_inputs_digest(refs),
        }
    pool_plan = read_json(
        runtime.output_root / str(plan["scaleSourcePool"]["planRef"])
    )
    selected_ids = {
        str(candidate_id)
        for selection in plan["laneSourcePoolSelections"].values()
        for candidate_id in selection["candidateIds"]
    }
    selected_candidates = sorted(
        (
            dict(row)
            for row in pool_plan["candidates"]
            if row["candidateId"] in selected_ids
        ),
        key=lambda row: (str(row["carrier"]), str(row["candidateId"])),
    )
    snapshot_stable = {
        "schema": "quwoquan_data.scale_source_pool_snapshot",
        "planDigest": pool_plan["planDigest"],
        "laneSourcePoolSelections": plan["laneSourcePoolSelections"],
        "selectedCandidates": selected_candidates,
    }
    snapshot_digest = payload_digest(snapshot_stable)
    stable = {
        "schema": "quwoquan_data.content_campaign_source_capsule",
        "format": "source-capsule-v2",
        "gitBranch": str(plan["gitBranch"]),
        "gitCommitSha": "c" * 40,
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "f" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": CATALOG_DIGEST,
        "roots": ["quwoquan_data"],
        "laneExternalInputs": lane_payload,
        "externalInputsDigest": plan["externalInputsDigest"],
        "scaleSourcePool": plan["scaleSourcePool"],
        "sourcePoolSnapshotRootRef": "scale-source-pool",
        "sourcePoolSnapshotDigest": snapshot_digest,
        "laneSourcePoolSelections": plan["laneSourcePoolSelections"],
    }
    write_json(
        capsule_path / "scale-source-pool/plan.json",
        pool_plan,
    )
    write_json(
        capsule_path / "scale-source-pool/selected.json",
        {**snapshot_stable, "snapshotDigest": snapshot_digest},
    )
    capsule_digest = payload_digest(stable)
    write_json(
        capsule_path / ".qwq_campaign_capsule.json",
        {
            **stable,
            "capsuleDigest": capsule_digest,
            "treeDigest": "sha256:" + ("d" * 64),
        },
    )
    return SourceCapsule(
        path=capsule_path,
        ref=capsule_path.relative_to(runtime.output_root).as_posix(),
        capsule_digest=capsule_digest,
        git_branch=str(plan["gitBranch"]),
        commit_sha="c" * 40,
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        execution_bundle_digest="sha256:" + "f" * 64,
        entity_catalog_digest=CATALOG_DIGEST,
        external_inputs_digest=str(plan["externalInputsDigest"]),
        lane_external_inputs=lane_payload,
        roots=("quwoquan_data",),
        read_only=True,
        scale_source_pool=dict(plan["scaleSourcePool"]),
        lane_source_pool_selections={
            carrier: dict(selection)
            for carrier, selection in plan["laneSourcePoolSelections"].items()
        },
        source_pool_snapshot_root_ref="scale-source-pool",
    )



def test_fenced_execution_envelope_uses_only_canonical_capsule_and_rejects_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    _, image_refs = _acquisition(tmp_path)
    plan, submissions = _frozen_documents(runtime, image_refs)
    capsule = _capsule(runtime, plan, image_refs)
    execution_root = runtime.output_root / "data/tasks" / EXECUTION_IDS["image"]
    execution_root.mkdir(parents=True)
    workspace = CampaignLaneWorkspace(
        carrier="image",
        capsule=capsule,
        execution_root=execution_root,
    )
    freeze_execution_external_input_envelope(
        runtime=runtime,
        root_execution_id=ROOT_ID,
        plan=plan,
        submission=submissions["image"],
        workspace=workspace,
    )
    video_execution_root = runtime.output_root / "data/tasks" / EXECUTION_IDS["video"]
    video_execution_root.mkdir(parents=True)
    video_workspace = CampaignLaneWorkspace(
        carrier="video",
        capsule=capsule,
        execution_root=video_execution_root,
    )
    freeze_execution_external_input_envelope(
        runtime=runtime,
        root_execution_id=ROOT_ID,
        plan=plan,
        submission=submissions["video"],
        workspace=video_workspace,
    )
    for key in (
        "QWQ_CAMPAIGN_ROOT_EXECUTION_ID",
        "QWQ_CAMPAIGN_CAPSULE_ROOT",
        "QWQ_CAMPAIGN_EXTERNAL_INPUT_ROOT",
        "QWQ_CAMPAIGN_EXTERNAL_INPUT_ENVELOPE",
    ):
        monkeypatch.setenv(key, str(tmp_path / "untrusted-env-value"))
    context = resolve_runtime_external_input_context(
        EXECUTION_IDS["image"],
        "image",
        requested_receipt_refs=[str(image_refs[0]["receiptRef"])],
        requested_kind="professional_image_acquisition",
        runtime_paths=runtime,
    )
    blob_path = context.blob_path(str(image_refs[0]["blobRefs"][0]["contentSha256"]))
    assert blob_path.is_file()
    assert capsule.path in blob_path.parents
    plan_path = tmp_path / "image_source_plan.json"
    write_json(
        plan_path,
        {
            "acquisitionReceiptRefs": [str(image_refs[0]["receiptRef"])],
            "payload": {
                "imageUrls": [
                    {
                        "url": "https://example.invalid/agent-replacement.jpg",
                        "sourceUrl": "https://example.invalid/agent-replacement",
                    }
                ],
            }
        },
    )
    monkeypatch.setattr(
        source_inputs,
        "_source_plan_files",
        lambda *_args, **_kwargs: [("image", plan_path)],
    )
    specs = source_inputs.curated_images_for_entity(
        EXECUTION_IDS["image"],
        "九寨沟",
        "景区",
        research_lane="image",
        external_input_context=context,
    )
    assert len(specs) == 1
    assert Path(specs[0]["url"].removeprefix("file://")) == blob_path
    write_json(plan_path, {"payload": {"acquisitionReceiptRefs": []}})
    with pytest.raises(ValueError, match="canonical top-level field"):
        source_inputs.curated_images_for_entity(
            EXECUTION_IDS["image"],
            "九寨沟",
            "景区",
            research_lane="image",
            external_input_context=context,
        )
    write_json(
        plan_path,
        {"acquisitionReceiptRefs": ["receipts/undeclared.json"]},
    )
    with pytest.raises(CampaignExternalInputError, match="UNDECLARED"):
        source_inputs.curated_images_for_entity(
            EXECUTION_IDS["image"],
            "九寨沟",
            "景区",
            research_lane="image",
            external_input_context=context,
        )

    with pytest.raises(CampaignExternalInputError, match="UNDECLARED"):
        resolve_runtime_external_input_context(
            EXECUTION_IDS["video"],
            "video",
            requested_receipt_refs=[str(image_refs[0]["receiptRef"])],
            requested_kind="professional_video_acquisition",
            runtime_paths=runtime,
        )

    blob_path.chmod(0o600)
    blob_path.write_bytes(blob_path.read_bytes() + b"runtime-replacement")
    with pytest.raises(
        CampaignExternalInputError, match="DIGEST_DRIFT|digest mismatch"
    ):
        resolve_runtime_external_input_context(
            EXECUTION_IDS["image"],
            "image",
            runtime_paths=runtime,
        )


def test_same_execution_cannot_replace_external_inputs_without_new_retry(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    _, image_refs = _acquisition(tmp_path)
    plan, submissions = _frozen_documents(runtime, image_refs)
    capsule = _capsule(runtime, plan, image_refs)
    execution_root = runtime.output_root / "data/tasks" / EXECUTION_IDS["image"]
    execution_root.mkdir(parents=True)
    workspace = CampaignLaneWorkspace("image", capsule, execution_root)
    freeze_execution_external_input_envelope(
        runtime=runtime,
        root_execution_id=ROOT_ID,
        plan=plan,
        submission=submissions["image"],
        workspace=workspace,
    )
    empty_digest = external_inputs_digest([])
    changed_submission = {
        **submissions["image"],
        "externalInputRefs": [],
        "externalInputsDigest": empty_digest,
    }
    changed_lane = {
        "executionId": EXECUTION_IDS["image"],
        "externalInputRefs": [],
        "externalInputsDigest": empty_digest,
    }
    changed_plan = {
        **plan,
        "laneExternalInputs": {
            **plan["laneExternalInputs"],
            "image": changed_lane,
        },
    }
    changed_capsule = SourceCapsule(
        path=capsule.path,
        ref=capsule.ref,
        capsule_digest="sha256:" + ("e" * 64),
        git_branch=capsule.git_branch,
        commit_sha=capsule.commit_sha,
        source_revision=capsule.source_revision,
        source_digest=capsule.source_digest,
        execution_bundle_digest=capsule.execution_bundle_digest,
        entity_catalog_digest=capsule.entity_catalog_digest,
        external_inputs_digest=capsule.external_inputs_digest,
        lane_external_inputs={
            **capsule.lane_external_inputs,
            "image": {
                "rootRef": "external-inputs/image",
                "externalInputRefs": [],
                "externalInputsDigest": empty_digest,
            },
        },
        roots=capsule.roots,
        read_only=True,
    )
    changed_workspace = CampaignLaneWorkspace("image", changed_capsule, execution_root)
    with pytest.raises(
        CampaignExternalInputError, match="new execution sequence with retryOf"
    ):
        freeze_execution_external_input_envelope(
            runtime=runtime,
            root_execution_id=ROOT_ID,
            plan=changed_plan,
            submission=changed_submission,
            workspace=changed_workspace,
        )

    request = RuntimeExecutionRequest(
        family_ref="content/travel/image/image",
        region_ref="china",
        selector=TargetSelector.PRIORITY,
        count=100,
        quota=100,
        execution_authority=synthetic_governed_execution_authority(),
        topic=None,
        source_providers=(),
        target_names=(),
    )
    with pytest.raises(ValueError, match="retryOf must reference a different"):
        write_submission(
            root_execution_id=ROOT_ID,
            execution_id=EXECUTION_IDS["image"],
            request=request,
            retry_of=EXECUTION_IDS["image"],
            repo_root=tmp_path,
            root=runtime.campaigns_root,
        )


def test_frozen_plan_carries_the_acquisition_base_each_lane_ref_resolves_against(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _governed_acquisition_handoff: None,
) -> None:
    """基准根必须随 lane 一路传到 capsule 物化面。

    每条 externalInputRef 只带 kind 子根（`.`/`video`），基准根来自解析方。提交面
    冻结了基准根却不向 plan 传，物化面就只能取默认采集根——冻结出的 ref 在那里
    一个字节都指不到，而 compile/submit 两道门都已经放行。
    """
    runtime = _runtime(tmp_path)
    # 冻结面的 main-tree 断言属于 git 事实，与本用例要锁的基准根传递无关。
    monkeypatch.setattr(
        campaign_plan, "assert_frozen_main_tree", lambda *_args, **_kwargs: None
    )
    # 夹具按 <output>/data/local/... 建采集根；基准根 ref 要落在同一受治理输出根内。
    monkeypatch.setattr(core_paths, "OUTPUT_ROOT", runtime.output_root)
    acquisition_root, image_refs = _acquisition(tmp_path)
    _preflight_path, semantic_preflight_binding = ready_semantic_preflight(
        "default",
        output_root=runtime.output_root,
    )
    pool_binding, pool_evidence_ref, pool_selections = _scale_source_pool(runtime)
    submissions = {
        carrier: _submission(
            carrier,
            image_refs if carrier == "image" else [],
            semantic_preflight_binding=semantic_preflight_binding,
            scale_source_pool=pool_binding,
            source_pool_evidence_root_ref=pool_evidence_ref,
            source_pool_selection=pool_selections[carrier],
        )
        for carrier in EXECUTION_IDS
    }
    plan, _digest = freeze_plan(runtime, ROOT_ID, submissions)

    image_lane = plan["laneExternalInputs"]["image"]
    assert image_lane["acquisitionRootRef"] == (
        submissions["image"]["acquisitionRootRef"]
    )
    # 没有外部输入的车道不声明基准根：缺席在这里是「无须解析」，不是「取默认值」。
    for carrier in EXECUTION_IDS:
        if carrier != "image":
            assert "acquisitionRootRef" not in plan["laneExternalInputs"][carrier]

    default_root = tmp_path / "never-used-default"
    default_root.mkdir()
    assert lane_acquisition_root(image_lane, default=default_root) != default_root
    assert lane_acquisition_root(
        plan["laneExternalInputs"]["homepage"], default=default_root
    ) == default_root
    assert acquisition_root.is_dir()


def test_capsule_materializes_lane_inputs_from_the_frozen_base_not_the_default_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _governed_acquisition_handoff: None,
) -> None:
    """物化面必须按 lane 冻结的基准根取字节，而不是默认采集根。

    专业图片的产出布局把 manifest/receipt/cas 放在 preparation 目录下，默认采集根
    里并没有这些相对路径。物化面一旦退回默认根，capsule 里就会缺字节，而 compile
    与 submit 两道门都已经放行。
    """
    runtime = _runtime(tmp_path)
    acquisition_root, image_refs = _acquisition(tmp_path)
    default_root = acquisition_root
    # 把采集面搬到默认根之外的子目录：默认根从此解析不到任何一条 ref。
    frozen_base = default_root.parent / "source-acquisition-preparations/image-001"
    frozen_base.parent.mkdir(parents=True, exist_ok=True)
    acquisition_root.rename(frozen_base)
    default_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core_paths, "OUTPUT_ROOT", runtime.output_root)
    monkeypatch.setattr(core_paths, "SOURCE_ACQUISITION_ROOT", default_root)
    frozen_base_ref = frozen_base.relative_to(runtime.output_root).as_posix()

    lane = {
        "executionId": EXECUTION_IDS["image"],
        "externalInputRefs": image_refs,
        "externalInputsDigest": external_inputs_digest(image_refs),
        "acquisitionRootRef": frozen_base_ref,
    }
    assert lane_acquisition_root(lane, default=default_root) == frozen_base

    destination = tmp_path / "capsule/external-inputs/image"
    materialize_external_input_bundle(
        destination,
        lane["externalInputRefs"],
        acquisition_root=lane_acquisition_root(lane, default=default_root),
        carrier="image",
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=CATALOG_DIGEST,
        library_root=tmp_path / "content_library",
    )
    assert (destination / str(image_refs[0]["manifestRef"])).is_file()

    # 退回默认根即判否：缺字节不能被当作「这条 lane 没有外部输入」。
    with pytest.raises(CampaignExternalInputError):
        materialize_external_input_bundle(
            tmp_path / "capsule-default/external-inputs/image",
            lane["externalInputRefs"],
            acquisition_root=default_root,
            carrier="image",
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
            library_root=tmp_path / "content_library",
        )

    # 真实冻结入口必须自己从 lane 取基准根，而不是由调用方补参数。
    lanes = {"image": lane}
    observed_roots: list[Path] = []

    def _spy(destination, refs, *, acquisition_root, **kwargs):
        observed_roots.append(acquisition_root)
        return materialize_external_input_bundle(
            destination, refs, acquisition_root=acquisition_root, **kwargs
        )

    monkeypatch.setattr(
        source_capsule_store, "materialize_external_input_bundle", _spy
    )
    monkeypatch.setattr(
        source_capsule_store,
        "campaign_snapshot_roots",
        lambda *_args, **_kwargs: ("quwoquan_data",),
    )
    monkeypatch.setattr(
        source_capsule_store,
        "materialize_source_snapshot",
        lambda *_args, **_kwargs: None,
    )
    # 后续的 capsule 身份校验需要完整源码树，本用例只裁定基准根的取值来源，
    # 因此让它在校验处失败，只对已观测到的实参断言。
    with pytest.raises(Exception):
        source_capsule_store.prepare_source_capsule(
            runtime,
            git_branch="dev1.0",
            commit_sha="c" * 40,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            execution_bundle={
                "algorithm": "sha256",
                "digest": "sha256:" + "f" * 64,
                "inputs": ["quwoquan_data/scripts"],
            },
            entity_catalog_digest=CATALOG_DIGEST,
            lane_external_inputs=lanes,
            external_inputs_digest=payload_digest(
                {
                    "schema": "quwoquan_data.campaign_external_input_lanes",
                    "lanes": lanes,
                }
            ),
        )
    assert observed_roots == [frozen_base]
