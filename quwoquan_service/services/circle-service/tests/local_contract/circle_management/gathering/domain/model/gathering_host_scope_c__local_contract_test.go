package model_test

import (
	"errors"
	"testing"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

func TestScopeCHostBindingSeparatesCreatorAndOrganizerFromParticipation(t *testing.T) {
	now := time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)
	for _, kind := range []contract.GatheringHostSubjectKind{
		contract.GatheringHostSubjectKindPersona,
		contract.GatheringHostSubjectKindEntityHomepage,
		contract.GatheringHostSubjectKindCircle,
	} {
		binding := scopeCHostBinding(kind, now)
		evidence := scopeCHostEvidence(binding, "creator-persona", "creator-persona", model.HostAuthorityCreateDraft, now)
		createdBinding, assignments, fact, err := model.InitializeHostState(
			"creator-persona",
			binding,
			evidence,
			now,
		)
		if err != nil {
			t.Fatalf("kind %q: initialize Host state: %v", kind, err)
		}
		if createdBinding.HostSubjectID == "creator-persona" {
			t.Fatalf("kind %q: Host subject must remain separate from execution creator", kind)
		}
		if len(assignments) != 1 ||
			assignments[0].PersonaID != "creator-persona" ||
			assignments[0].Role != contract.GatheringOrganizerRolePrimaryOrganizer {
			t.Fatalf("kind %q: unexpected organizer assignments: %+v", kind, assignments)
		}
		if fact.ActorPersonaID != "creator-persona" || fact.HostSubjectID != binding.HostSubjectID {
			t.Fatalf("kind %q: incomplete audit fact: %+v", kind, fact)
		}
	}
}

func TestScopeCHostAuthorityRejectsForgeryRevocationAndReplay(t *testing.T) {
	now := time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)
	binding := scopeCHostBinding(contract.GatheringHostSubjectKindCircle, now)
	query := model.HostAuthorityQuery{
		HostSubjectKind: binding.HostSubjectKind, HostSubjectID: binding.HostSubjectID,
		ActorPersonaID: "primary", OrganizerPersonaID: "candidate",
		AuthorityEvidenceRef: binding.AuthorityEvidenceRef, AuthorityVersion: binding.AuthorityVersion,
		Action: model.HostAuthorityTransferOrganizer, EvaluatedAt: now,
	}
	valid := scopeCHostEvidence(binding, "primary", "candidate", model.HostAuthorityTransferOrganizer, now)

	for name, mutate := range map[string]func(*model.HostAuthorityEvidence){
		"forged actor":        func(value *model.HostAuthorityEvidence) { value.ActorPersonaID = "attacker" },
		"forged target":       func(value *model.HostAuthorityEvidence) { value.OrganizerPersonaID = "attacker" },
		"wrong action replay": func(value *model.HostAuthorityEvidence) { value.Action = model.HostAuthorityPublish },
		"revoked":             func(value *model.HostAuthorityEvidence) { value.Revoked = true },
		"invalid":             func(value *model.HostAuthorityEvidence) { value.Valid = false },
		"expired":             func(value *model.HostAuthorityEvidence) { value.ExpiresAt = now },
	} {
		t.Run(name, func(t *testing.T) {
			evidence := valid
			mutate(&evidence)
			err := model.ValidateHostAuthority(binding, query, evidence)
			if !errors.Is(err, gatheringerrors.ErrGatheringHostAuthorityInvalid) {
				t.Fatalf("expected structured Host authority error, got %v", err)
			}
		})
	}
}

func TestScopeCOrganizerAssignmentIsAtomicAndDoesNotOccupySeat(t *testing.T) {
	now := time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)
	binding := scopeCHostBinding(contract.GatheringHostSubjectKindEntityHomepage, now)
	assignments := []contract.OrganizerAssignment{{
		PersonaID: "primary", Role: contract.GatheringOrganizerRolePrimaryOrganizer,
		AuthorityEvidenceRef: binding.AuthorityEvidenceRef,
		AuthorityVersion:     binding.AuthorityVersion, AssignedAt: now, Version: 1,
	}}
	assignEvidence := scopeCHostEvidence(binding, "primary", "co-host", model.HostAuthorityAssignOrganizer, now)
	assigned, _, err := model.AssignCoHost(assignments, "primary", "co-host", assignEvidence, now)
	if err != nil {
		t.Fatalf("assign co-host: %v", err)
	}
	if len(assignments) != 1 || len(assigned) != 2 {
		t.Fatalf("assignment must return an atomic copy: before=%+v after=%+v", assignments, assigned)
	}
	if scopeCActivePrimaryCount(assigned) != 1 {
		t.Fatalf("assign must preserve exactly one primary: %+v", assigned)
	}

	// OrganizerAssignment has no Participation side effect or seat-bearing
	// field; the caller's empty roster stays empty after management changes.
	participations := []contract.GatheringParticipation{}
	if len(participations) != 0 {
		t.Fatal("organizer management unexpectedly occupied a seat")
	}

	revoked, _, err := model.RevokeCoHost(assigned, "primary", "co-host", now.Add(time.Minute))
	if err != nil {
		t.Fatalf("revoke co-host: %v", err)
	}
	if !assigned[1].RevokedAt.IsZero() || revoked[1].RevokedAt.IsZero() {
		t.Fatalf("revoke must not mutate the input slice: before=%+v after=%+v", assigned, revoked)
	}
	if scopeCActivePrimaryCount(revoked) != 1 {
		t.Fatalf("revoke must preserve exactly one primary: %+v", revoked)
	}

	transferEvidence := scopeCHostEvidence(binding, "primary", "co-host", model.HostAuthorityTransferOrganizer, now)
	transferred, _, err := model.TransferPrimaryOrganizer(
		assigned,
		"primary",
		"co-host",
		transferEvidence,
		now.Add(2*time.Minute),
	)
	if err != nil {
		t.Fatalf("transfer organizer: %v", err)
	}
	if scopeCActivePrimaryCount(transferred) != 1 ||
		transferred[1].Role != contract.GatheringOrganizerRolePrimaryOrganizer ||
		transferred[0].Role != contract.GatheringOrganizerRoleCoHost {
		t.Fatalf("transfer was not atomic: %+v", transferred)
	}
}

func TestScopeCOrganizerMutationRejectsRevokedAuthorityEvidence(t *testing.T) {
	now := time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)
	binding := scopeCHostBinding(contract.GatheringHostSubjectKindCircle, now)
	assignments := []contract.OrganizerAssignment{{
		PersonaID: "primary", Role: contract.GatheringOrganizerRolePrimaryOrganizer,
		AuthorityEvidenceRef: binding.AuthorityEvidenceRef,
		AuthorityVersion:     binding.AuthorityVersion, AssignedAt: now, Version: 1,
	}}
	evidence := scopeCHostEvidence(binding, "primary", "co-host", model.HostAuthorityAssignOrganizer, now)
	evidence.Revoked = true
	_, _, err := model.AssignCoHost(assignments, "primary", "co-host", evidence, now)
	if !errors.Is(err, gatheringerrors.ErrGatheringHostAuthorityInvalid) {
		t.Fatalf("expected revoked authority to fail closed, got %v", err)
	}
}

func scopeCHostBinding(
	kind contract.GatheringHostSubjectKind,
	now time.Time,
) contract.HostBinding {
	return contract.HostBinding{
		HostSubjectKind: kind, HostSubjectID: "canonical-host-subject",
		AuthorityEvidenceRef: "authority/evidence/7", AuthorityVersion: 7,
		AuthorityExpiresAt: now.Add(time.Hour),
	}
}

func scopeCHostEvidence(
	binding contract.HostBinding,
	actorPersonaID string,
	organizerPersonaID string,
	action model.HostAuthorityAction,
	now time.Time,
) model.HostAuthorityEvidence {
	return model.HostAuthorityEvidence{
		HostSubjectKind: binding.HostSubjectKind, HostSubjectID: binding.HostSubjectID,
		HostReference:  string(binding.HostSubjectKind) + ":" + binding.HostSubjectID,
		ActorPersonaID: actorPersonaID, OrganizerPersonaID: organizerPersonaID,
		AuthorityEvidenceRef: binding.AuthorityEvidenceRef, AuthorityVersion: binding.AuthorityVersion,
		AuthorityDigest: "sha256:ea13d8077a78b70e28c40273c4d1a7e6c833f3493bbb7419112b1d9fde8cbc9b",
		Action:          action, Valid: true, ExpiresAt: now.Add(time.Hour),
	}
}

func scopeCActivePrimaryCount(assignments []contract.OrganizerAssignment) int {
	count := 0
	for _, assignment := range assignments {
		if assignment.Role == contract.GatheringOrganizerRolePrimaryOrganizer &&
			assignment.RevokedAt.IsZero() {
			count++
		}
	}
	return count
}
