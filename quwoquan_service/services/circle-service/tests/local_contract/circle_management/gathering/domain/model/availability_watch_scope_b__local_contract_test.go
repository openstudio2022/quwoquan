package model_test

import (
	"errors"
	"testing"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-002
func TestFullGatheringOnlyCreatesAvailabilityWatch(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 1)
	current.Participations = []model.GatheringParticipation{{
		GatheringID: current.ID, PersonaID: "persona-active",
		State: model.ParticipationStateActive, Version: 1, AttemptNo: 1,
	}}
	if _, err := model.JoinOpen(
		current,
		scopeBParticipationInput(current, "persona-watcher", 0, scopeBNow),
	); !errors.Is(err, gatheringerrors.ErrGatheringCapacityFull) {
		t.Fatalf("full join error = %v", err)
	}

	watched, err := model.WatchAvailability(current, model.AvailabilityWatchInput{
		ActorPersonaID:           "persona-watcher",
		ExpectedGatheringVersion: current.Version,
		ExpectedWatchVersion:     0,
		OccurredAt:               scopeBNow,
	})
	if err != nil {
		t.Fatalf("WatchAvailability: %v", err)
	}
	if len(watched.AvailabilityWatches) != 1 ||
		watched.AvailabilityWatches[0].Status != model.AvailabilityWatchStatusActive ||
		watched.AvailabilityWatches[0].Version != 1 {
		t.Fatalf("watch = %+v", watched.AvailabilityWatches)
	}
	if len(watched.Participations) != 1 ||
		model.CapacityAt(watched, scopeBNow).OccupiedSeats != 1 ||
		watched.RoomBindingStatus != current.RoomBindingStatus {
		t.Fatalf("watch granted participation/capacity/room access: %+v", watched)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-002
func TestWatchRequiresFullCapacityAndRootWatchCAS(t *testing.T) {
	notFull := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 2)
	if _, err := model.WatchAvailability(notFull, model.AvailabilityWatchInput{
		ActorPersonaID:           "persona-watcher",
		ExpectedGatheringVersion: notFull.Version,
		ExpectedWatchVersion:     0,
		OccurredAt:               scopeBNow,
	}); !errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden) {
		t.Fatalf("watch before full error = %v", err)
	}

	full := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 1)
	full.Participations = []model.GatheringParticipation{{
		GatheringID: full.ID, PersonaID: "persona-active",
		State: model.ParticipationStateActive, Version: 1, AttemptNo: 1,
	}}
	staleRoot := model.AvailabilityWatchInput{
		ActorPersonaID:           "persona-watcher",
		ExpectedGatheringVersion: full.Version - 1,
		ExpectedWatchVersion:     0,
		OccurredAt:               scopeBNow,
	}
	if _, err := model.WatchAvailability(full, staleRoot); !errors.Is(
		err,
		gatheringerrors.ErrGatheringVersionConflict,
	) {
		t.Fatalf("stale watch root error = %v", err)
	}
	staleChild := staleRoot
	staleChild.ExpectedGatheringVersion = full.Version
	staleChild.ExpectedWatchVersion = 1
	if _, err := model.WatchAvailability(full, staleChild); !errors.Is(
		err,
		gatheringerrors.ErrGatheringVersionConflict,
	) {
		t.Fatalf("missing watch with nonzero version error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-002
func TestUnwatchAndRewatchKeepOneMonotonicOwnedRow(t *testing.T) {
	full := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 1)
	full.Participations = []model.GatheringParticipation{{
		GatheringID: full.ID, PersonaID: "persona-active",
		State: model.ParticipationStateActive, Version: 1, AttemptNo: 1,
	}}
	watched, err := model.WatchAvailability(full, model.AvailabilityWatchInput{
		ActorPersonaID:           "persona-watcher",
		ExpectedGatheringVersion: full.Version,
		ExpectedWatchVersion:     0,
		OccurredAt:               scopeBNow,
	})
	if err != nil {
		t.Fatalf("WatchAvailability: %v", err)
	}
	first := watched.AvailabilityWatches[0]
	cancelled, err := model.UnwatchAvailability(watched, model.AvailabilityWatchInput{
		ActorPersonaID:           "persona-watcher",
		ExpectedGatheringVersion: watched.Version,
		ExpectedWatchVersion:     first.Version,
		OccurredAt:               scopeBNow.Add(time.Minute),
	})
	if err != nil {
		t.Fatalf("UnwatchAvailability: %v", err)
	}
	closed := cancelled.AvailabilityWatches[0]
	if closed.Status != model.AvailabilityWatchStatusCancelled ||
		closed.Version != first.Version+1 {
		t.Fatalf("cancelled watch = %+v", closed)
	}
	rewatched, err := model.WatchAvailability(cancelled, model.AvailabilityWatchInput{
		ActorPersonaID:           "persona-watcher",
		ExpectedGatheringVersion: cancelled.Version,
		ExpectedWatchVersion:     closed.Version,
		OccurredAt:               scopeBNow.Add(2 * time.Minute),
	})
	if err != nil {
		t.Fatalf("WatchAvailability retry: %v", err)
	}
	if len(rewatched.AvailabilityWatches) != 1 ||
		rewatched.AvailabilityWatches[0].Status != model.AvailabilityWatchStatusActive ||
		rewatched.AvailabilityWatches[0].Version != closed.Version+1 {
		t.Fatalf("rewatched rows = %+v", rewatched.AvailabilityWatches)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-002
func TestUnwatchRemainsAvailableAfterGatheringStarts(t *testing.T) {
	full := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 1)
	full.Participations = []model.GatheringParticipation{{
		GatheringID: full.ID, PersonaID: "persona-active",
		State: model.ParticipationStateActive, Version: 1, AttemptNo: 1,
	}}
	watched, err := model.WatchAvailability(full, model.AvailabilityWatchInput{
		ActorPersonaID:           "persona-watcher",
		ExpectedGatheringVersion: full.Version,
		ExpectedWatchVersion:     0,
		OccurredAt:               scopeBNow,
	})
	if err != nil {
		t.Fatalf("WatchAvailability: %v", err)
	}
	first := watched.AvailabilityWatches[0]
	cancelled, err := model.UnwatchAvailability(watched, model.AvailabilityWatchInput{
		ActorPersonaID:           "persona-watcher",
		ExpectedGatheringVersion: watched.Version,
		ExpectedWatchVersion:     first.Version,
		OccurredAt:               watched.Schedule.StartAt,
	})
	if err != nil {
		t.Fatalf("UnwatchAvailability after start: %v", err)
	}
	if cancelled.AvailabilityWatches[0].Status != model.AvailabilityWatchStatusCancelled {
		t.Fatalf("cancelled watch = %+v", cancelled.AvailabilityWatches[0])
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-002
func TestDuplicateWatchIdentityIsRejected(t *testing.T) {
	full := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 1)
	full.Participations = []model.GatheringParticipation{{
		GatheringID: full.ID, PersonaID: "persona-active",
		State: model.ParticipationStateActive, Version: 1, AttemptNo: 1,
	}}
	full.AvailabilityWatches = []contract.GatheringAvailabilityWatch{
		{
			GatheringID: full.ID, PersonaID: "persona-watcher",
			Status: model.AvailabilityWatchStatusCancelled, Version: 1,
		},
		{
			GatheringID: full.ID, PersonaID: "persona-watcher",
			Status: model.AvailabilityWatchStatusCancelled, Version: 1,
		},
	}
	if _, err := model.WatchAvailability(full, model.AvailabilityWatchInput{
		ActorPersonaID:           "persona-watcher",
		ExpectedGatheringVersion: full.Version,
		ExpectedWatchVersion:     1,
		OccurredAt:               scopeBNow,
	}); !errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden) {
		t.Fatalf("duplicate watch error = %v", err)
	}
}
