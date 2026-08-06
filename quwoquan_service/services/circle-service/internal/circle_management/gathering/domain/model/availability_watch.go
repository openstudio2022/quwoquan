package gathering

import (
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

type GatheringAvailabilityWatch = contract.GatheringAvailabilityWatch
type GatheringAvailabilityWatchStatus = contract.GatheringAvailabilityWatchStatus

const (
	AvailabilityWatchStatusActive    = contract.GatheringAvailabilityWatchStatusActive
	AvailabilityWatchStatusCancelled = contract.GatheringAvailabilityWatchStatusCancelled
	AvailabilityWatchStatusNotified  = contract.GatheringAvailabilityWatchStatusNotified
)

type AvailabilityWatchInput struct {
	ActorPersonaID           string
	ExpectedGatheringVersion int64
	ExpectedWatchVersion     int64
	OccurredAt               time.Time
}

// WatchAvailability is the only full-capacity response path. It creates no
// Participation, consumes no seat and grants no room access.
func WatchAvailability(current Gathering, input AvailabilityWatchInput) (Gathering, error) {
	if err := validateWatchInput(current, input); err != nil {
		return Gathering{}, err
	}
	if current.LifecycleStatus != contract.GatheringLifecycleStatusPublished ||
		TemporalPhaseAt(current.Schedule, input.OccurredAt).TemporalPhase !=
			TemporalPhaseUpcoming {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if AdmissionStateAt(current, input.OccurredAt).AdmissionState != AdmissionStateFull {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if participation, found := FindParticipation(current, input.ActorPersonaID); found && participation.State == ParticipationStateActive {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	next := cloneParticipationOwnedState(current)
	index, watch, found, duplicate := availabilityWatchIndex(next, input.ActorPersonaID)
	if duplicate {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if !found {
		if input.ExpectedWatchVersion != 0 {
			return Gathering{}, gatheringerrors.ErrGatheringVersionConflict
		}
		next.AvailabilityWatches = append(next.AvailabilityWatches, GatheringAvailabilityWatch{
			GatheringID: next.ID,
			PersonaID:   strings.TrimSpace(input.ActorPersonaID),
			Status:      AvailabilityWatchStatusActive,
			Version:     1,
			CreatedAt:   input.OccurredAt.UTC(),
			UpdatedAt:   input.OccurredAt.UTC(),
		})
	} else {
		if watch.Version != input.ExpectedWatchVersion {
			return Gathering{}, gatheringerrors.ErrGatheringVersionConflict
		}
		if watch.Status == AvailabilityWatchStatusActive {
			return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
		}
		watch.Status = AvailabilityWatchStatusActive
		watch.Version++
		watch.UpdatedAt = input.OccurredAt.UTC()
		next.AvailabilityWatches[index] = watch
	}
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

func UnwatchAvailability(current Gathering, input AvailabilityWatchInput) (Gathering, error) {
	if err := validateWatchInput(current, input); err != nil {
		return Gathering{}, err
	}
	index, watch, found, duplicate := availabilityWatchIndex(current, input.ActorPersonaID)
	if duplicate || !found || watch.Version != input.ExpectedWatchVersion {
		return Gathering{}, gatheringerrors.ErrGatheringVersionConflict
	}
	if watch.Status != AvailabilityWatchStatusActive {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	next := cloneParticipationOwnedState(current)
	watch.Status = AvailabilityWatchStatusCancelled
	watch.Version++
	watch.UpdatedAt = input.OccurredAt.UTC()
	next.AvailabilityWatches[index] = watch
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

func FindAvailabilityWatch(
	current Gathering,
	personaID string,
) (GatheringAvailabilityWatch, bool) {
	_, watch, found, duplicate := availabilityWatchIndex(current, personaID)
	if duplicate {
		return GatheringAvailabilityWatch{}, false
	}
	return watch, found
}

func validateWatchInput(current Gathering, input AvailabilityWatchInput) error {
	if strings.TrimSpace(current.ID) == "" ||
		strings.TrimSpace(input.ActorPersonaID) == "" ||
		input.OccurredAt.IsZero() {
		return ErrInvalidArgument
	}
	if input.ExpectedGatheringVersion != current.Version {
		return gatheringerrors.ErrGatheringVersionConflict
	}
	return nil
}

func availabilityWatchIndex(
	current Gathering,
	personaID string,
) (int, GatheringAvailabilityWatch, bool, bool) {
	personaID = strings.TrimSpace(personaID)
	index := -1
	var result GatheringAvailabilityWatch
	for candidate := range current.AvailabilityWatches {
		if strings.TrimSpace(current.AvailabilityWatches[candidate].PersonaID) != personaID {
			continue
		}
		if strings.TrimSpace(current.AvailabilityWatches[candidate].GatheringID) !=
			strings.TrimSpace(current.ID) ||
			index >= 0 {
			return 0, GatheringAvailabilityWatch{}, false, true
		}
		index = candidate
		result = current.AvailabilityWatches[candidate]
	}
	return index, result, index >= 0, false
}
