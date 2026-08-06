package model_test

import (
	"errors"
	"testing"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-005
func TestR8CapacityCountsOnlyActiveAndUnexpiredInvitationHolds(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 5)
	current.Participations = []model.GatheringParticipation{
		{
			GatheringID: current.ID, PersonaID: "active",
			State: model.ParticipationStateActive, Version: 1, AttemptNo: 1,
		},
		{
			GatheringID: current.ID, PersonaID: "held",
			State:         model.ParticipationStateInvitedPending,
			SeatHoldUntil: scopeBNow.Add(time.Second),
			Version:       1, AttemptNo: 1,
		},
		{
			GatheringID: current.ID, PersonaID: "expired-at-boundary",
			State:         model.ParticipationStateInvitedPending,
			SeatHoldUntil: scopeBNow,
			Version:       1, AttemptNo: 1,
		},
		{
			GatheringID: current.ID, PersonaID: "applicant",
			State:   model.ParticipationStateApplicationPending,
			Version: 1, AttemptNo: 1,
		},
	}
	current.OrganizerAssignments = append(
		current.OrganizerAssignments,
		contract.OrganizerAssignment{
			PersonaID: "organizer-only",
			Role:      contract.GatheringOrganizerRoleCoHost,
			Version:   1,
		},
	)

	capacity := model.CapacityAt(current, scopeBNow)
	if capacity.OccupiedSeats != 2 || capacity.RemainingSeats != 3 ||
		capacity.MaxParticipants != 5 {
		t.Fatalf("capacity = %+v", capacity)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestInvitationSeatHoldIsAtomicUnderAggregateCAS(t *testing.T) {
	snapshot := scopeBGathering(contract.GatheringAdmissionPolicyInviteOnly, 1)
	firstInput := model.InviteParticipationInput{
		ParticipationCommandInput: model.ParticipationCommandInput{
			ActorPersonaID: "persona-owner", ParticipantPersonaID: "persona-2",
			ExpectedGatheringVersion:     snapshot.Version,
			ExpectedParticipationVersion: 0,
			OccurredAt:                   scopeBNow,
		},
		SeatHoldUntil: scopeBNow.Add(10 * time.Minute),
	}
	secondInput := firstInput
	secondInput.ParticipantPersonaID = "persona-3"

	firstCommit, err := model.Invite(snapshot, firstInput)
	if err != nil {
		t.Fatalf("first Invite: %v", err)
	}
	if got := model.CapacityAt(firstCommit, scopeBNow).OccupiedSeats; got != 1 {
		t.Fatalf("first hold occupied seats = %d", got)
	}
	if _, err := model.Invite(firstCommit, secondInput); !errors.Is(
		err,
		gatheringerrors.ErrGatheringVersionConflict,
	) {
		t.Fatalf("losing snapshot CAS error = %v", err)
	}

	secondInput.ExpectedGatheringVersion = firstCommit.Version
	if _, err := model.Invite(firstCommit, secondInput); !errors.Is(
		err,
		gatheringerrors.ErrGatheringCapacityFull,
	) {
		t.Fatalf("fresh second invite full error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-005
func TestCapacityChangeCannotGoBelowOccupiedSeats(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 3)
	current.Participations = []model.GatheringParticipation{
		{
			GatheringID: current.ID, PersonaID: "persona-2",
			State: model.ParticipationStateActive, Version: 1, AttemptNo: 1,
		},
		{
			GatheringID: current.ID, PersonaID: "persona-3",
			State:         model.ParticipationStateInvitedPending,
			SeatHoldUntil: scopeBNow.Add(time.Minute),
			Version:       1, AttemptNo: 1,
		},
	}
	if _, err := model.ChangeCapacity(current, model.ChangeCapacityInput{
		ActorPersonaID:           "persona-owner",
		ExpectedGatheringVersion: current.Version,
		MaxParticipants:          1,
		OccurredAt:               scopeBNow,
	}); !errors.Is(err, gatheringerrors.ErrGatheringCapacityBelowOccupiedSeats) {
		t.Fatalf("below occupied error = %v", err)
	}
	changed, err := model.ChangeCapacity(current, model.ChangeCapacityInput{
		ActorPersonaID:            "persona-owner",
		ExpectedGatheringVersion:  current.Version,
		MaxParticipants:           2,
		AcknowledgementDeadlineAt: scopeBNow.Add(90 * time.Minute),
		OccurredAt:                scopeBNow,
	})
	if err != nil {
		t.Fatalf("ChangeCapacity: %v", err)
	}
	if changed.PolicySet.CapacityPolicy.MaxParticipants != 2 ||
		changed.Version != current.Version+1 ||
		len(changed.Revisions) != 1 ||
		changed.CurrentGatheringRevisionID == "" {
		t.Fatalf("capacity change = %+v", changed.PolicySet.CapacityPolicy)
	}
	active := scopeBParticipation(t, changed, "persona-2")
	if active.CurrentChangeAcknowledgement.Status != contract.GatheringRevisionAcknowledgementStatusPending ||
		active.CurrentChangeAcknowledgement.RevisionID != changed.CurrentGatheringRevisionID ||
		active.CurrentChangeAcknowledgement.DeadlineAt != scopeBNow.Add(90*time.Minute) ||
		active.Version != 2 {
		t.Fatalf("active capacity acknowledgement = %+v", active.CurrentChangeAcknowledgement)
	}
	invited := scopeBParticipation(t, changed, "persona-3")
	if invited.Version != 1 ||
		invited.CurrentChangeAcknowledgement.Status == contract.GatheringRevisionAcknowledgementStatusPending {
		t.Fatalf("invited hold was asked to acknowledge: %+v", invited)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-005
func TestSeatReleaseDerivesAdmissionReopenWithoutWaitlistMutation(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 1)
	joined, err := model.JoinOpen(current, scopeBParticipationInput(current, "persona-2", 0, scopeBNow))
	if err != nil {
		t.Fatalf("JoinOpen: %v", err)
	}
	if state := model.AdmissionStateAt(joined, scopeBNow); state.AdmissionState != model.AdmissionStateFull {
		t.Fatalf("full admission state = %+v", state)
	}
	active := scopeBParticipation(t, joined, "persona-2")
	left, err := model.LeaveParticipation(
		joined,
		scopeBParticipationInput(joined, "persona-2", active.Version, scopeBNow.Add(time.Minute)),
	)
	if err != nil {
		t.Fatalf("LeaveParticipation: %v", err)
	}
	if state := model.AdmissionStateAt(left, scopeBNow.Add(time.Minute)); state.AdmissionState != model.AdmissionStateAccepting {
		t.Fatalf("released admission state = %+v", state)
	}
	if len(left.AvailabilityWatches) != 0 {
		t.Fatalf("seat release mutated waitlist/watch state: %+v", left.AvailabilityWatches)
	}
}
