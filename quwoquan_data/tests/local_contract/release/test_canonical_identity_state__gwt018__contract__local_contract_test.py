"""spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-001.t1
spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-001.t2
spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-001.t3
spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-001.t4
"""

from __future__ import annotations

from core.schema import assert_valid


_DIGEST = "sha256:" + "a" * 64


def test_canonical_identity_contracts_freeze_six_states_and_one_action() -> None:
    projection = {
        "schema": "quwoquan_data.canonical_identity_state_projection",
        "objectType": "homepage",
        "objectId": "entity:landmark:emei",
        "objectRef": "locations/landmark/emei",
        "state": "invalid_record_repairable",
        "deepestError": "DATA.POOL.PAYLOAD_DIGEST_DRIFT",
        "recoveryAction": {
            "command": "resolve_invalid_canonical_identity",
            "action": "record_repair",
        },
        "optimisticSnapshotToken": _DIGEST,
        "contentVersion": 1,
        "recordSequence": 1,
        "terminalFact": None,
    }
    assert_valid(
        projection,
        "release",
        "canonical_identity_state_projection",
        label="canonical identity state projection",
    )

    command = {
        "schema": "quwoquan_data.resolve_invalid_canonical_identity_command",
        "objectType": "homepage",
        "objectId": "entity:landmark:emei",
        "objectRef": "locations/landmark/emei",
        "action": "record_repair",
        "expectedSnapshotToken": _DIGEST,
        "expectedContentVersion": 1,
        "expectedRecordSequence": 1,
        "currentPayloadDigest": "sha256:" + "b" * 64,
        "evidencePredicate": "same_logical_version",
        "evidenceBindings": [
            {"role": "record", "ref": "record-proof.json", "sha256": _DIGEST}
        ],
        "terminalReason": None,
        "terminalNextAction": None,
    }
    assert_valid(
        command,
        "release",
        "resolve_invalid_canonical_identity_command",
        label="resolve invalid canonical identity command",
    )


def test_terminal_fact_is_append_only_identity_fact_not_content_version() -> None:
    fact = {
        "schema": "quwoquan_data.canonical_identity_terminal_fact",
        "objectType": "homepage",
        "objectId": "entity:landmark:emei",
        "objectRef": "locations/landmark/emei",
        "recordSequence": 2,
        "contentVersion": 1,
        "terminalReason": "immutable_evidence_unavailable",
        "nextAction": "select_new_identity",
        "previousSnapshotToken": _DIGEST,
        "resolutionCommandDigest": "sha256:" + "c" * 64,
        "evidenceBindings": [
            {"role": "diagnostic", "ref": "diagnostic.json", "sha256": _DIGEST}
        ],
        "terminatedAt": "2026-08-20T00:00:00Z",
    }
    assert_valid(
        fact,
        "release",
        "canonical_identity_terminal_fact",
        label="canonical identity terminal fact",
    )
