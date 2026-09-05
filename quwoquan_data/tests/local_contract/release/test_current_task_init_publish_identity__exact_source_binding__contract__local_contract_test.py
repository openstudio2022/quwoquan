from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from content.release.canonical import (
    object_source_identity,
    object_transaction,
    post_promotion,
    post_transaction,
)
from content.release.canonical.object_source_identity import (
    freeze_execution_source_identity,
)
from content.release.canonical.object_transaction import (
    build_entity_object_transaction_package,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    canonical_transaction_id,
)
from content.release.canonical.post_transaction import (
    build_post_object_transaction_package,
)
from content.release.canonical.publish_object import publish_object
from support.post_object_transaction_fixture import (
    EXECUTION_ID,
    POST_REF,
    _admit_packaged_creator,
    _fixture,
)

CURRENT_POST_REF = POST_REF


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    return path


def _current_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, str]:
    legacy, _legacy_package, _legacy_publish, _legacy_transaction = _fixture(
        tmp_path / "seed", monkeypatch
    )
    output = tmp_path / "current-output"
    execution = output / "data/tasks" / EXECUTION_ID
    demand = {
        "schema": "quwoquan_data.carrier_demand",
        "status": "confirmed",
        "executionId": EXECUTION_ID,
        "carrier": "image",
        "familyRef": "content/travel/image/image",
        "quota": 1,
        "retryOf": None,
    }
    bindings = {
        "schema": "quwoquan_data.immutable_candidate_bindings",
        "executionId": EXECUTION_ID,
        "carrier": "image",
        "entityCatalogDigest": "sha256:" + "4" * 64,
        "candidateCount": 1,
        "targets": [
            {
                "name": "西湖",
                "entityType": "地点/景区",
                "publishAngle": "西湖",
                "publishTitle": "光影",
                "publishSeq": 1,
            }
        ],
    }
    demand_digest = object_source_identity._canonical_file_digest(demand)
    candidate_digest = object_source_identity._canonical_file_digest(bindings)
    demand_binding = {
        "scope": "output",
        "ref": "inputs/demand.json",
        "digest": demand_digest,
    }
    candidate_binding = {
        "scope": "output",
        "ref": "inputs/bindings.json",
        "digest": candidate_digest,
    }
    submitted_inputs = {
        "carrierDemand": demand,
        "immutableCandidateBindings": bindings,
    }
    request = {
        "schema": "quwoquan_data.task_init_request",
        "executionId": EXECUTION_ID,
        "carrier": "image",
        "familyRef": "content/travel/image/image",
        "quota": 1,
        "candidateCount": 1,
        "carrierDemand": demand_binding,
        "immutableCandidateBindings": candidate_binding,
        "submittedInputs": submitted_inputs,
        "retryOf": None,
    }
    target_set = {
        "schema": "quwoquan_data.target_set",
        "executionId": EXECUTION_ID,
        "carrier": "image",
        "selectionPolicy": "frozen",
        "entityCatalogDigest": bindings["entityCatalogDigest"],
        "candidateBinding": {**candidate_binding, "candidateCount": 1},
        "targetCount": 1,
        "targetRefs": [f"posts/{CURRENT_POST_REF}"],
        "targets": bindings["targets"],
    }
    family_path = (
        Path(__file__).resolve().parents[4]
        / "quwoquan_data/control_plane/families/content/travel/image/image.recipe.yaml"
    )
    manifest = {
        "schema": "quwoquan_data.content_execution_manifest",
        "executionId": EXECUTION_ID,
        "carrier": "image",
        "familyRef": {
            "ref": "content/travel/image/image",
            "digest": "sha256:" + hashlib.sha256(family_path.read_bytes()).hexdigest(),
        },
        "initInputs": {
            "carrierDemand": demand_binding,
            "immutableCandidateBindings": candidate_binding,
        },
        "submittedInputs": submitted_inputs,
        "request": {
            "ref": "0.plan/request.json",
            "digest": object_source_identity._canonical_file_digest(request),
        },
        "targetSet": {
            "ref": "0.plan/target_set.json",
            "digest": object_source_identity._canonical_file_digest(target_set),
        },
        "retryOf": None,
    }
    _write(execution / "execution_manifest.json", manifest)
    _write(execution / "0.plan/request.json", request)
    _write(execution / "0.plan/target_set.json", target_set)
    shutil.copytree(legacy / "sources", execution / "sources")
    shutil.copytree(
        legacy / "posts" / POST_REF,
        execution / "posts" / CURRENT_POST_REF,
    )
    transaction_id = canonical_transaction_id(
        execution_id=EXECUTION_ID,
        object_kind="posts",
        object_ref=CURRENT_POST_REF,
    )
    package = execution / "evidence/object-transactions" / transaction_id
    publish = tmp_path / "publish"
    for relative in ("creators", "entities", "posts", "tags"):
        (publish / relative).mkdir(parents=True, exist_ok=True)
    return execution, package, publish, transaction_id


def test_current_task_init_documents_publish_one_post_plan_and_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, package, publish, transaction_id = _current_execution(
        tmp_path, monkeypatch
    )
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=CURRENT_POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    _admit_packaged_creator(package, publish)
    monkeypatch.setattr(post_transaction, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(post_promotion, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(post_promotion, "OUTPUT_ROOT", tmp_path / "current-output")
    monkeypatch.setattr(
        "content.release.canonical.publish_object.PUBLISH_ROOT", publish
    )
    monkeypatch.setattr(
        "content.release.canonical.publish_object.OUTPUT_ROOT",
        tmp_path / "current-output",
    )
    monkeypatch.setattr(
        post_promotion, "execution_root", lambda _execution_id: execution
    )
    monkeypatch.setattr(
        "content.release.canonical.publish_object.execution_root",
        lambda _execution_id: execution,
    )
    monkeypatch.setattr(
        "content.release.canonical.publish_object._review_approved",
        lambda _execution_id, _path, **_kwargs: None,
    )

    planned = publish_object(EXECUTION_ID, f"posts/{CURRENT_POST_REF}")
    applied = publish_object(EXECUTION_ID, f"posts/{CURRENT_POST_REF}", apply=True)

    published = json.loads(
        (publish / "posts" / CURRENT_POST_REF / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert planned["status"] == "ready"
    assert applied["status"] == "published"
    assert applied["admissionResult"] == "appended"
    assert published["sourceIdentity"]["executionId"] == EXECUTION_ID
    assert "sourceDigest" not in published
    assert "executionBundle" not in published
    assert "sourceDigest" not in json.loads(
        (execution / "execution_manifest.json").read_text(encoding="utf-8")
    )
    assert (publish / "posts" / CURRENT_POST_REF / "_pool/versions/1.json").is_file()


@pytest.mark.parametrize(
    "document_ref", ("0.plan/request.json", "0.plan/target_set.json")
)
def test_current_task_init_identity_rejects_exact_document_byte_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    document_ref: str,
) -> None:
    execution, _package, _publish, _transaction_id = _current_execution(
        tmp_path, monkeypatch
    )
    path = execution / document_ref
    path.write_bytes(path.read_bytes() + b" ")
    manifest = json.loads(
        (execution / "execution_manifest.json").read_text(encoding="utf-8")
    )

    with pytest.raises(ObjectTransactionError, match="SOURCE_IDENTITY_DRIFT"):
        freeze_execution_source_identity(
            execution_root=execution,
            execution_manifest=manifest,
            target_ref=f"posts/{CURRENT_POST_REF}",
        )


def test_current_task_init_identity_rejects_target_drift_even_with_rebound_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, _package, _publish, _transaction_id = _current_execution(
        tmp_path, monkeypatch
    )
    target_path = execution / "0.plan/target_set.json"
    target_set = json.loads(target_path.read_text(encoding="utf-8"))
    target_set["targetRefs"] = ["posts/image/other/title/1"]
    _write(target_path, target_set)
    manifest_path = execution / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["targetSet"]["digest"] = (
        "sha256:" + hashlib.sha256(target_path.read_bytes()).hexdigest()
    )
    _write(manifest_path, manifest)

    with pytest.raises(ObjectTransactionError, match="target membership"):
        freeze_execution_source_identity(
            execution_root=execution,
            execution_manifest=manifest,
            target_ref=f"posts/{CURRENT_POST_REF}",
        )


@pytest.mark.parametrize(
    ("has_acquisition_receipt", "review_usage_scope"),
    [(True, "commercial"), (True, "research"), (False, "commercial")],
)
def test_current_task_init_documents_build_entity_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    has_acquisition_receipt: bool,
    review_usage_scope: str,
) -> None:
    execution, _post_package, _publish, _post_transaction = _current_execution(
        tmp_path, monkeypatch
    )
    manifest_path = execution / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["carrier"] = "homepage"
    submitted_demand = manifest["submittedInputs"]["carrierDemand"]
    submitted_bindings = manifest["submittedInputs"]["immutableCandidateBindings"]
    submitted_demand["carrier"] = "homepage"
    submitted_demand["familyRef"] = "content/travel/homepage/homepage"
    submitted_bindings["carrier"] = "homepage"
    submitted_bindings["targets"] = [{"name": "西湖", "entityType": "地点/景区"}]
    manifest["initInputs"]["carrierDemand"]["digest"] = (
        object_source_identity._canonical_file_digest(submitted_demand)
    )
    manifest["initInputs"]["immutableCandidateBindings"]["digest"] = (
        object_source_identity._canonical_file_digest(submitted_bindings)
    )
    request_path = execution / "0.plan/request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["carrier"] = "homepage"
    request["familyRef"] = "content/travel/homepage/homepage"
    request["carrierDemand"] = manifest["initInputs"]["carrierDemand"]
    request["immutableCandidateBindings"] = manifest["initInputs"][
        "immutableCandidateBindings"
    ]
    request["submittedInputs"] = manifest["submittedInputs"]
    target_path = execution / "0.plan/target_set.json"
    target_set = json.loads(target_path.read_text(encoding="utf-8"))
    entity_ref = "地点/景区/西湖"
    target_ref = f"entities/{entity_ref}"
    target_set["carrier"] = "homepage"
    target_set["targetRefs"] = [target_ref]
    target_set["targets"] = submitted_bindings["targets"]
    target_set["candidateBinding"] = {
        **manifest["initInputs"]["immutableCandidateBindings"],
        "candidateCount": 1,
    }
    _write(request_path, request)
    _write(target_path, target_set)
    family_path = (
        Path(__file__).resolve().parents[4]
        / "quwoquan_data/control_plane/families/content/travel/homepage/homepage.recipe.yaml"
    )
    manifest["familyRef"] = {
        "ref": "content/travel/homepage/homepage",
        "digest": "sha256:" + hashlib.sha256(family_path.read_bytes()).hexdigest(),
    }
    manifest["request"]["digest"] = (
        "sha256:" + hashlib.sha256(request_path.read_bytes()).hexdigest()
    )
    manifest["targetSet"]["digest"] = (
        "sha256:" + hashlib.sha256(target_path.read_bytes()).hexdigest()
    )
    _write(manifest_path, manifest)
    entity_root = execution / target_ref
    source_asset = execution / "posts" / CURRENT_POST_REF / "assets/cover.jpg"
    source_unit_asset = execution / "sources/commons/assets/cover.jpg"
    source_unit_asset.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_asset, source_unit_asset)
    source_index_path = execution / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_index["assets"][0]["distributionDecision"] = "commercial_allowed"
    if has_acquisition_receipt:
        source_index["assets"][0]["acquisitionReceiptRef"] = (
            "receipts/fixture-image-acquisition.json"
        )
    else:
        source_index["assets"][0].pop("acquisitionReceiptRef", None)
    _write(source_index_path, source_index)
    (entity_root / "assets").mkdir(parents=True)
    shutil.copy2(source_asset, entity_root / "assets/cover.jpg")
    source_attribution = json.loads(
        (execution / "posts" / CURRENT_POST_REF / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["sourceAttribution"]
    source_attribution.update(
        publicationAdmission="commercial_release",
        commercialAuthorizationStatus="verified",
        authorizationProofUrl="https://example.test/proof",
        termsUrl="https://example.test/terms",
    )
    _write(
        entity_root / "_entity.json",
        {
            "entityRef": f"/entity/{entity_ref}",
            "tagRefs": [],
            "primarySource": {
                "sourceKind": "wikipedia",
                "fetchedAt": "2026-07-18T04:00:00Z",
            },
            "sourceAttribution": source_attribution,
        },
    )
    _write(
        entity_root / "manifest.json",
        {
            "vertical": "travel",
            "sourceAttribution": source_attribution,
            "assets": [
                {
                    "assetId": "west-lake-cover",
                    "fileName": "cover.jpg",
                    "sourceAssetId": "west-lake-cover",
                    "sourceAssetRef": "sources/commons/assets/cover.jpg",
                    "caption": "西湖",
                    "credit": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                    "usageScope": "app_publish",
                    "distributionDecision": "commercial_allowed",
                    "modelReleaseStatus": "not_required",
                    "rightsAuditStatus": "verified",
                    "rightsAuditIssues": [],
                }
            ],
        },
    )
    (entity_root / "page.md").write_text("# 西湖\n", encoding="utf-8")
    _write(entity_root / "evidence/source_catalog.json", {"sources": []})
    _write(
        entity_root / "5.review/content_review.json",
        {
            "schema": "quwoquan_data.content_review",
            "stage": "5.review",
            "executionId": EXECUTION_ID,
            "objectRef": target_ref,
            "decision": "approved",
            "draft": {"ref": "4.draft/page.md", "digest": "sha256:" + "1" * 64},
            "dimensions": [{"name": "content", "decision": "approved", "issues": []}],
            "blockingIssues": [],
            "assetRights": [
                {
                    "assetRef": "sources/commons/assets/cover.jpg",
                    "sourceUrl": "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
                    "license": "CC BY 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                    "usageScope": review_usage_scope,
                    "decision": "approved",
                    "issues": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        object_transaction,
        "_project_entity_creator_closure",
        lambda **_kwargs: ([], []),
    )
    transaction_id = canonical_transaction_id(
        execution_id=EXECUTION_ID,
        object_kind="entities",
        object_ref=entity_ref,
    )
    package = execution / "evidence/object-transactions" / transaction_id

    if not has_acquisition_receipt:
        with pytest.raises(ObjectTransactionError, match="acquisitionReceiptRef"):
            build_entity_object_transaction_package(
                execution_root=execution,
                object_ref=f"/entity/{entity_ref}",
                transaction_id=transaction_id,
                package_root=package,
            )
        return

    built = build_entity_object_transaction_package(
        execution_root=execution,
        object_ref=f"/entity/{entity_ref}",
        transaction_id=transaction_id,
        package_root=package,
    )

    canonical_manifest = json.loads(
        (package / "object/manifest.json").read_text(encoding="utf-8")
    )
    assert built["target"]["objectKind"] == "entities"
    assert canonical_manifest["sourceIdentity"]["executionId"] == EXECUTION_ID
    assert canonical_manifest["admission"]["usageScope"] == review_usage_scope
    assert "sourceDigest" not in canonical_manifest
    assert "executionBundle" not in canonical_manifest
    asset_binding = json.loads(
        (package / "object/asset.refs.json").read_text(encoding="utf-8")
    )["assets"][0]
    assert asset_binding["sourceAssetRefs"] == ["sources/commons/assets/cover.jpg"]
    assert asset_binding["acquisitionReceiptRefs"] == [
        "receipts/fixture-image-acquisition.json"
    ]
