"""Durable explicit handoff publication and portable admission contract."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
import sys
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

import handoff_consumer  # noqa: E402
from lib import handoff_store  # noqa: E402
from lib.agent_governance_contract import contract_schema_version  # noqa: E402
from lib.evidence_fingerprint import build_evidence_fingerprint, canonical_json_bytes  # noqa: E402
from lib.governance_pipeline_admission import adapters  # noqa: E402
from lib.human_agent_delivery.runtime_bridge import project_runtime_decision  # noqa: E402


def _payload() -> dict:
    payload = {
        "schema_version": contract_schema_version("handoff_manifest"),
        "intent": "durable explicit handoff",
        "triggers": ["user_explicit_request"],
        "artifacts": ["artifact.txt"],
        "pending_dispositions": [],
        "downstream": "plan-next",
        "human_decision_ref": None,
        "human_decision_projection": project_runtime_decision(target_kind="handoff"),
        "owner_identity_ref": "owner.json",
        "candidate_evidence_ref": "candidate.json",
        "review_plan_ref": "plan.json",
        "evidence_receipt_refs": ["evidence.json"],
        "reviewer_result_refs": ["review.json"],
        "review_consolidation_ref": "consolidation.json",
        "recovery_token": "rerun_evidence_for_new_fingerprint",
        "fingerprint_receipt": build_evidence_fingerprint({
            "git": {"head_sha": "a" * 40, "merge_base_sha": "b" * 40},
            "workspace": {
                "tracked_digest": "sha256:" + "1" * 64,
                "untracked_digest": "sha256:" + "2" * 64,
                "deleted_digest": "sha256:" + "3" * 64,
                "renamed_digest": "sha256:" + "4" * 64,
                "symlink_digest": "sha256:" + "5" * 64,
            },
            "assets": {
                "canonical_assets_digest": "sha256:" + "6" * 64,
                "review_assets_digest": "sha256:" + "7" * 64,
            },
            "execution": {
                "commands_digest": "sha256:" + "8" * 64,
                "toolchain_digest": "sha256:" + "9" * 64,
                "provider_digest": "sha256:" + "a" * 64,
                "generator_digest": "sha256:" + "b" * 64,
            },
        }, captured_by="handoff-test", captured_metadata={"consumer": "handoff-test"}),
    }
    return handoff_store.bind_identity(payload)


def _fake_common(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    common = tmp_path / "common"
    common.mkdir(mode=0o700)
    monkeypatch.setattr(handoff_store, "git_common_dir", lambda _root: common)
    return common


def test_projection_deletion_does_not_remove_authoritative_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_common(tmp_path, monkeypatch)
    handoff_ref, exact = handoff_store.publish(_payload(), repo_root=tmp_path)
    projection = tmp_path / ".qwq_output/handoff/payload.json"
    projection.parent.mkdir(parents=True)
    projection.write_bytes(exact)
    projection.unlink()
    assert handoff_store.read(handoff_ref, repo_root=tmp_path) == exact
    assert handoff_store.validate_ref_bytes(handoff_ref, exact)["intent"] == "durable explicit handoff"


def test_same_identity_same_bytes_is_idempotent_and_other_bytes_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_common(tmp_path, monkeypatch)
    payload = _payload()
    first_ref, first = handoff_store.publish(payload, repo_root=tmp_path)
    second_ref, second = handoff_store.publish(copy.deepcopy(payload), repo_root=tmp_path)
    assert (second_ref, second) == (first_ref, first)

    conflict = copy.deepcopy(payload)
    conflict["fingerprint_receipt"]["captured_at"] = "2026-09-02T16:00:01+00:00"
    with pytest.raises(handoff_store.HandoffStoreConflict, match="CREATE_ONCE_CONFLICT"):
        handoff_store.publish(conflict, repo_root=tmp_path)
    assert handoff_store.read(first_ref, repo_root=tmp_path) == first


def test_symlink_and_hardlink_published_entries_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    common = _fake_common(tmp_path, monkeypatch)
    payload = _payload()
    exact = canonical_json_bytes(payload)
    identity = payload["handoff_identity"]["digest"]
    entry = common / "qwq-state/handoffs" / (identity.removeprefix("sha256:") + ".json")
    entry.parent.mkdir(parents=True, mode=0o700)
    target = tmp_path / "target.json"
    target.write_bytes(exact)
    entry.symlink_to(target)
    handoff_ref = f"handoff-ref-v1:{identity}:sha256:{__import__('hashlib').sha256(exact).hexdigest()}"
    with pytest.raises(handoff_store.HandoffStoreUnsafe, match="STORE_UNSAFE"):
        handoff_store.read(handoff_ref, repo_root=tmp_path)

    entry.unlink()
    os.link(target, entry)
    with pytest.raises(handoff_store.HandoffStoreUnsafe, match="STORE_UNSAFE"):
        handoff_store.read(handoff_ref, repo_root=tmp_path)


def test_nonregular_published_entry_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    common = _fake_common(tmp_path, monkeypatch)
    payload = _payload()
    exact = canonical_json_bytes(payload)
    identity = payload["handoff_identity"]["digest"]
    entry = common / "qwq-state/handoffs" / (identity.removeprefix("sha256:") + ".json")
    entry.parent.mkdir(parents=True, mode=0o700)
    entry.mkdir(mode=0o700)
    handoff_ref = f"handoff-ref-v1:{identity}:sha256:{__import__('hashlib').sha256(exact).hexdigest()}"
    with pytest.raises(handoff_store.HandoffStoreUnsafe, match="STORE_UNSAFE"):
        handoff_store.read(handoff_ref, repo_root=tmp_path)


def test_consumer_requires_explicit_ref_and_never_uses_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(handoff_consumer.HandoffConsumerError, match="EXPLICIT_REF_REQUIRED"):
        handoff_consumer.consume(Path("latest.json"))

    environment_ref = f"handoff-ref-v1:sha256:{'1' * 64}:sha256:{'2' * 64}"
    explicit_ref = f"handoff-ref-v1:sha256:{'3' * 64}:sha256:{'4' * 64}"
    observed: list[str] = []

    def reject_explicit(ref: str, *, repo_root: Path) -> bytes:
        observed.append(ref)
        raise handoff_store.HandoffStoreError("explicit ref missing")

    monkeypatch.setenv("QWQ_HANDOFF_REF", environment_ref)
    monkeypatch.setattr(handoff_consumer.handoff_store, "read", reject_explicit)
    with pytest.raises(handoff_consumer.HandoffConsumerError, match="explicit ref missing"):
        handoff_consumer.consume_ref(explicit_ref)
    assert observed == [explicit_ref]


def test_portable_raw_bytes_validate_in_another_clone_without_absolute_path(
    tmp_path: Path,
) -> None:
    exact = canonical_json_bytes(_payload())
    identity = json.loads(exact)["handoff_identity"]["digest"]
    handoff_ref = f"handoff-ref-v1:{identity}:sha256:{__import__('hashlib').sha256(exact).hexdigest()}"
    clone_a = tmp_path / "clone-a"
    clone_b = tmp_path / "clone-b"
    clone_a.mkdir(); clone_b.mkdir()
    artifact = clone_a / "artifact.bin"
    artifact.write_bytes(exact)
    transferred = (clone_b / "artifact.bin")
    transferred.write_bytes(artifact.read_bytes())
    payload = handoff_consumer.validate_published_bytes(
        handoff_ref, transferred.read_bytes(), validate_current=False
    )
    assert payload["handoff_identity"]["digest"] == identity


def test_local_and_hosted_admission_accept_same_ref_and_exact_bytes(
    tmp_path: Path,
) -> None:
    exact = canonical_json_bytes(_payload())
    identity = json.loads(exact)["handoff_identity"]["digest"]
    handoff_ref = f"handoff-ref-v1:{identity}:sha256:{__import__('hashlib').sha256(exact).hexdigest()}"
    contract = {
        "layer_admission": {
            "handoff_freshness": {"verifier_id": "governance.handoff.v1"}
        }
    }
    readback = adapters.verify_handoff(
        raw=exact, receipt_ref=handoff_ref, candidate_id="candidate",
        scope_id="scope", verification_time=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ), contract=contract, validate_current=False,
    )
    assert readback["receipt_ref"] == handoff_ref
    assert readback["receipt_bytes_sha256"] == "sha256:" + __import__("hashlib").sha256(exact).hexdigest()
    # Hosted runners receive this same pair from artifact transport; clone/worktree inventory is diagnostic only.
    assert handoff_store.validate_ref_bytes(handoff_ref, exact)["downstream"] == "plan-next"
