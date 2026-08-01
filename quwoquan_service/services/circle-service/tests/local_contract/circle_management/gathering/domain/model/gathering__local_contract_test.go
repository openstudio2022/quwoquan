package model_test

import (
	"errors"
	"testing"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

var baseTime = time.Date(2026, 8, 1, 8, 0, 0, 0, time.UTC)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestGatheringUsesOneAggregateForOpenAndClosedTimeRanges(t *testing.T) {
	point := mustCreate(t, model.JoinPolicyOpen, 3, time.Time{})
	rangeGathering, err := model.Create(createInput(model.JoinPolicyOpen, 3, baseTime.Add(3*time.Hour)))
	if err != nil {
		t.Fatalf("Create range Gathering: %v", err)
	}
	if !point.EndAt.IsZero() || rangeGathering.EndAt.IsZero() || point.Status != model.StatusDraft || rangeGathering.Status != model.StatusDraft {
		t.Fatalf("unexpected time representations: point=%+v range=%+v", point, rangeGathering)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-002
func TestGatheringExpiresAndRejectsSubsequentJoin(t *testing.T) {
	current := mustBound(t, mustCreate(t, model.JoinPolicyOpen, 3, time.Time{}))
	expired := model.Reevaluate(current, current.StartAt)
	if expired.Status != model.StatusCompleted {
		t.Fatalf("status = %q, want completed", expired.Status)
	}
	if _, err := model.Join(expired, "persona-2", current.StartAt.Add(time.Minute)); !errors.Is(err, gatheringerrors.ErrGatheringNotOpen) {
		t.Fatalf("Join expired error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestGatheringCapacityAndDuplicateJoinAreAtomicAggregateRules(t *testing.T) {
	current := mustBound(t, mustCreate(t, model.JoinPolicyOpen, 2, time.Time{}))
	joined, err := model.Join(current, "persona-2", baseTime.Add(3*time.Minute))
	if err != nil {
		t.Fatalf("Join: %v", err)
	}
	if joined.Status != model.StatusFull || model.JoinedCount(joined) != 2 {
		t.Fatalf("full projection = status %q count %d", joined.Status, model.JoinedCount(joined))
	}
	replay, err := model.Join(joined, "persona-2", baseTime.Add(4*time.Minute))
	if err != nil || replay.Version != joined.Version || len(replay.Participants) != 2 {
		t.Fatalf("duplicate join must be stable: replay=%+v err=%v", replay, err)
	}
	if _, err := model.Join(joined, "persona-3", baseTime.Add(4*time.Minute)); !errors.Is(err, gatheringerrors.ErrGatheringFull) {
		t.Fatalf("over-capacity error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-002
func TestGatheringApprovalRejectCancelAndReapplyRemainDistinct(t *testing.T) {
	current := mustBound(t, mustCreate(t, model.JoinPolicyApproval, 3, time.Time{}))
	pending, err := model.Join(current, "persona-2", baseTime.Add(3*time.Minute))
	if err != nil || pending.Participants[1].State != model.ParticipantStatePending {
		t.Fatalf("pending Join = %+v err=%v", pending.Participants, err)
	}
	rejected, err := model.Reject(pending, "persona-owner", "persona-2", baseTime.Add(4*time.Minute))
	if err != nil || rejected.Participants[1].State != model.ParticipantStateRejected {
		t.Fatalf("Reject = %+v err=%v", rejected.Participants, err)
	}
	reapplied, err := model.Join(rejected, "persona-2", baseTime.Add(5*time.Minute))
	if err != nil || len(reapplied.Participants) != 2 || reapplied.Participants[1].State != model.ParticipantStatePending {
		t.Fatalf("reapply must reuse roster row: %+v err=%v", reapplied.Participants, err)
	}
	cancelled, err := model.Cancel(reapplied, "persona-owner", baseTime.Add(6*time.Minute))
	if err != nil || cancelled.Status != model.StatusCancelled {
		t.Fatalf("Cancel = %q err=%v", cancelled.Status, err)
	}
	if _, err := model.Join(cancelled, "persona-3", baseTime.Add(7*time.Minute)); !errors.Is(err, gatheringerrors.ErrGatheringNotOpen) {
		t.Fatalf("Join cancelled error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-002
func TestGatheringBindingFailureNeverOpensAndRetryIsIdempotent(t *testing.T) {
	current := mustCreate(t, model.JoinPolicyOpen, 3, time.Time{})
	failed, err := model.MarkConversationBindingFailed(current, baseTime.Add(time.Minute))
	if err != nil || failed.Status != model.StatusDraft {
		t.Fatalf("MarkConversationBindingFailed = status %q err=%v", failed.Status, err)
	}
	if _, err := model.Join(failed, "persona-2", baseTime.Add(2*time.Minute)); !errors.Is(err, gatheringerrors.ErrGatheringNotOpen) {
		t.Fatalf("Join unbound error = %v", err)
	}
	bound, err := model.BindConversation(failed, "conversation-1", baseTime.Add(3*time.Minute))
	if err != nil || bound.Status != model.StatusOpen {
		t.Fatalf("BindConversation = %+v err=%v", bound, err)
	}
	replay, err := model.BindConversation(bound, "conversation-1", baseTime.Add(4*time.Minute))
	if err != nil || replay.Version != bound.Version {
		t.Fatalf("binding replay = version %d err=%v", replay.Version, err)
	}
	if _, err := model.BindConversation(bound, "conversation-2", baseTime.Add(4*time.Minute)); !errors.Is(err, gatheringerrors.ErrGatheringConversationBindingFailed) {
		t.Fatalf("second conversation error = %v", err)
	}
}

func createInput(policy model.JoinPolicy, capacity int64, endAt time.Time) model.CreateInput {
	return model.CreateInput{
		ID:               "gathering-1",
		CreatorPersonaID: "persona-owner",
		Title:            "贡嘎日落同行",
		TargetRef: model.TargetRef{
			ObjectTypeRef: "photo_spot",
			ObjectID:      "photo-spot-gongga",
			RouteID:       "gatheringDetail",
		},
		StartAt:    baseTime.Add(2 * time.Hour),
		EndAt:      endAt,
		Capacity:   capacity,
		JoinPolicy: policy,
		OccurredAt: baseTime,
	}
}

func mustCreate(t *testing.T, policy model.JoinPolicy, capacity int64, endAt time.Time) model.Gathering {
	t.Helper()
	result, err := model.Create(createInput(policy, capacity, endAt))
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	return result
}

func mustBound(t *testing.T, current model.Gathering) model.Gathering {
	t.Helper()
	result, err := model.BindConversation(current, "conversation-1", baseTime.Add(time.Minute))
	if err != nil {
		t.Fatalf("BindConversation: %v", err)
	}
	return result
}
