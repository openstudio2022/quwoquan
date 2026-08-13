// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
//
// 本文件按对象为 gathering errors.yaml 中此前未被断言的 domain 负例补齐
// 真实错误断言：每条 case 通过公开 domain 行为触发非法迁移/校验失败，
// 并用 errors.Is 断言 generated 稳定错误哨兵（与既有 scope A/B/C 测试同形态）。
package model_test

import (
	"errors"
	"testing"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

var negativePathNow = time.Date(2026, 8, 10, 9, 0, 0, 0, time.UTC)

func TestPublishGatheringRejectsIncompleteInvalidOrUndisclosedDrafts(t *testing.T) {
	tests := []struct {
		name    string
		mutate  func(current *model.Gathering)
		wantErr error
	}{
		{
			name: "missing_title_is_draft_incomplete",
			mutate: func(current *model.Gathering) {
				current.Purpose.Title = ""
			},
			wantErr: gatheringerrors.ErrGatheringDraftIncomplete,
		},
		{
			name: "end_not_after_start_is_schedule_invalid",
			mutate: func(current *model.Gathering) {
				current.Schedule.EndAt = current.Schedule.StartAt
			},
			wantErr: gatheringerrors.ErrGatheringScheduleInvalid,
		},
		{
			name: "unknown_time_disclosure_is_disclosure_invalid",
			mutate: func(current *model.Gathering) {
				current.PolicySet.DisclosurePolicy.TimeDisclosure = "not_a_disclosure"
			},
			wantErr: gatheringerrors.ErrGatheringDisclosureInvalid,
		},
		{
			name: "missing_policy_digest_is_publish_obligation_missing",
			mutate: func(current *model.Gathering) {
				current.PolicySet.PolicyDigest = ""
			},
			wantErr: gatheringerrors.ErrGatheringPublishObligationMissing,
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			current := negativePathGathering(contract.GatheringAdmissionPolicyOpen, 3)
			current.LifecycleStatus = contract.GatheringLifecycleStatusDraft
			test.mutate(&current)
			if _, err := model.PublishGathering(
				current,
				"persona-owner",
				current.Version,
				negativePathNow,
			); !errors.Is(err, test.wantErr) {
				t.Fatalf("publish error = %v, want %v", err, test.wantErr)
			}
		})
	}
}

func TestCompleteGatheringSurfacesDisputedOutcomeAsCanonicalConflict(t *testing.T) {
	current := negativePathGathering(contract.GatheringAdmissionPolicyOpen, 3)
	endedAt := current.Schedule.EndAt.Add(time.Hour)
	if _, err := model.CompleteGathering(
		current,
		"persona-owner",
		current.Version,
		contract.GatheringOutcome{
			Status:                   contract.GatheringOutcomeStatusDisputed,
			EvidenceRefs:             []contract.CanonicalObjectRef{},
			IndependentEvidenceCount: 0,
			CalculatedAt:             endedAt,
			CalculationDigest:        "sha256:16ab580baf64c884ef5cc75ce2e6d2f9c667b73b2572e838fca270aaf03241f3",
		},
		endedAt,
	); !errors.Is(err, gatheringerrors.ErrGatheringOutcomeDisputed) {
		t.Fatalf("disputed completion error = %v", err)
	}
}

func TestRevisionAcknowledgementAfterDeadlineIsReconfirmationExpired(t *testing.T) {
	deadline := negativePathNow.Add(30 * time.Minute)
	participation := negativePathActiveParticipation("persona-2", 3)
	participation.CurrentChangeAcknowledgement = contract.GatheringRevisionAcknowledgement{
		RevisionID:     "revision-2",
		RevisionNumber: 2,
		RevisionDigest: "revision-digest-2",
		Status:         contract.GatheringRevisionAcknowledgementStatusPending,
		DeadlineAt:     deadline,
	}
	if _, _, err := model.DecideRevisionAcknowledgement(
		participation,
		"revision-2",
		"revision-digest-2",
		model.AcknowledgementDecisionAccept,
		participation.Version,
		deadline.Add(time.Minute),
	); !errors.Is(err, gatheringerrors.ErrGatheringReconfirmationExpired) {
		t.Fatalf("late acknowledgement error = %v", err)
	}
}

func TestDeclareArrivalOutsideInProgressPhaseIsAttendanceConflict(t *testing.T) {
	participation := negativePathActiveParticipation("persona-2", 2)
	if _, _, err := model.DeclareArrival(
		participation,
		participation.Version,
		model.OutcomeTemporalPhaseUpcoming,
		negativePathEvidenceRefs(),
		negativePathNow,
	); !errors.Is(err, gatheringerrors.ErrGatheringAttendanceConflict) {
		t.Fatalf("upcoming-phase arrival error = %v", err)
	}
}

func TestDeclareArrivalOnClosedParticipationRequiresActiveParticipation(t *testing.T) {
	participation := negativePathActiveParticipation("persona-2", 2)
	participation.State = contract.GatheringParticipationStateClosed
	if _, _, err := model.DeclareArrival(
		participation,
		participation.Version,
		model.OutcomeTemporalPhaseInProgress,
		negativePathEvidenceRefs(),
		negativePathNow,
	); !errors.Is(err, gatheringerrors.ErrGatheringActiveParticipationRequired) {
		t.Fatalf("closed participation arrival error = %v", err)
	}
}

func TestJoinOpenWhilePausedIsAdmissionPaused(t *testing.T) {
	current := negativePathGathering(contract.GatheringAdmissionPolicyOpen, 3)
	current.AdmissionControl.Status = contract.GatheringAdmissionControlStatusPaused
	if _, err := model.JoinOpen(
		current,
		negativePathParticipationInput(current, "persona-2", 0),
	); !errors.Is(err, gatheringerrors.ErrGatheringAdmissionPaused) {
		t.Fatalf("paused-admission join error = %v", err)
	}
}

func TestJoinOpenTwiceIsAlreadyActive(t *testing.T) {
	current := negativePathGathering(contract.GatheringAdmissionPolicyOpen, 3)
	joined, err := model.JoinOpen(
		current,
		negativePathParticipationInput(current, "persona-2", 0),
	)
	if err != nil {
		t.Fatalf("first JoinOpen: %v", err)
	}
	active, found := model.FindParticipation(joined, "persona-2")
	if !found {
		t.Fatalf("joined participation missing: %+v", joined.Participations)
	}
	if _, err := model.JoinOpen(
		joined,
		negativePathParticipationInput(joined, "persona-2", active.Version),
	); !errors.Is(err, gatheringerrors.ErrGatheringAlreadyActive) {
		t.Fatalf("repeated join error = %v", err)
	}
}

func TestPrimaryOrganizerLeaveRequiresOrganizerTransfer(t *testing.T) {
	current := negativePathGathering(contract.GatheringAdmissionPolicyOpen, 3)
	if _, err := model.LeaveParticipation(
		current,
		negativePathParticipationInput(current, "persona-owner", 1),
	); !errors.Is(err, gatheringerrors.ErrGatheringOrganizerTransferRequired) {
		t.Fatalf("primary organizer leave error = %v", err)
	}
}

func negativePathGathering(
	admissionPolicy contract.GatheringAdmissionPolicy,
	maxParticipants int64,
) model.Gathering {
	return model.Gathering{
		ID:                 "gathering-negative-paths",
		Version:            5,
		CreatedByPersonaID: "persona-owner",
		HostBinding: contract.HostBinding{
			HostSubjectKind:      contract.GatheringHostSubjectKindPersona,
			HostSubjectID:        "persona-owner",
			AuthorityEvidenceRef: "authority-negative",
			AuthorityVersion:     1,
		},
		OrganizerAssignments: []contract.OrganizerAssignment{
			{
				PersonaID:            "persona-owner",
				Role:                 contract.GatheringOrganizerRolePrimaryOrganizer,
				AuthorityEvidenceRef: "authority-negative",
				AuthorityVersion:     1,
				AssignedAt:           negativePathNow.Add(-time.Hour),
				Version:              1,
			},
		},
		Purpose: contract.GatheringPurpose{
			Title:            "错误码负例专用活动",
			Summary:          "验证未断言错误码的真实触发路径。",
			TopicRefs:        []string{},
			RequirementRefs:  []string{},
			SourceObjectRefs: []contract.GatheringSourceRef{},
			CostNotice:       contract.GatheringCostNoticeFree,
		},
		Schedule: contract.GatheringSchedule{
			Timezone:          "Asia/Shanghai",
			StartAt:           negativePathNow.Add(2 * time.Hour),
			EndAt:             negativePathNow.Add(4 * time.Hour),
			AdmissionClosesAt: negativePathNow.Add(time.Hour),
		},
		Place: contract.GatheringPlace{
			Mode:              contract.GatheringPlaceModeOnline,
			OnlineLocationRef: "room://gathering-negative-paths",
		},
		PolicySet: contract.GatheringPolicySet{
			AudiencePolicy:  contract.GatheringAudiencePolicyPublic,
			AdmissionPolicy: admissionPolicy,
			CapacityPolicy:  contract.GatheringCapacityPolicy{MaxParticipants: maxParticipants},
			DisclosurePolicy: contract.GatheringDisclosurePolicy{
				TimeDisclosure:   contract.GatheringTimeDisclosureExact,
				PlaceDisclosure:  contract.GatheringPlaceDisclosureExact,
				RosterDisclosure: contract.GatheringRosterDisclosureCountOnly,
			},
			ApplicationQuestions: []contract.GatheringApplicationQuestion{},
			RiskControlPolicyRef: "risk-policy-negative",
			PolicyDecisionRef:    "policy-decision-negative",
			PolicyDigest:         "sha256:357e693239bc107a5c4d8bfe3c737fea68d38b8d6887db3e4a8cf6f279158489",
			ObligationDigest:     "obligation-digest-negative",
		},
		AdmissionControl: contract.GatheringAdmissionControl{
			Status:  contract.GatheringAdmissionControlStatusOpen,
			Version: 1,
		},
		LifecycleStatus:     contract.GatheringLifecycleStatusPublished,
		RoomBindingStatus:   contract.GatheringRoomBindingStatusReady,
		Participations:      []model.GatheringParticipation{},
		Revisions:           []contract.GatheringRevision{},
		AvailabilityWatches: []contract.GatheringAvailabilityWatch{},
		CreatedAt:           negativePathNow.Add(-time.Hour),
		UpdatedAt:           negativePathNow.Add(-time.Hour),
	}
}

func negativePathParticipationInput(
	current model.Gathering,
	personaID string,
	expectedParticipationVersion int64,
) model.ParticipationCommandInput {
	return model.ParticipationCommandInput{
		ActorPersonaID:               personaID,
		ParticipantPersonaID:         personaID,
		ExpectedGatheringVersion:     current.Version,
		ExpectedParticipationVersion: expectedParticipationVersion,
		OccurredAt:                   negativePathNow,
	}
}

func negativePathActiveParticipation(
	personaID string,
	version int64,
) contract.GatheringParticipation {
	return contract.GatheringParticipation{
		GatheringID: "gathering-negative-paths",
		PersonaID:   personaID,
		State:       contract.GatheringParticipationStateActive,
		Version:     version,
		JoinedAt:    negativePathNow.Add(-time.Hour),
		Attendance: contract.GatheringAttendance{
			Status: contract.GatheringAttendanceStatusNotDeclared,
		},
	}
}

func negativePathEvidenceRefs() []contract.CanonicalObjectRef {
	return []contract.CanonicalObjectRef{{
		ObjectTypeRef: "content.post",
		ObjectID:      "evidence-negative-1",
	}}
}
