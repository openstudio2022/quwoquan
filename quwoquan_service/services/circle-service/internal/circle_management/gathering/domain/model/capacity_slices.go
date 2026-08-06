package gathering

import (
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
)

type CapacitySlice struct {
	MaxParticipants      int64
	ActiveSeatCount      int64
	InvitedSeatHoldCount int64
	OccupiedSeats        int64
	RemainingSeats       int64
	Full                 bool
}

type ChangeCapacityInput struct {
	ActorPersonaID            string
	ExpectedGatheringVersion  int64
	MaxParticipants           int64
	AcknowledgementDeadlineAt time.Time
	OccurredAt                time.Time
}

// CapacityAt is the single capacity truth used by admission decisions,
// mutations and projections. OrganizerAssignment is deliberately absent:
// authority never consumes a participant seat.
func CapacityAt(current Gathering, now time.Time) CapacitySlice {
	maxParticipants := current.PolicySet.CapacityPolicy.MaxParticipants
	var activeSeatCount int64
	var invitedSeatHoldCount int64
	for _, participation := range current.Participations {
		switch participation.State {
		case ParticipationStateActive:
			activeSeatCount++
		case ParticipationStateInvitedPending:
			if !participation.SeatHoldUntil.IsZero() &&
				participation.SeatHoldUntil.After(now) {
				invitedSeatHoldCount++
			}
		}
	}
	occupiedSeats := activeSeatCount + invitedSeatHoldCount
	remainingSeats := maxParticipants - occupiedSeats
	if remainingSeats < 0 {
		remainingSeats = 0
	}
	return CapacitySlice{
		MaxParticipants:      maxParticipants,
		ActiveSeatCount:      activeSeatCount,
		InvitedSeatHoldCount: invitedSeatHoldCount,
		OccupiedSeats:        occupiedSeats,
		RemainingSeats:       remainingSeats,
		Full:                 maxParticipants <= 0 || occupiedSeats >= maxParticipants,
	}
}

// ChangeCapacity applies the occupiedSeats lower bound in the same owner
// version boundary as admission. It never persists full as lifecycle state.
func ChangeCapacity(current Gathering, input ChangeCapacityInput) (Gathering, error) {
	if strings.TrimSpace(input.ActorPersonaID) == "" ||
		input.OccurredAt.IsZero() ||
		input.MaxParticipants <= 0 {
		return Gathering{}, ErrInvalidArgument
	}
	if input.ExpectedGatheringVersion != current.Version {
		return Gathering{}, gatheringerrors.ErrGatheringVersionConflict
	}
	if !HasActiveOrganizerAuthority(current, input.ActorPersonaID) {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	if TemporalPhaseAt(current.Schedule, input.OccurredAt).TemporalPhase !=
		TemporalPhaseUpcoming {
		return Gathering{}, gatheringerrors.ErrGatheringOperationNotAllowedInProgress
	}
	capacity := CapacityAt(current, input.OccurredAt)
	if input.MaxParticipants < capacity.OccupiedSeats {
		return Gathering{}, gatheringerrors.ErrGatheringCapacityBelowOccupiedSeats
	}
	policySet := current.PolicySet
	policySet.CapacityPolicy.MaxParticipants = input.MaxParticipants
	next, revision, changed, err := AppendMaterialGatheringRevision(
		current,
		AppendMaterialRevisionInput{
			ActorPersonaID:  input.ActorPersonaID,
			ExpectedVersion: input.ExpectedGatheringVersion,
			Purpose:         current.Purpose,
			Schedule:        current.Schedule,
			Place:           current.Place,
			PolicySet:       policySet,
			HostBinding:     current.HostBinding,
			OccurredAt:      input.OccurredAt,
		},
	)
	if err != nil {
		return Gathering{}, err
	}
	if !changed {
		return next, nil
	}
	deadlineAt := input.AcknowledgementDeadlineAt
	if deadlineAt.IsZero() {
		deadlineAt = next.Schedule.StartAt
	}
	next.Participations, err = RequireMaterialRevisionAcknowledgement(
		next.Participations,
		revision,
		deadlineAt,
	)
	if err != nil {
		return Gathering{}, err
	}
	return next, nil
}
