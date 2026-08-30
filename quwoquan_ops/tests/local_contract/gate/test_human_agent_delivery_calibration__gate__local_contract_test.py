"""Human calibration model B v2 exact contract and local readback.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-004.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-004.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-004.t4
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-004.t5
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-004.t6
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "quwoquan_ops/cli/human_agent_delivery.py"
FIXTURES = Path(__file__).with_name("fixtures") / "human_agent_delivery_calibration"
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.human_agent_delivery import (  # noqa: E402
    CalibrationError, calibration_session_digest, load_contract, read_calibration_store,
    summarize_calibration_sessions, validate_calibration_readback,
    validate_calibration_session, verify_calibration_readback,
    write_create_once_calibration_session,
)
from lib.human_agent_delivery.calibration import _canonical_bytes  # noqa: E402

NOW = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)
FINGERPRINT = "sha256:" + "a" * 64
MAPPING = {
    "product": ["business", "product", "experience"],
    "engineering": ["engineering"],
    "quality": ["quality"],
    "release_operations": ["release_operations"],
}
DIMENSIONS = [
    "understanding", "option_cross_role_impact_comprehension", "transfer",
    "pause_deny_abort", "recovery", "post_check",
]


def fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def role_session(principal: str, *, participant: str | None = None, policy: str = "role-record-only", source: str = "human_participant") -> dict[str, object]:
    contract = load_contract()
    model = contract["calibration_model"]
    participant = participant or f"participant-{principal.replace('_', '-')}"
    return {
        "schema_version": 2, "contract_version": model["contract_version"],
        "role_model_version": model["role_model_version"],
        "observation_model_version": model["observation_model_version"],
        "session_id": f"calibration-{principal.replace('_', '-')}",
        "principal_class": principal, "participant_ref": participant,
        "scope": {"decision_unit_id": "decision-unit-calibration", "task_id": f"task-{principal}", "evidence_fingerprint": FINGERPRINT, "responsibility_classes": MAPPING[principal]},
        "started_at": "2026-08-30T00:00:00+00:00", "completed_at": "2026-08-30T00:30:00+00:00",
        "source_assurance": {
            "source_kind": source, "authentication_provider_ref": "provider-authenticated" if source == "human_participant" else None,
            "participant_authenticated": source == "human_participant", "consent_obtained": source == "human_participant",
            "consent_recorded_at": "2026-08-29T23:59:00+00:00", "direct_identifiers_removed": True,
            "free_text_excluded": True, "observer_attested": source == "human_participant",
        },
        "separation_policy": policy,
        "observations": [
            {"observation_id": f"observation-{index + 1}", "dimension": dimension, "observed_at": "2026-08-30T00:10:00+00:00", "outcome": "demonstrated", "responsibility_classes": MAPPING[principal]}
            for index, dimension in enumerate(DIMENSIONS)
        ],
    }


def full_sessions(*, shared_participant: bool = False, policy: str = "role-record-only") -> list[dict[str, object]]:
    return [role_session(principal, participant="participant-shared" if shared_participant else None, policy=policy) for principal in MAPPING]


def exact_bytes(readback: dict[str, object], sessions: list[dict[str, object]]) -> dict[str, bytes]:
    by_id = {session["session_id"]: _canonical_bytes(session) for session in sessions}
    return {ref["ref"]: by_id[ref["session_id"]] for ref in readback["session_refs"]}


def test_contract_freezes_exact_model_b_closed_sets_mapping_and_no_delegation() -> None:
    contract = load_contract()
    assert contract["schema_version"] == 2
    assert contract["closed_sets"]["human_calibration_principal_class"] == list(MAPPING)
    assert contract["closed_sets"]["human_calibration_responsibility_class"] == ["business", "product", "experience", "quality", "engineering", "release_operations"]
    assert contract["closed_sets"]["human_calibration_observation_dimension"] == DIMENSIONS
    assert contract["closed_sets"]["human_calibration_status"] == ["not_observed", "insufficient", "calibrated"]
    assert contract["calibration_model"]["principal_responsibility_mapping"] == MAPPING
    assert contract["calibration_model"]["mapping_semantics"] == "calibration_coverage_only"
    assert contract["calibration_model"]["authority_delegation"] is False
    assert contract["calibration_model"]["signoff_substitution"] is False
    assert contract["calibration_model"]["freshness_seconds"] == 86400


def test_not_observed_without_qualifying_sessions_and_machine_fixture_never_calibrates() -> None:
    empty = summarize_calibration_sessions([], now=NOW)
    assert empty["status"] == "not_observed"
    assert empty["sample_counters"]["qualifying_role_session_count"] == 0
    machine = summarize_calibration_sessions([fixture("machine_baseline_session.json")], now=NOW)
    assert machine["status"] == "not_observed"
    assert machine["sample_counters"]["machine_source_session_count"] == 1
    assert machine["source_assurance"]["human_source_only"] is False


@pytest.mark.parametrize(
    "mutate,blocker",
    [
        (lambda sessions: sessions.pop(), "principal_coverage_incomplete"),
        (lambda sessions: sessions[0]["source_assurance"].update(consent_obtained=False), "source_assurance_incomplete"),
        (lambda sessions: sessions[0]["source_assurance"].update(participant_authenticated=False), "source_assurance_incomplete"),
        (lambda sessions: sessions[0]["source_assurance"].update(direct_identifiers_removed=False), "source_assurance_incomplete"),
        (lambda sessions: sessions[0]["observations"][0].update(outcome="insufficient"), "source_assurance_incomplete"),
    ],
)
def test_partial_unconsented_unauthenticated_undeidentified_and_dimension_failures_are_insufficient(mutate, blocker: str) -> None:
    sessions = full_sessions()
    mutate(sessions)
    report = summarize_calibration_sessions(sessions, now=NOW)
    assert report["status"] == "insufficient"
    assert blocker in report["blockers"]




def test_partial_responsibility_coverage_is_insufficient() -> None:
    sessions = full_sessions()
    for observation in sessions[0]["observations"]:
        observation["responsibility_classes"] = ["product"]
    report = summarize_calibration_sessions(sessions, now=NOW)
    assert report["status"] == "insufficient"
    assert "responsibility_coverage_incomplete" in report["blockers"]


def test_mixed_machine_fixture_cannot_join_human_sessions_to_calibrate() -> None:
    sessions = full_sessions()
    sessions.append(fixture("machine_baseline_session.json"))
    report = summarize_calibration_sessions(sessions, now=NOW)
    assert report["status"] == "insufficient"
    assert report["source_assurance"]["human_source_only"] is False
    assert "source_assurance_incomplete" in report["blockers"]


def test_stale_session_is_insufficient_and_bad_chronology_is_rejected() -> None:
    sessions = full_sessions()
    for session in sessions:
        session["started_at"] = "2026-08-28T00:00:00+00:00"
        session["completed_at"] = "2026-08-28T00:30:00+00:00"
        session["source_assurance"]["consent_recorded_at"] = "2026-08-27T23:59:00+00:00"
        for observation in session["observations"]:
            observation["observed_at"] = "2026-08-28T00:10:00+00:00"
    report = summarize_calibration_sessions(sessions, now=NOW)
    assert report["status"] == "insufficient"
    assert "session_stale" in report["blockers"]
    broken = role_session("product")
    broken["completed_at"] = "2026-08-29T23:00:00+00:00"
    with pytest.raises(CalibrationError) as error:
        validate_calibration_session(broken)
    assert error.value.code == "HAD.CALIBRATION_INVALID"


def test_calibrated_requires_four_role_sessions_six_responsibilities_and_dimensions() -> None:
    sessions = full_sessions()
    report = summarize_calibration_sessions(sessions, now=NOW)
    assert report["status"] == "calibrated"
    assert report["sample_counters"] == {"session_count": 4, "human_source_session_count": 4, "machine_source_session_count": 0, "qualifying_role_session_count": 4, "unique_participant_count": 4}
    assert report["coverage"]["completed_principal_classes"] == list(MAPPING)
    assert report["coverage"]["completed_responsibility_classes"] == ["business", "product", "experience", "quality", "engineering", "release_operations"]
    assert report["coverage"]["completed_observation_dimensions"] == DIMENSIONS
    assert report["source_assurance"] == {"authenticated": True, "consented": True, "deidentified": True, "raw_content_excluded": True, "human_source_only": True}


def test_same_participant_role_record_only_needs_separate_role_sessions_but_not_four_people() -> None:
    sessions = full_sessions(shared_participant=True)
    report = summarize_calibration_sessions(sessions, now=NOW)
    assert report["status"] == "calibrated"
    assert report["sample_counters"]["session_count"] == 4
    assert report["sample_counters"]["unique_participant_count"] == 1
    assert len({item["principal_class"] for item in report["session_refs"]}) == 4


def test_independent_principal_policy_requires_distinct_participants() -> None:
    invalid = summarize_calibration_sessions(full_sessions(shared_participant=True, policy="independent-principal-required"), now=NOW)
    assert invalid["status"] == "insufficient"
    assert "independent_principal_required" in invalid["blockers"]
    valid = summarize_calibration_sessions(full_sessions(policy="independent-principal-required"), now=NOW)
    assert valid["status"] == "calibrated"
    assert valid["separation"]["required_distinct_participant_count"] == 4


def test_exact_bytes_verifier_rejects_digest_drift_unknown_version_extra_field_and_v1() -> None:
    sessions = full_sessions()
    readback = summarize_calibration_sessions(sessions, now=NOW)
    verified = verify_calibration_readback(readback, session_bytes_by_ref=exact_bytes(readback, sessions), now=NOW, expected_scope={"decision_unit_id": "decision-unit-calibration", "evidence_fingerprint": FINGERPRINT})
    assert verified["status"] == "calibrated"
    drift = exact_bytes(readback, sessions)
    first = next(iter(drift))
    drift[first] += b" "
    with pytest.raises(CalibrationError) as error:
        verify_calibration_readback(readback, session_bytes_by_ref=drift, now=NOW, expected_scope={"decision_unit_id": "decision-unit-calibration", "evidence_fingerprint": FINGERPRINT})
    assert error.value.code == "HAD.CALIBRATION_CONTRACT_INCOMPATIBLE"
    for broken in (dict(readback, role_model_version="unknown"), dict(readback, shadow_roles=[]), {"schema_version": 1, "status": "observed"}):
        with pytest.raises(CalibrationError) as error:
            validate_calibration_readback(broken)
        assert error.value.code == "HAD.CALIBRATION_CONTRACT_INCOMPATIBLE"


def test_verifier_rejects_expired_readback_scope_mismatch_and_caller_status_override() -> None:
    sessions = full_sessions()
    readback = summarize_calibration_sessions(sessions, now=NOW)
    with pytest.raises(CalibrationError) as error:
        verify_calibration_readback(readback, session_bytes_by_ref=exact_bytes(readback, sessions), now=NOW + timedelta(days=2), expected_scope={"decision_unit_id": "decision-unit-calibration", "evidence_fingerprint": FINGERPRINT})
    assert error.value.code == "HAD.CALIBRATION_CONTRACT_INCOMPATIBLE"
    forged = deepcopy(readback)
    forged["status"] = "not_observed"
    with pytest.raises(CalibrationError) as error:
        verify_calibration_readback(forged, session_bytes_by_ref=exact_bytes(readback, sessions), now=NOW, expected_scope={"decision_unit_id": "decision-unit-calibration", "evidence_fingerprint": FINGERPRINT})
    assert error.value.code == "HAD.CALIBRATION_CONTRACT_INCOMPATIBLE"
    with pytest.raises(CalibrationError):
        verify_calibration_readback(readback, session_bytes_by_ref=exact_bytes(readback, sessions), now=NOW, expected_scope={"decision_unit_id": "other", "evidence_fingerprint": FINGERPRINT})


def test_payload_has_no_forbidden_raw_or_pii_keys() -> None:
    payload = {"sessions": full_sessions(), "readback": summarize_calibration_sessions(full_sessions(), now=NOW)}
    forbidden = {"prompt", "prompt_text", "message", "message_text", "payload", "raw_payload", "free_text", "transcript", "name", "email", "phone", "address", "government_id", "raw_identity_claim", "actor_id", "user_id"}
    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for child in value.values() for key in keys(child)}
        if isinstance(value, list):
            return {key for child in value for key in keys(child)}
        return set()
    assert not (keys(payload) & forbidden)
    broken = role_session("product")
    broken["observations"][0]["raw_payload"] = "forbidden"
    with pytest.raises(CalibrationError) as error:
        validate_calibration_session(broken)
    assert error.value.code == "HAD.CALIBRATION_PII_FORBIDDEN"


def test_create_once_readback_and_cli_keep_machine_fixture_not_observed(tmp_path: Path) -> None:
    store = tmp_path / "sessions"
    session = fixture("machine_baseline_session.json")
    first = write_create_once_calibration_session(store=store, session=session)
    second = write_create_once_calibration_session(store=store, session=session)
    assert first.created is True and second.created is False
    assert read_calibration_store(store, now=NOW)["status"] == "not_observed"
    env = os.environ.copy(); env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run([sys.executable, "-B", str(CLI), "calibration-readback", "--store", str(store)], cwd=ROOT, text=True, capture_output=True, check=False, env=env)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "not_observed"
