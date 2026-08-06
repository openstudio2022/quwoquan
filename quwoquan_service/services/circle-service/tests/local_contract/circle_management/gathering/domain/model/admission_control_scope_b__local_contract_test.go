package model_test

import (
	"errors"
	"testing"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-004
func TestR10AdmissionClosesAtDeadlineAndNeverReopensAfterStart(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 3)
	before := model.AdmissionStateAt(current, current.Schedule.AdmissionClosesAt.Add(-time.Nanosecond))
	if before.AdmissionState != model.AdmissionStateAccepting {
		t.Fatalf("before deadline state = %+v", before)
	}
	atDeadline := model.AdmissionStateAt(current, current.Schedule.AdmissionClosesAt)
	if atDeadline.AdmissionState != model.AdmissionStateClosed {
		t.Fatalf("deadline state = %+v", atDeadline)
	}
	atStart := model.AdmissionStateAt(current, current.Schedule.StartAt)
	if atStart.AdmissionState != model.AdmissionStateClosed {
		t.Fatalf("start state = %+v", atStart)
	}

	input := scopeBParticipationInput(current, "persona-2", 0, current.Schedule.StartAt)
	if _, err := model.JoinOpen(current, input); !errors.Is(
		err,
		gatheringerrors.ErrGatheringAdmissionClosed,
	) {
		t.Fatalf("join after start error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-002
func TestTemporalPhaseUsesScheduleBoundaries(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 3)
	if phase := model.TemporalPhaseAt(
		current.Schedule,
		current.Schedule.StartAt.Add(-time.Nanosecond),
	); phase.TemporalPhase != model.TemporalPhaseUpcoming {
		t.Fatalf("before start phase = %+v", phase)
	}
	if phase := model.TemporalPhaseAt(
		current.Schedule,
		current.Schedule.StartAt,
	); phase.TemporalPhase != model.TemporalPhaseInProgress {
		t.Fatalf("at start phase = %+v", phase)
	}
	if phase := model.TemporalPhaseAt(
		current.Schedule,
		current.Schedule.EndAt,
	); phase.TemporalPhase != model.TemporalPhaseEnded {
		t.Fatalf("at end phase = %+v", phase)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-004
func TestPauseResumeUsesRootAndAdmissionControlVersions(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyApproval, 3)
	paused, err := model.PauseAdmission(current, model.ChangeAdmissionInput{
		ActorPersonaID:                  "persona-owner",
		ReasonRef:                       "weather-check",
		ExpectedGatheringVersion:        current.Version,
		ExpectedAdmissionControlVersion: current.AdmissionControl.Version,
		OccurredAt:                      scopeBNow,
	})
	if err != nil {
		t.Fatalf("PauseAdmission: %v", err)
	}
	if paused.AdmissionControl.Status != contract.GatheringAdmissionControlStatusPaused ||
		paused.AdmissionControl.Version != current.AdmissionControl.Version+1 ||
		model.AdmissionStateAt(paused, scopeBNow).AdmissionState != model.AdmissionStatePaused {
		t.Fatalf("paused control/state = %+v / %+v", paused.AdmissionControl, model.AdmissionStateAt(paused, scopeBNow))
	}

	stale := model.ChangeAdmissionInput{
		ActorPersonaID:                  "persona-owner",
		ExpectedGatheringVersion:        paused.Version,
		ExpectedAdmissionControlVersion: current.AdmissionControl.Version,
		OccurredAt:                      scopeBNow.Add(time.Minute),
	}
	if _, err := model.ResumeAdmission(paused, stale); !errors.Is(
		err,
		gatheringerrors.ErrGatheringVersionConflict,
	) {
		t.Fatalf("stale admission version error = %v", err)
	}
	stale.ExpectedAdmissionControlVersion = paused.AdmissionControl.Version
	resumed, err := model.ResumeAdmission(paused, stale)
	if err != nil {
		t.Fatalf("ResumeAdmission: %v", err)
	}
	if resumed.AdmissionControl.Status != contract.GatheringAdmissionControlStatusOpen ||
		resumed.AdmissionControl.Version != paused.AdmissionControl.Version+1 ||
		model.AdmissionStateAt(resumed, scopeBNow.Add(time.Minute)).AdmissionState != model.AdmissionStateAccepting {
		t.Fatalf("resumed control/state = %+v / %+v", resumed.AdmissionControl, model.AdmissionStateAt(resumed, scopeBNow.Add(time.Minute)))
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-004
func TestResumeKeepsFullDerivedAndRejectsStartedGathering(t *testing.T) {
	full := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 1)
	full.AdmissionControl.Status = contract.GatheringAdmissionControlStatusPaused
	full.Participations = []model.GatheringParticipation{{
		GatheringID: full.ID, PersonaID: "persona-2",
		State: model.ParticipationStateActive, Version: 1, AttemptNo: 1,
	}}
	resumed, err := model.ResumeAdmission(full, model.ChangeAdmissionInput{
		ActorPersonaID:                  "persona-owner",
		ExpectedGatheringVersion:        full.Version,
		ExpectedAdmissionControlVersion: full.AdmissionControl.Version,
		OccurredAt:                      scopeBNow,
	})
	if err != nil {
		t.Fatalf("resume full control: %v", err)
	}
	if state := model.AdmissionStateAt(resumed, scopeBNow); state.AdmissionState != model.AdmissionStateFull {
		t.Fatalf("resumed full state = %+v", state)
	}

	started := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 3)
	started.AdmissionControl.Status = contract.GatheringAdmissionControlStatusPaused
	if _, err := model.ResumeAdmission(started, model.ChangeAdmissionInput{
		ActorPersonaID:                  "persona-owner",
		ExpectedGatheringVersion:        started.Version,
		ExpectedAdmissionControlVersion: started.AdmissionControl.Version,
		OccurredAt:                      started.Schedule.StartAt,
	}); !errors.Is(err, gatheringerrors.ErrGatheringAdmissionClosed) {
		t.Fatalf("resume started error = %v", err)
	}
}
