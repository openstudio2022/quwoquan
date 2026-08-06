package model_test

import (
	"errors"
	"testing"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

func TestScopeCMaterialRevisionRequiresIndependentCurrentAcknowledgement(t *testing.T) {
	now := time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)
	participations := []contract.GatheringParticipation{
		scopeCAttendanceActiveParticipation("participant-a", 3),
		scopeCAttendanceActiveParticipation("participant-b", 7),
		{
			GatheringID: "gathering-1", PersonaID: "closed-participant",
			State: contract.GatheringParticipationStateClosed, Version: 4,
		},
	}
	revision := contract.GatheringRevision{
		RevisionID: "revision-2", RevisionNumber: 2, Digest: "revision-digest-2",
		MaterialChange: true, CreatedAt: now,
	}
	updated, err := model.RequireMaterialRevisionAcknowledgement(
		participations,
		revision,
		now.Add(time.Hour),
	)
	if err != nil {
		t.Fatalf("require material acknowledgement: %v", err)
	}
	for index := 0; index < 2; index++ {
		ack := updated[index].CurrentChangeAcknowledgement
		if ack.Status != contract.GatheringRevisionAcknowledgementStatusPending ||
			ack.RevisionID != revision.RevisionID ||
			ack.RevisionDigest != revision.Digest {
			t.Fatalf("participant %d did not receive exact current acknowledgement: %+v", index, ack)
		}
		if updated[index].Version != participations[index].Version+1 {
			t.Fatalf("participant %d version was not advanced independently", index)
		}
	}
	if updated[2].Version != participations[2].Version ||
		updated[2].CurrentChangeAcknowledgement.Status ==
			contract.GatheringRevisionAcknowledgementStatusPending {
		t.Fatalf("closed participation must not be enrolled: %+v", updated[2])
	}

	accepted, fact, err := model.DecideRevisionAcknowledgement(
		updated[0],
		revision.RevisionID,
		revision.Digest,
		model.AcknowledgementDecisionAccept,
		updated[0].Version,
		now.Add(time.Minute),
	)
	if err != nil {
		t.Fatalf("accept current revision: %v", err)
	}
	if accepted.CurrentChangeAcknowledgement.Status !=
		contract.GatheringRevisionAcknowledgementStatusAccepted ||
		updated[1].CurrentChangeAcknowledgement.Status !=
			contract.GatheringRevisionAcknowledgementStatusPending {
		t.Fatalf("one participant must not consent for another: accepted=%+v other=%+v", accepted, updated[1])
	}
	if fact.ParticipantPersonaID != "participant-a" ||
		fact.RevisionID != revision.RevisionID ||
		fact.RevisionNumber != revision.RevisionNumber {
		t.Fatalf("incomplete acknowledgement audit fact: %+v", fact)
	}
}

func TestScopeCRevisionAcknowledgementRejectsForgedOrStaleConsent(t *testing.T) {
	now := time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)
	current := scopeCAttendanceActiveParticipation("participant-a", 5)
	current.CurrentChangeAcknowledgement = contract.GatheringRevisionAcknowledgement{
		RevisionID: "revision-4", RevisionNumber: 4, RevisionDigest: "digest-4",
		Status:     contract.GatheringRevisionAcknowledgementStatusPending,
		DeadlineAt: now.Add(time.Hour),
	}
	for _, testCase := range []struct {
		name       string
		revisionID string
		digest     string
		version    int64
	}{
		{name: "forged revision", revisionID: "revision-attacker", digest: "digest-4", version: 5},
		{name: "forged digest", revisionID: "revision-4", digest: "digest-attacker", version: 5},
		{name: "stale participation", revisionID: "revision-4", digest: "digest-4", version: 4},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			_, _, err := model.DecideRevisionAcknowledgement(
				current,
				testCase.revisionID,
				testCase.digest,
				model.AcknowledgementDecisionAccept,
				testCase.version,
				now,
			)
			if err == nil {
				t.Fatal("forged or stale acknowledgement unexpectedly succeeded")
			}
			if !errors.Is(err, gatheringerrors.ErrGatheringReconfirmationRequired) &&
				!errors.Is(err, gatheringerrors.ErrGatheringParticipationConflict) {
				t.Fatalf("unexpected structured error: %v", err)
			}
		})
	}
}

func TestScopeCDeclineThenExitChangesOnlyCurrentParticipation(t *testing.T) {
	now := time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)
	current := scopeCAttendanceActiveParticipation("participant-a", 8)
	current.CurrentChangeAcknowledgement = contract.GatheringRevisionAcknowledgement{
		RevisionID: "revision-5", RevisionNumber: 5, RevisionDigest: "digest-5",
		Status:     contract.GatheringRevisionAcknowledgementStatusPending,
		DeadlineAt: now.Add(time.Hour),
	}
	declined, fact, err := model.DecideRevisionAcknowledgement(
		current,
		"revision-5",
		"digest-5",
		model.AcknowledgementDecisionDecline,
		8,
		now,
	)
	if err != nil {
		t.Fatalf("decline current revision: %v", err)
	}
	if declined.CurrentChangeAcknowledgement.Status !=
		contract.GatheringRevisionAcknowledgementStatusDeclined ||
		fact.Operation != "DeclineGatheringRevision" {
		t.Fatalf("decline was not explicit: participation=%+v fact=%+v", declined, fact)
	}
	exited, _, err := model.ExitDeclinedRevision(declined, declined.Version, now.Add(time.Minute))
	if err != nil {
		t.Fatalf("exit after decline: %v", err)
	}
	if exited.State != contract.GatheringParticipationStateClosed ||
		exited.ClosedReason != contract.GatheringParticipationClosedReasonLeft ||
		exited.ClosedByPersonaID != "participant-a" {
		t.Fatalf("unexpected exit state: %+v", exited)
	}
}

func TestScopeCArrivalAndEarlyLeaveArePerParticipantFacts(t *testing.T) {
	now := time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)
	current := scopeCAttendanceActiveParticipation("participant-a", 2)
	arrivalEvidence := []contract.CanonicalObjectRef{
		scopeCAttendanceEvidence("circle.check_in", "arrival-a"),
	}
	arrived, arrivalFact, err := model.DeclareArrival(
		current,
		2,
		model.OutcomeTemporalPhaseInProgress,
		arrivalEvidence,
		now,
	)
	if err != nil {
		t.Fatalf("declare arrival: %v", err)
	}
	if arrived.Attendance.Status != contract.GatheringAttendanceStatusArrived ||
		arrivalFact.ParticipantPersonaID != "participant-a" {
		t.Fatalf("unexpected arrival: participation=%+v fact=%+v", arrived, arrivalFact)
	}

	left, leaveFact, err := model.DeclareLeaveEarly(
		arrived,
		arrived.Version,
		model.OutcomeTemporalPhaseInProgress,
		[]contract.CanonicalObjectRef{
			scopeCAttendanceEvidence("circle.check_out", "leave-a"),
		},
		now.Add(30*time.Minute),
	)
	if err != nil {
		t.Fatalf("declare early leave: %v", err)
	}
	if left.Attendance.Status != contract.GatheringAttendanceStatusLeftEarly ||
		len(left.Attendance.EvidenceRefs) != 2 ||
		leaveFact.ParticipantPersonaID != "participant-a" {
		t.Fatalf("unexpected early leave: participation=%+v fact=%+v", left, leaveFact)
	}
}

func TestScopeCCompleteSelfDoesNotSelectAggregateOutcome(t *testing.T) {
	now := time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)
	current := scopeCAttendanceActiveParticipation("participant-a", 2)
	current.Attendance = contract.GatheringAttendance{
		Status:     contract.GatheringAttendanceStatusArrived,
		DeclaredAt: now.Add(-time.Hour),
		EvidenceRefs: []contract.CanonicalObjectRef{
			scopeCAttendanceEvidence("circle.check_in", "arrival-a"),
		},
	}
	completed, fact, err := model.CompleteSelf(
		current,
		2,
		model.OutcomeTemporalPhaseEnded,
		[]contract.CanonicalObjectRef{
			scopeCAttendanceEvidence("circle.completion", "completion-a"),
		},
		now,
	)
	if err != nil {
		t.Fatalf("complete self: %v", err)
	}
	if completed.Attendance.Status != contract.GatheringAttendanceStatusCompleted ||
		fact.Operation != "CompleteGatheringSelf" {
		t.Fatalf("unexpected self completion: participation=%+v fact=%+v", completed, fact)
	}
	// This result is a Participation, not Gathering: lifecycle and aggregate
	// Outcome are outside CompleteSelf's calculation boundary.
}

func scopeCAttendanceActiveParticipation(
	personaID string,
	version int64,
) contract.GatheringParticipation {
	return contract.GatheringParticipation{
		GatheringID: "gathering-1", PersonaID: personaID,
		State: contract.GatheringParticipationStateActive, Version: version,
		Attendance: contract.GatheringAttendance{
			Status:       contract.GatheringAttendanceStatusNotDeclared,
			EvidenceRefs: []contract.CanonicalObjectRef{},
		},
		CurrentChangeAcknowledgement: contract.GatheringRevisionAcknowledgement{
			Status: contract.GatheringRevisionAcknowledgementStatusNotRequired,
		},
	}
}

func scopeCAttendanceEvidence(
	objectTypeRef string,
	objectID string,
) contract.CanonicalObjectRef {
	return contract.CanonicalObjectRef{ObjectTypeRef: objectTypeRef, ObjectID: objectID}
}
