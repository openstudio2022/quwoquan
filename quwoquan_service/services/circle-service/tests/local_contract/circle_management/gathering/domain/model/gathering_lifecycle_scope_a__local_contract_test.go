package model_test

import (
	"errors"
	"testing"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

var scopeABaseTime = time.Date(2026, 8, 1, 8, 0, 0, 0, time.UTC)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestScopeACreateDraftOwnsInitialRevisionWithoutBindingRoom(t *testing.T) {
	current := scopeAMustDraft(t)

	if current.LifecycleStatus != contract.GatheringLifecycleStatusDraft ||
		current.RoomBindingStatus != contract.GatheringRoomBindingStatusPending ||
		current.ConversationID != "" {
		t.Fatalf("unexpected draft binding state: %+v", current)
	}
	if current.Version != 1 || len(current.Revisions) != 1 ||
		current.CurrentGatheringRevisionNumber != 1 ||
		current.CurrentGatheringRevisionID != current.Revisions[0].RevisionID ||
		current.Revisions[0].MaterialChange {
		t.Fatalf("initial revision invariant failed: %+v", current)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestScopeAPublishRequiresReadyRoomAndCompleteCommitments(t *testing.T) {
	current := scopeAMustDraft(t)
	if _, err := model.PublishGathering(
		current,
		"persona-owner",
		current.Version,
		scopeABaseTime.Add(time.Hour),
	); !errors.Is(err, gatheringerrors.ErrGatheringRoomProvisionPending) {
		t.Fatalf("publish without room error = %v", err)
	}

	ready, err := model.MarkGatheringRoomReady(
		current,
		"conversation-1",
		scopeABaseTime.Add(30*time.Minute),
	)
	if err != nil {
		t.Fatalf("mark room ready: %v", err)
	}
	published, err := model.PublishGathering(
		ready,
		"persona-owner",
		ready.Version,
		scopeABaseTime.Add(time.Hour),
	)
	if err != nil {
		t.Fatalf("publish complete draft: %v", err)
	}
	if published.LifecycleStatus != contract.GatheringLifecycleStatusPublished ||
		published.Version != ready.Version+1 {
		t.Fatalf("unexpected published aggregate: %+v", published)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-003
func TestScopeAUpdateAppendsOnlyMaterialRevision(t *testing.T) {
	current := scopeAMustDraft(t)
	input := model.AppendMaterialRevisionInput{
		ActorPersonaID:  "persona-owner",
		ExpectedVersion: current.Version,
		Purpose:         current.Purpose,
		Schedule:        current.Schedule,
		Place:           current.Place,
		PolicySet:       current.PolicySet,
		HostBinding:     current.HostBinding,
		OccurredAt:      scopeABaseTime.Add(time.Hour),
	}
	unchanged, _, appended, err := model.AppendMaterialGatheringRevision(current, input)
	if err != nil || appended || unchanged.Version != current.Version {
		t.Fatalf("identical update changed aggregate: appended=%v value=%+v err=%v", appended, unchanged, err)
	}

	input.Purpose.Title = "更新后的活动"
	changed, revision, appended, err := model.AppendMaterialGatheringRevision(current, input)
	if err != nil {
		t.Fatalf("append material revision: %v", err)
	}
	if !appended || !revision.MaterialChange ||
		changed.CurrentGatheringRevisionNumber != 2 ||
		len(changed.Revisions) != 2 ||
		changed.Version != current.Version+1 ||
		changed.Revisions[0].Digest == revision.Digest {
		t.Fatalf("material revision invariant failed: %+v", changed)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-002
func TestScopeACancelOnlyAllowsUpcomingTemporalPhase(t *testing.T) {
	current := scopeAMustDraft(t)
	cancelled, err := model.CancelGathering(
		current,
		"persona-owner",
		current.Version,
		"reason/change-of-plan",
		scopeABaseTime.Add(time.Hour),
	)
	if err != nil || cancelled.LifecycleStatus != contract.GatheringLifecycleStatusCancelled {
		t.Fatalf("cancel upcoming: value=%+v err=%v", cancelled, err)
	}

	if _, err := model.CancelGathering(
		current,
		"persona-owner",
		current.Version,
		"reason/too-late",
		current.Schedule.StartAt.Add(time.Minute),
	); !errors.Is(err, gatheringerrors.ErrGatheringCancellationWindowClosed) {
		t.Fatalf("cancel in progress error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-002
func TestScopeACompleteAndExplicitTerminalOperationsStayDistinct(t *testing.T) {
	current := scopeAMustPublished(t)
	outcome := contract.GatheringOutcome{
		Status:                   contract.GatheringOutcomeStatusOccurred,
		IndependentEvidenceCount: 2,
		EvidenceRefs: []contract.CanonicalObjectRef{{
			ObjectTypeRef: "GatheringAttendanceEvidence",
			ObjectID:      "evidence-1",
		}},
		CalculatedAt:      current.Schedule.EndAt,
		CalculationDigest: "outcome-digest",
	}
	if _, err := model.CompleteGathering(
		current,
		"persona-owner",
		current.Version,
		outcome,
		current.Schedule.EndAt.Add(-time.Minute),
	); !errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden) {
		t.Fatalf("complete before ended error = %v", err)
	}
	insufficient := outcome
	insufficient.IndependentEvidenceCount = 1
	if _, err := model.CompleteGathering(
		current,
		"persona-owner",
		current.Version,
		insufficient,
		current.Schedule.EndAt,
	); !errors.Is(err, gatheringerrors.ErrGatheringOutcomeUnverified) {
		t.Fatalf("complete without independent evidence error = %v", err)
	}
	// 催回顾链路的语义前提：host 完成行动不得关闭参与者 participation，
	// 否则催回顾通知回链详情后「发布回顾」入口（active 才可见）会消失。
	current.Participations = append(current.Participations, contract.GatheringParticipation{
		PersonaID: "persona-joiner",
		State:     contract.GatheringParticipationStateActive,
		Version:   1,
	})
	completed, err := model.CompleteGathering(
		current,
		"persona-owner",
		current.Version,
		outcome,
		current.Schedule.EndAt,
	)
	if err != nil || completed.Outcome.Status != contract.GatheringOutcomeStatusOccurred {
		t.Fatalf("complete ended: value=%+v err=%v", completed, err)
	}
	if len(completed.Participations) != 1 ||
		completed.Participations[0].PersonaID != "persona-joiner" ||
		completed.Participations[0].State != contract.GatheringParticipationStateActive {
		t.Fatalf(
			"complete must keep participant state untouched: %+v",
			completed.Participations,
		)
	}

	endedEarly, err := model.EndGatheringEarly(
		current,
		"persona-owner",
		current.Version,
		"reason/weather",
		nil,
		current.Schedule.StartAt.Add(time.Minute),
	)
	if err != nil || endedEarly.Outcome.Status != contract.GatheringOutcomeStatusEndedEarly {
		t.Fatalf("end early: value=%+v err=%v", endedEarly, err)
	}
	safetyTerminated, err := model.SafetyTerminateGathering(
		current,
		current.Version,
		"reason/safety",
		nil,
		current.Schedule.StartAt.Add(time.Minute),
	)
	if err != nil ||
		safetyTerminated.Outcome.Status != contract.GatheringOutcomeStatusSafetyTerminated {
		t.Fatalf("safety terminate: value=%+v err=%v", safetyTerminated, err)
	}
}

func scopeAMustDraft(t *testing.T) model.Gathering {
	t.Helper()
	current, err := model.CreateGatheringDraft(model.CreateGatheringDraftInput{
		ID:                 "gathering-scope-a",
		CreatedByPersonaID: "persona-owner",
		HostBinding: contract.HostBinding{
			HostSubjectKind:      contract.GatheringHostSubjectKindPersona,
			HostSubjectID:        "persona-owner",
			AuthorityEvidenceRef: "authority/owner",
			AuthorityVersion:     1,
			AuthorityExpiresAt:   scopeABaseTime.Add(24 * time.Hour),
		},
		Purpose: contract.GatheringPurpose{
			Title:      "周末徒步",
			Summary:    "一起完成近郊徒步",
			CostNotice: contract.GatheringCostNoticeFree,
		},
		Schedule: contract.GatheringSchedule{
			Timezone:          "Asia/Shanghai",
			StartAt:           scopeABaseTime.Add(3 * time.Hour),
			EndAt:             scopeABaseTime.Add(5 * time.Hour),
			AdmissionClosesAt: scopeABaseTime.Add(2 * time.Hour),
		},
		Place: contract.GatheringPlace{
			Mode:              contract.GatheringPlaceModePhysical,
			CoarsePlaceLabel:  "杭州",
			ExactMeetingPoint: "地铁站 A 口",
		},
		PolicySet: contract.GatheringPolicySet{
			AudiencePolicy:  contract.GatheringAudiencePolicyPublic,
			AdmissionPolicy: contract.GatheringAdmissionPolicyOpen,
			CapacityPolicy: contract.GatheringCapacityPolicy{
				MaxParticipants: 12,
			},
			DisclosurePolicy: contract.GatheringDisclosurePolicy{
				TimeDisclosure:   contract.GatheringTimeDisclosureExact,
				PlaceDisclosure:  contract.GatheringPlaceDisclosureExact,
				RosterDisclosure: contract.GatheringRosterDisclosureCountOnly,
			},
			RiskControlPolicyRef: "risk/default",
			PolicyDecisionRef:    "decision/allow",
			PolicyDigest:         "sha256:ca7acf0a841461bfd3e8d38fa0a80f7c7131dcc59c95d225f5c0987bfad35973",
			ObligationDigest:     "obligation-digest",
		},
		CreatedAt: scopeABaseTime,
	})
	if err != nil {
		t.Fatalf("create scope A draft: %v", err)
	}
	return current
}

func scopeAMustPublished(t *testing.T) model.Gathering {
	t.Helper()
	current := scopeAMustDraft(t)
	ready, err := model.MarkGatheringRoomReady(
		current,
		"conversation-scope-a",
		scopeABaseTime.Add(30*time.Minute),
	)
	if err != nil {
		t.Fatalf("mark room ready: %v", err)
	}
	published, err := model.PublishGathering(
		ready,
		"persona-owner",
		ready.Version,
		scopeABaseTime.Add(time.Hour),
	)
	if err != nil {
		t.Fatalf("publish scope A draft: %v", err)
	}
	return published
}
