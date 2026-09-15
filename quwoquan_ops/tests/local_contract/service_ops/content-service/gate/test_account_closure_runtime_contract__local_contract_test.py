"""只验证owner类型/存储成员合同，不创建或声称成功runtime receipt。"""
# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
from pathlib import Path
from typing import get_args

import pytest
import yaml
from pydantic import TypeAdapter, ValidationError

from quwoquan_ops.cli.lib.generated import content_account_closure_runtime as wire

ROOT = Path(__file__).resolve().parents[6]
OWNER = ROOT / "quwoquan_service/services/content-service/contracts/content/content_account_closure_workflow"


def runtime_types():
    return [value for name, value in vars(wire).items()
            if name.startswith("ContentAccountClosureRuntime") and isinstance(value, type)]


def test_all_runtime_fields_are_explicit_and_models_strict():
    models = runtime_types()
    assert len(models) == 6
    for model in models:
        assert model.model_config["extra"] == "forbid"
        assert model.model_config["strict"] is True
        assert all(field.is_required() for field in model.model_fields.values())
        with pytest.raises(ValidationError):
            model.model_validate({"restoreVerified": True})


def test_collection_enum_exactly_covers_owner_storage():
    storage = yaml.safe_load((OWNER / "storage.yaml").read_text())
    declared = set(get_args(wire.ContentAccountClosureRuntimeCollection.model_fields["collection"].annotation))
    assert declared == set(storage["collections"])
    assert len(declared) == 9
    assert "post_safety_states" not in declared


@pytest.mark.parametrize("name", ["ContentAccountClosureRuntimeEvidence", "ContentAccountClosureRuntimeSourceCreation"])
def test_production_is_not_a_runtime_evidence_environment(name):
    model = getattr(wire, name)
    adapter = TypeAdapter(model.model_fields["environment"].annotation)
    for value in ("prod", "prod-hosted", "gamma-local", "test"):
        with pytest.raises(ValidationError):
            adapter.validate_python(value, strict=True)
    assert adapter.validate_python("gamma", strict=True) == "gamma"


@pytest.mark.parametrize("field,value", [("recordCount", -1), ("recordCount", True), ("recordCount", "0"), ("canonicalDigest", "sha256:invalid"), ("physicalInstanceId", " ")])
def test_collection_scalar_constraints_reject_invalid_readback(field, value):
    # 单个集合字段的局部负例，不写文件、不作为creation/owner事实。
    data = {"collection": "closed_account_subject_tombstones", "physicalInstanceId": "unverified-test-scalar", "recordCount": 0, "canonicalDigest": "sha256:" + "0" * 64}
    data[field] = value
    with pytest.raises(ValidationError):
        wire.ContentAccountClosureRuntimeCollection.model_validate(data)


def test_source_modes_and_nullable_refs_have_no_implicit_default():
    fields = wire.ContentAccountClosureRuntimeSource.model_fields
    assert set(get_args(fields["mode"].annotation)) == {"new_source", "replayed_source"}
    assert fields["sourceCreation"].is_required()
    assert fields["recovery"].is_required()
    assert set(get_args(fields["stream"].annotation)) == {"events.user.account"}
    assert {"firstAvailablePosition", "frozenThrough", "deliveredThrough", "appliedThrough", "pendingCount"} <= set(wire.ContentAccountClosureRuntimeSourcePartition.model_fields)


def test_post_only_references_the_owner_schema():
    post = yaml.safe_load((OWNER.parent / "post/fields.yaml").read_text())
    assert "ContentAccountClosureRuntimeEvidence" not in post["types"]
    evidence = next(field for field in post["types"]["PostSafetyRuntimeClosure"]["fields"] if field["name"] == "ownerEvidence")
    assert evidence["type"] == "PostSafetyRuntimeEvidence"
    assert "ContentAccountClosureRuntimeEvidence" in evidence["description"]
