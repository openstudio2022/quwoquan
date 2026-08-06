package gathering

import (
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

type GatheringAdmissionControl = contract.GatheringAdmissionControl

type AdmissionState string

type TemporalPhaseSlice struct {
	TemporalPhase TemporalPhase
	EvaluatedAt   time.Time
}

type AdmissionStateSlice struct {
	AdmissionState AdmissionState
	ReasonRef      string
	EvaluatedAt    time.Time
}

const (
	TemporalPhaseUpcoming   TemporalPhase = "upcoming"
	TemporalPhaseInProgress TemporalPhase = "in_progress"
	TemporalPhaseEnded      TemporalPhase = "ended"

	AdmissionStateAccepting AdmissionState = "accepting"
	AdmissionStateFull      AdmissionState = "full"
	AdmissionStatePaused    AdmissionState = "paused"
	AdmissionStateClosed    AdmissionState = "closed"
)

type ChangeAdmissionInput struct {
	ActorPersonaID                  string
	ReasonRef                       string
	ExpectedGatheringVersion        int64
	ExpectedAdmissionControlVersion int64
	OccurredAt                      time.Time
}

func TemporalPhaseAt(
	schedule contract.GatheringSchedule,
	now time.Time,
) TemporalPhaseSlice {
	return TemporalPhaseSlice{
		TemporalPhase: ResolveTemporalPhase(Gathering{Schedule: schedule}, now),
		EvaluatedAt:   now.UTC(),
	}
}

// AdmissionStateAt derives admission from owner facts. The state is never
// written into lifecycleStatus, so releasing a pre-start seat immediately
// reopens admission when no other closing condition remains.
func AdmissionStateAt(current Gathering, now time.Time) AdmissionStateSlice {
	result := AdmissionStateSlice{EvaluatedAt: now.UTC()}
	temporal := TemporalPhaseAt(current.Schedule, now)
	if current.LifecycleStatus != contract.GatheringLifecycleStatusPublished ||
		temporal.TemporalPhase != TemporalPhaseUpcoming ||
		(!current.Schedule.AdmissionClosesAt.IsZero() &&
			!now.Before(current.Schedule.AdmissionClosesAt)) {
		result.AdmissionState = AdmissionStateClosed
		return result
	}
	switch current.PolicySet.AdmissionPolicy {
	case contract.GatheringAdmissionPolicyOpen,
		contract.GatheringAdmissionPolicyApproval,
		contract.GatheringAdmissionPolicyInviteOnly:
	default:
		result.AdmissionState = AdmissionStateClosed
		return result
	}
	if current.AdmissionControl.Status == contract.GatheringAdmissionControlStatusPaused {
		result.AdmissionState = AdmissionStatePaused
		result.ReasonRef = current.AdmissionControl.ReasonRef
		return result
	}
	if current.AdmissionControl.Status != contract.GatheringAdmissionControlStatusOpen {
		result.AdmissionState = AdmissionStateClosed
		return result
	}
	if CapacityAt(current, now).Full {
		result.AdmissionState = AdmissionStateFull
		return result
	}
	result.AdmissionState = AdmissionStateAccepting
	return result
}

func PauseAdmission(current Gathering, input ChangeAdmissionInput) (Gathering, error) {
	if err := validateAdmissionChange(current, input); err != nil {
		return Gathering{}, err
	}
	if !HasActiveOrganizerAuthority(current, input.ActorPersonaID) {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	if current.AdmissionControl.Status != contract.GatheringAdmissionControlStatusOpen ||
		AdmissionStateAtIgnoringControl(current, input.OccurredAt) == AdmissionStateClosed {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	next := cloneParticipationOwnedState(current)
	next.AdmissionControl.Status = contract.GatheringAdmissionControlStatusPaused
	next.AdmissionControl.PausedByPersonaID = strings.TrimSpace(input.ActorPersonaID)
	next.AdmissionControl.ReasonRef = strings.TrimSpace(input.ReasonRef)
	next.AdmissionControl.PausedAt = input.OccurredAt.UTC()
	next.AdmissionControl.Version++
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

func ResumeAdmission(current Gathering, input ChangeAdmissionInput) (Gathering, error) {
	if err := validateAdmissionChange(current, input); err != nil {
		return Gathering{}, err
	}
	if !HasActiveOrganizerAuthority(current, input.ActorPersonaID) {
		return Gathering{}, gatheringerrors.ErrGatheringPermissionDenied
	}
	if current.AdmissionControl.Status != contract.GatheringAdmissionControlStatusPaused {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if AdmissionStateAtIgnoringControl(current, input.OccurredAt) == AdmissionStateClosed {
		return Gathering{}, gatheringerrors.ErrGatheringAdmissionClosed
	}
	next := cloneParticipationOwnedState(current)
	next.AdmissionControl.Status = contract.GatheringAdmissionControlStatusOpen
	next.AdmissionControl.PausedByPersonaID = ""
	next.AdmissionControl.ReasonRef = ""
	next.AdmissionControl.PausedAt = time.Time{}
	next.AdmissionControl.Version++
	touchParticipationRoot(&next, input.OccurredAt)
	return next, nil
}

func validateAdmissionChange(current Gathering, input ChangeAdmissionInput) error {
	if strings.TrimSpace(input.ActorPersonaID) == "" || input.OccurredAt.IsZero() {
		return ErrInvalidArgument
	}
	if input.ExpectedGatheringVersion != current.Version {
		return gatheringerrors.ErrGatheringVersionConflict
	}
	if input.ExpectedAdmissionControlVersion != current.AdmissionControl.Version {
		return gatheringerrors.ErrGatheringVersionConflict
	}
	return nil
}

func requireAdmissionAccepting(current Gathering, now time.Time, consumeSeat bool) error {
	switch AdmissionStateAt(current, now).AdmissionState {
	case AdmissionStateAccepting:
		return nil
	case AdmissionStateFull:
		if consumeSeat {
			return gatheringerrors.ErrGatheringCapacityFull
		}
		return nil
	case AdmissionStatePaused:
		return gatheringerrors.ErrGatheringAdmissionPaused
	default:
		return gatheringerrors.ErrGatheringAdmissionClosed
	}
}

// requireAdmissionOpenForHeldSeat checks only irreversible closing facts.
// Manual pause and full do not invalidate an already-reserved invitation.
func requireAdmissionOpenForHeldSeat(current Gathering, now time.Time) error {
	if AdmissionStateAtIgnoringControl(current, now) == AdmissionStateClosed {
		return gatheringerrors.ErrGatheringAdmissionClosed
	}
	return nil
}

func AdmissionStateAtIgnoringControl(
	current Gathering,
	now time.Time,
) AdmissionState {
	temporal := TemporalPhaseAt(current.Schedule, now)
	if current.LifecycleStatus != contract.GatheringLifecycleStatusPublished ||
		temporal.TemporalPhase != TemporalPhaseUpcoming ||
		(!current.Schedule.AdmissionClosesAt.IsZero() &&
			!now.Before(current.Schedule.AdmissionClosesAt)) {
		return AdmissionStateClosed
	}
	switch current.PolicySet.AdmissionPolicy {
	case contract.GatheringAdmissionPolicyOpen,
		contract.GatheringAdmissionPolicyApproval,
		contract.GatheringAdmissionPolicyInviteOnly:
	default:
		return AdmissionStateClosed
	}
	if CapacityAt(current, now).Full {
		return AdmissionStateFull
	}
	return AdmissionStateAccepting
}
