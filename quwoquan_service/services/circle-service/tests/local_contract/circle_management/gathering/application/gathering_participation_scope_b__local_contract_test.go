// readiness_case: join-gathering-local
// readiness_case: approve-gathering-participant-local
// readiness_case: leave-gathering-local
package application_test

import (
	"sync"
	"testing"
	"time"

	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestParticipationFacadeReplaysSameReceiptWithoutSecondMutation(t *testing.T) {
	now := time.Now().UTC()
	store := newMemoryStore()
	initial := scopeBApplicationGathering(now, contract.GatheringAdmissionPolicyOpen, 2)
	store.value = &initial
	facade := app.NewCommandFacade(store)
	command := app.GatheringParticipationVersionCommand{
		GatheringID:                  initial.ID,
		ExpectedGatheringVersion:     initial.Version,
		ExpectedParticipationVersion: 0,
	}
	ctx := commandContext("persona-2", "scope-b-join")

	first, err := facade.JoinOpenGathering(ctx, command)
	if err != nil {
		t.Fatalf("JoinOpenGathering: %v", err)
	}
	replay, err := facade.JoinOpenGathering(ctx, command)
	if err != nil {
		t.Fatalf("JoinOpenGathering replay: %v", err)
	}
	stored := store.mustLoad(t)
	if first.IdempotentReplay || !replay.IdempotentReplay ||
		first.AggregateVersion != replay.AggregateVersion ||
		len(stored.Participations) != 1 ||
		stored.Participations[0].Version != 1 {
		t.Fatalf("idempotent replay drift: first=%+v replay=%+v stored=%+v", first, replay, stored.Participations)
	}

	changedPayload := command
	changedPayload.ExpectedGatheringVersion++
	if _, err := facade.JoinOpenGathering(ctx, changedPayload); err == nil {
		t.Fatal("same idempotency key with a different command digest must fail")
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-002
func TestConcurrentInviteFacadesCannotOverbookOneSeat(t *testing.T) {
	now := time.Now().UTC()
	store := newMemoryStore()
	initial := scopeBApplicationGathering(now, contract.GatheringAdmissionPolicyInviteOnly, 1)
	store.value = &initial
	facade := app.NewCommandFacade(store)

	start := make(chan struct{})
	results := make(chan error, 2)
	var wait sync.WaitGroup
	for index, personaID := range []string{"persona-2", "persona-3"} {
		index, personaID := index, personaID
		wait.Add(1)
		go func() {
			defer wait.Done()
			<-start
			_, err := facade.InviteToGathering(
				commandContext("persona-owner", "scope-b-invite-"+personaID),
				app.InviteToGatheringCommand{
					GatheringID:                  initial.ID,
					ParticipantPersonaID:         personaID,
					SeatHoldUntil:                now.Add(time.Hour),
					ExpectedGatheringVersion:     initial.Version,
					ExpectedParticipationVersion: 0,
				},
			)
			_ = index
			results <- err
		}()
	}
	close(start)
	wait.Wait()
	close(results)

	successes := 0
	failures := 0
	for err := range results {
		if err == nil {
			successes++
		} else {
			failures++
		}
	}
	stored := store.mustLoad(t)
	capacity := model.CapacityAt(stored, now)
	if successes != 1 || failures != 1 || capacity.OccupiedSeats != 1 ||
		len(stored.Participations) != 1 {
		t.Fatalf(
			"concurrent invite successes=%d failures=%d capacity=%+v participations=%+v",
			successes,
			failures,
			capacity,
			stored.Participations,
		)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-002
func TestParticipationFacadeReviewsApplicationAndApprovedParticipantLeaves(t *testing.T) {
	now := time.Now().UTC()
	store := newMemoryStore()
	initial := scopeBApplicationGathering(now, contract.GatheringAdmissionPolicyApproval, 2)
	store.value = &initial
	facade := app.NewCommandFacade(store)

	applied, err := facade.ApplyToGathering(
		commandContext("persona-applicant", "scope-b-apply"),
		app.ApplyToGatheringCommand{
			GatheringParticipationVersionCommand: app.GatheringParticipationVersionCommand{
				GatheringID:                  initial.ID,
				ExpectedGatheringVersion:     initial.Version,
				ExpectedParticipationVersion: 0,
			},
			Answers: []model.GatheringApplicationAnswer{},
		},
	)
	if err != nil || applied.ParticipationVersion == 0 {
		t.Fatalf("apply to Gathering: result=%+v err=%v", applied, err)
	}

	approved, err := facade.ReviewGatheringApplication(
		commandContext("persona-owner", "scope-b-approve"),
		app.ReviewGatheringApplicationCommand{
			GatheringID:                  initial.ID,
			ParticipantPersonaID:         "persona-applicant",
			Decision:                     "approve",
			ReasonRef:                    "review/approved",
			ExpectedGatheringVersion:     applied.AggregateVersion,
			ExpectedParticipationVersion: applied.ParticipationVersion,
		},
	)
	if err != nil ||
		approved.ParticipationState !=
			gatheringclient.GatheringParticipationStateActive ||
		approved.ParticipationVersion == 0 {
		t.Fatalf("approve Gathering application: result=%+v err=%v", approved, err)
	}

	left, err := facade.LeaveGathering(
		commandContext("persona-applicant", "scope-b-leave"),
		app.GatheringParticipationVersionCommand{
			GatheringID:                  initial.ID,
			ExpectedGatheringVersion:     approved.AggregateVersion,
			ExpectedParticipationVersion: approved.ParticipationVersion,
		},
	)
	if err != nil ||
		left.ParticipationState !=
			gatheringclient.GatheringParticipationStateClosed {
		t.Fatalf("leave approved Gathering: result=%+v err=%v", left, err)
	}
}

func scopeBApplicationGathering(
	now time.Time,
	admissionPolicy contract.GatheringAdmissionPolicy,
	maxParticipants int64,
) model.Gathering {
	return model.Gathering{
		ID:      "gathering-scope-b-application",
		Version: 7,
		OrganizerAssignments: []contract.OrganizerAssignment{{
			PersonaID:            "persona-owner",
			Role:                 contract.GatheringOrganizerRolePrimaryOrganizer,
			AuthorityEvidenceRef: "authority-1",
			AuthorityVersion:     1,
			AssignedAt:           now.Add(-time.Hour),
			Version:              1,
		}},
		Schedule: contract.GatheringSchedule{
			Timezone:          "Asia/Shanghai",
			StartAt:           now.Add(2 * time.Hour),
			EndAt:             now.Add(4 * time.Hour),
			AdmissionClosesAt: now.Add(time.Hour),
		},
		PolicySet: contract.GatheringPolicySet{
			AdmissionPolicy:      admissionPolicy,
			CapacityPolicy:       contract.GatheringCapacityPolicy{MaxParticipants: maxParticipants},
			ApplicationQuestions: []contract.GatheringApplicationQuestion{},
		},
		AdmissionControl: contract.GatheringAdmissionControl{
			Status:  contract.GatheringAdmissionControlStatusOpen,
			Version: 1,
		},
		LifecycleStatus:     contract.GatheringLifecycleStatusPublished,
		RoomBindingStatus:   contract.GatheringRoomBindingStatusReady,
		Participations:      []model.GatheringParticipation{},
		AvailabilityWatches: []contract.GatheringAvailabilityWatch{},
		CreatedAt:           now.Add(-time.Hour),
		UpdatedAt:           now.Add(-time.Hour),
	}
}
