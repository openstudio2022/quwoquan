"""商用证据聚合器的 exact-byte、分层与非裁决契约。

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-003.t5
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "quwoquan_ops/cli/human_agent_delivery.py"
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.human_agent_delivery import (  # noqa: E402
    CommercialEvidenceError,
    project_commercial_evidence_payload,
)


def _write_evidence(root: Path, name: str, status: str, **values: object) -> tuple[str, str]:
    raw = json.dumps(
        {"status": status, **values},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return name, "sha256:" + hashlib.sha256(raw).hexdigest()


def _item(
    evidence_id: str,
    *,
    owner_role: str,
    status: str = "passed",
    required: bool = True,
    hard_gate: bool = True,
    fresh: bool = True,
    ref: str | None = None,
    digest: str | None = None,
    label: str | None = None,
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "owner_role": owner_role,
        "label": label or evidence_id,
        "status": status,
        "required": required,
        "hard_gate": hard_gate,
        "fresh": fresh,
        "ref": ref,
        "digest": digest,
        "detail": f"{evidence_id} 证据详情",
    }


def _payload(root: Path, items: list[dict[str, object]], **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "scope": {
            "immutable_candidate": "sha256:" + "a" * 64,
            "source_sha": "b" * 40,
        },
        "evidence_root": str(root.resolve()),
        "evidence_items": items,
        "captured_at": "2026-08-29T12:00:00Z",
        "policy_allows_limited_go": True,
        "limited_scope_reversible": True,
    }
    value.update(overrides)
    return value


def _passed(root: Path, evidence_id: str, role: str, *, label: str | None = None) -> dict[str, object]:
    ref, digest = _write_evidence(root, f"{evidence_id}.json", "passed", source=evidence_id)
    return _item(evidence_id, owner_role=role, ref=ref, digest=digest, label=label)


def _cli(harness: str, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable, "-B", str(CLI), "commercial-evidence-project",
            "--harness", harness, "--input", "-",
        ],
        cwd=ROOT,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


def test_happy_projection_is_still_not_decided_and_external_authority_stays_open(tmp_path: Path) -> None:
    items = [
        _passed(tmp_path, "immutable_artifact", "release_owner"),
        _passed(tmp_path, "nonproduction_uat", "quality_owner"),
        _passed(tmp_path, "commercial_readiness", "product_owner"),
    ]
    result = project_commercial_evidence_payload(_payload(tmp_path, items))
    assert result["decision_status"] == "not_decided"
    assert result["selected_commercial_option"] is None
    assert result["authenticated_authority"] is False
    assert result["executable"] is False
    assert result["available_commercial_options"] == ["go", "limited_go", "hold", "abort"]
    assert {item["open_id"] for item in result["external_authority_blockers"]} == {
        "human-agent-delivery/OPEN-001", "human-agent-delivery/OPEN-003",
    }
    assert result["next_required_roles"][-1] == "product_owner"
    assert {"release_owner", "operations_support_market_channel_owner", "business_sponsor"}.issubset(
        result["next_required_roles"]
    )
    assert all(card["card_type"] == "post_check" for card in result["role_cards"])


@pytest.mark.parametrize("status", ["failed", "missing", "unknown"])
def test_required_hard_gate_status_blocks_go_and_limited_go(tmp_path: Path, status: str) -> None:
    if status == "missing":
        ref = digest = None
    else:
        ref, digest = _write_evidence(tmp_path, "risk.json", status)
    item = _item(
        "risk_gate", owner_role="security_privacy_legal_compliance_owner",
        status=status, ref=ref, digest=digest,
    )
    result = project_commercial_evidence_payload(_payload(tmp_path, [item]))
    assert result["available_commercial_options"] == ["hold", "abort"]
    assert result["hard_gate_blockers"][0]["code"] == "HAD.HARD_GATE_FAILED"
    assert status in result["hard_gate_blockers"][0]["reasons"]
    assert result["next_required_roles"][0] == "security_privacy_legal_compliance_owner"


def test_stale_required_hard_gate_blocks_go_and_requires_fact_owner(tmp_path: Path) -> None:
    ref, digest = _write_evidence(tmp_path, "slo.json", "passed")
    item = _item(
        "production_slo", owner_role="environment_reliability_owner",
        fresh=False, ref=ref, digest=digest,
    )
    result = project_commercial_evidence_payload(_payload(tmp_path, [item]))
    assert result["available_commercial_options"] == ["hold", "abort"]
    assert result["hard_gate_blockers"][0]["reasons"] == ["stale"]
    assert result["next_required_roles"][0] == "environment_reliability_owner"


def test_review_role_is_rejected_as_evidence_owner(tmp_path: Path) -> None:
    ref, digest = _write_evidence(tmp_path, "review.json", "passed")
    payload = _payload(tmp_path, [_item("review", owner_role="developer", ref=ref, digest=digest)])
    with pytest.raises(CommercialEvidenceError) as raised:
        project_commercial_evidence_payload(payload)
    assert raised.value.code == "HAD.REVIEW_ROLE_FORBIDDEN"


@pytest.mark.parametrize("unsafe_ref", ["../outside.json", "/tmp/outside.json", "nested/../evidence.json"])
def test_path_traversal_and_absolute_ref_are_rejected(tmp_path: Path, unsafe_ref: str) -> None:
    item = _item(
        "unsafe", owner_role="quality_owner", ref=unsafe_ref,
        digest="sha256:" + "0" * 64,
    )
    with pytest.raises(CommercialEvidenceError, match="ref"):
        project_commercial_evidence_payload(_payload(tmp_path, [item]))


def test_symlink_ref_is_rejected(tmp_path: Path) -> None:
    ref, digest = _write_evidence(tmp_path, "actual.json", "passed")
    os.symlink(ref, tmp_path / "linked.json")
    item = _item("linked", owner_role="quality_owner", ref="linked.json", digest=digest)
    with pytest.raises(CommercialEvidenceError, match="symlink"):
        project_commercial_evidence_payload(_payload(tmp_path, [item]))


def test_exact_byte_digest_drift_is_rejected(tmp_path: Path) -> None:
    ref, digest = _write_evidence(tmp_path, "evidence.json", "passed")
    (tmp_path / ref).write_bytes((tmp_path / ref).read_bytes() + b"\n")
    item = _item("drift", owner_role="quality_owner", ref=ref, digest=digest)
    with pytest.raises(CommercialEvidenceError, match="digest drift"):
        project_commercial_evidence_payload(_payload(tmp_path, [item]))


def test_declared_status_must_equal_exact_evidence_status(tmp_path: Path) -> None:
    ref, digest = _write_evidence(tmp_path, "evidence.json", "failed")
    item = _item("status", owner_role="quality_owner", status="passed", ref=ref, digest=digest)
    with pytest.raises(CommercialEvidenceError, match="不一致"):
        project_commercial_evidence_payload(_payload(tmp_path, [item]))


def test_evidence_item_order_does_not_change_fingerprint(tmp_path: Path) -> None:
    first = _passed(tmp_path, "b-evidence", "quality_owner")
    second = _passed(tmp_path, "a-evidence", "release_owner")
    direct = project_commercial_evidence_payload(_payload(tmp_path, [first, second]))
    reversed_result = project_commercial_evidence_payload(_payload(tmp_path, [second, first]))
    assert direct["digest"] == reversed_result["digest"]
    assert direct["fingerprint_ref"] == reversed_result["fingerprint_ref"]
    assert direct == reversed_result


def test_released_and_published_evidence_cannot_derive_attained(tmp_path: Path) -> None:
    items = [
        _passed(tmp_path, "production_released", "release_owner", label="生产 released"),
        _passed(
            tmp_path, "channel_published", "operations_support_market_channel_owner",
            label="渠道 published",
        ),
    ]
    result = project_commercial_evidence_payload(_payload(tmp_path, items))
    layers = {item["layer"]: item for item in result["delivery_layers"]}
    assert layers["production_campaign"]["evidence_status"] == "evidenced"
    assert layers["channel"]["evidence_status"] == "evidenced"
    assert layers["outcome"]["evidence_status"] == "not_evidenced"
    assert layers["outcome"]["decision_status"] == "not_decided"
    guarantees = result["non_derivation_guarantees"]
    assert guarantees["released_or_published_does_not_attain_outcome"] is True
    assert guarantees["outcome_acceptance_emitted"] is False
    assert "attained" not in json.dumps(result["delivery_layers"], ensure_ascii=False)


def test_cursor_and_codex_bytes_are_identical(tmp_path: Path) -> None:
    payload = _payload(tmp_path, [_passed(tmp_path, "quality", "quality_owner")])
    cursor = _cli("cursor", payload)
    codex = _cli("codex", payload)
    assert cursor.returncode == codex.returncode == 0
    assert cursor.stderr == codex.stderr == ""
    assert cursor.stdout.encode("utf-8") == codex.stdout.encode("utf-8")
    assert json.loads(cursor.stdout)["decision_status"] == "not_decided"


def test_cli_error_is_typed_blocker_without_traceback(tmp_path: Path) -> None:
    payload = _payload(tmp_path, [
        _item(
            "review", owner_role="review.developer", ref="x.json",
            digest="sha256:" + "0" * 64,
        )
    ])
    completed = _cli("cursor", payload)
    assert completed.returncode == 1
    assert completed.stderr == ""
    result = json.loads(completed.stdout)
    assert result["result"] == "typed_blocker"
    assert result["code"] == "HAD.REVIEW_ROLE_FORBIDDEN"
    assert "Traceback" not in completed.stdout


def test_limited_go_requires_both_policy_and_reversibility(tmp_path: Path) -> None:
    item = _passed(tmp_path, "hard_gate", "quality_owner")
    for overrides in (
        {"policy_allows_limited_go": False, "limited_scope_reversible": True},
        {"policy_allows_limited_go": True, "limited_scope_reversible": False},
    ):
        result = project_commercial_evidence_payload(_payload(tmp_path, [item], **overrides))
        assert result["available_commercial_options"] == ["go", "hold", "abort"]


def test_input_and_evidence_item_fields_are_closed(tmp_path: Path) -> None:
    item = _passed(tmp_path, "quality", "quality_owner")
    bad_item = deepcopy(item)
    bad_item["business_verdict"] = "go"
    with pytest.raises(CommercialEvidenceError, match="字段漂移"):
        project_commercial_evidence_payload(_payload(tmp_path, [bad_item]))
    bad_input = _payload(tmp_path, [item], latest=True)
    with pytest.raises(CommercialEvidenceError, match="字段漂移"):
        project_commercial_evidence_payload(bad_input)
