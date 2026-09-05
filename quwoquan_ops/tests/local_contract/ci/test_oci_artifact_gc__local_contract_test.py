"""Reference-safe OCI GC planner.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
"""
import pytest
from quwoquan_ops.ci.plan_oci_artifact_gc import plan_gc


def ref(c: str) -> str:
    return "ghcr.io/openstudio2022/quwoquan/release-artifact@sha256:" + c * 64


def test_released_lkg_and_active_refs_are_never_eligible() -> None:
    inventory = [{"ref": ref(c), "createdAt": "2026-09-01T00:00:00Z"} for c in "abc"]
    plan = plan_gc(inventory=inventory, references=[
        {"ref": ref("a"), "reason": "released"},
        {"ref": ref("b"), "reason": "last-known-good"},
    ])
    assert [item["ref"] for item in plan["protected"]] == [ref("a"), ref("b")]
    assert [item["ref"] for item in plan["eligible"]] == [ref("c")]
    assert plan["applyAuthorized"] is False


def test_invalid_or_mutable_reference_index_fails_closed() -> None:
    with pytest.raises(ValueError, match="REFERENCE_INDEX_INVALID"):
        plan_gc(inventory=[], references=[{"ref": "ghcr.io/x:latest", "reason": "released"}])
