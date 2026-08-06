package model_test

import (
	"testing"
	"time"

	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

func TestScopeCTimeEndedDoesNotAutoDeclareOccurred(t *testing.T) {
	now := time.Date(2026, 8, 6, 12, 0, 0, 0, time.UTC)
	outcome, err := model.NewOutcomeCalculator().Calculate(model.OutcomeCalculationInput{
		TemporalPhase: model.OutcomeTemporalPhaseEnded,
		Participations: []contract.GatheringParticipation{
			scopeCOutcomeActiveParticipation("participant-a", 1),
			scopeCOutcomeActiveParticipation("participant-b", 1),
		},
		CalculatedAt: now,
	})
	if err != nil {
		t.Fatalf("calculate ended outcome: %v", err)
	}
	if outcome.Status != contract.GatheringOutcomeStatusUnverified ||
		outcome.IndependentEvidenceCount != 0 ||
		outcome.CalculationDigest == "" {
		t.Fatalf("time-ended Gathering must stay unverified: %+v", outcome)
	}
}

func TestScopeCOccurredRequiresIndependentExplicitEvidence(t *testing.T) {
	now := time.Date(2026, 8, 6, 12, 0, 0, 0, time.UTC)
	one := scopeCOutcomeCompletedParticipation("participant-a", "completion-a")
	outcome, err := model.NewOutcomeCalculator().Calculate(model.OutcomeCalculationInput{
		TemporalPhase:  model.OutcomeTemporalPhaseEnded,
		Participations: []contract.GatheringParticipation{one},
		CalculatedAt:   now,
	})
	if err != nil {
		t.Fatalf("calculate one-sided evidence: %v", err)
	}
	if outcome.Status != contract.GatheringOutcomeStatusUnverified {
		t.Fatalf("one participant must not establish occurred: %+v", outcome)
	}

	two := scopeCOutcomeCompletedParticipation("participant-b", "completion-b")
	outcome, err = model.NewOutcomeCalculator().Calculate(model.OutcomeCalculationInput{
		TemporalPhase:  model.OutcomeTemporalPhaseEnded,
		Participations: []contract.GatheringParticipation{one, two},
		CalculatedAt:   now,
	})
	if err != nil {
		t.Fatalf("calculate independent evidence: %v", err)
	}
	if outcome.Status != contract.GatheringOutcomeStatusOccurred ||
		outcome.IndependentEvidenceCount != 2 ||
		len(outcome.EvidenceRefs) != 2 {
		t.Fatalf("two independent explicit facts should establish occurred: %+v", outcome)
	}
}

func TestScopeCBilateralDisagreementProducesDisputedWithoutPenaltyMutation(t *testing.T) {
	now := time.Date(2026, 8, 6, 12, 0, 0, 0, time.UTC)
	positive := scopeCOutcomeCompletedParticipation("participant-a", "completion-a")
	negative := scopeCOutcomeActiveParticipation("participant-b", 4)
	negative.Attendance = contract.GatheringAttendance{
		Status: contract.GatheringAttendanceStatusNoShow, DeclaredAt: now,
		EvidenceRefs: []contract.CanonicalObjectRef{
			scopeCOutcomeEvidence("circle.no_show", "no-show-b"),
		},
	}
	input := []contract.GatheringParticipation{positive, negative}
	outcome, err := model.NewOutcomeCalculator().Calculate(model.OutcomeCalculationInput{
		TemporalPhase:  model.OutcomeTemporalPhaseEnded,
		Participations: input,
		CalculatedAt:   now,
	})
	if err != nil {
		t.Fatalf("calculate disputed outcome: %v", err)
	}
	if outcome.Status != contract.GatheringOutcomeStatusDisputed ||
		outcome.IndependentEvidenceCount != 2 {
		t.Fatalf("bilateral disagreement must be disputed: %+v", outcome)
	}
	if input[0].State != contract.GatheringParticipationStateActive ||
		input[1].State != contract.GatheringParticipationStateActive ||
		input[0].Version != positive.Version ||
		input[1].Version != negative.Version {
		t.Fatalf("calculator applied an automatic penalty or roster mutation: %+v", input)
	}
}

func scopeCOutcomeCompletedParticipation(
	personaID string,
	evidenceID string,
) contract.GatheringParticipation {
	value := scopeCOutcomeActiveParticipation(personaID, 3)
	value.Attendance = contract.GatheringAttendance{
		Status: contract.GatheringAttendanceStatusCompleted,
		EvidenceRefs: []contract.CanonicalObjectRef{
			scopeCOutcomeEvidence("circle.completion", evidenceID),
		},
	}
	return value
}

func scopeCOutcomeActiveParticipation(
	personaID string,
	version int64,
) contract.GatheringParticipation {
	return contract.GatheringParticipation{
		GatheringID: "gathering-1",
		PersonaID:   personaID,
		State:       contract.GatheringParticipationStateActive,
		Version:     version,
		Attendance: contract.GatheringAttendance{
			Status:       contract.GatheringAttendanceStatusNotDeclared,
			EvidenceRefs: []contract.CanonicalObjectRef{},
		},
		CurrentChangeAcknowledgement: contract.GatheringRevisionAcknowledgement{
			Status: contract.GatheringRevisionAcknowledgementStatusNotRequired,
		},
	}
}

func scopeCOutcomeEvidence(
	objectTypeRef string,
	objectID string,
) contract.CanonicalObjectRef {
	return contract.CanonicalObjectRef{ObjectTypeRef: objectTypeRef, ObjectID: objectID}
}
