package model_test

import (
	"errors"
	"testing"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
func TestScopeARoomEnsureRetriesFailedAndReadyIsIdempotent(t *testing.T) {
	current := scopeAMustDraft(t)
	failed, err := model.MarkGatheringRoomFailed(
		current,
		scopeABaseTime.Add(time.Minute),
	)
	if err != nil {
		t.Fatalf("mark room failed: %v", err)
	}
	replayedFailure, err := model.MarkGatheringRoomFailed(
		failed,
		scopeABaseTime.Add(2*time.Minute),
	)
	if err != nil || replayedFailure.Version != failed.Version {
		t.Fatalf("failed replay mutated aggregate: value=%+v err=%v", replayedFailure, err)
	}

	ready, err := model.MarkGatheringRoomReady(
		failed,
		"conversation-retried",
		scopeABaseTime.Add(3*time.Minute),
	)
	if err != nil {
		t.Fatalf("retry room ensure to ready: %v", err)
	}
	replayedReady, err := model.MarkGatheringRoomReady(
		ready,
		"conversation-retried",
		scopeABaseTime.Add(4*time.Minute),
	)
	if err != nil || replayedReady.Version != ready.Version {
		t.Fatalf("ready replay mutated aggregate: value=%+v err=%v", replayedReady, err)
	}
	if ready.RoomBindingStatus != contract.GatheringRoomBindingStatusReady ||
		ready.ConversationID != "conversation-retried" {
		t.Fatalf("unexpected ready binding: %+v", ready)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
func TestScopeARoomBindingNeverRebindsOrDowngradesReady(t *testing.T) {
	current := scopeAMustDraft(t)
	ready, err := model.MarkGatheringRoomReady(
		current,
		"conversation-canonical",
		scopeABaseTime.Add(time.Minute),
	)
	if err != nil {
		t.Fatalf("mark room ready: %v", err)
	}
	if _, err := model.MarkGatheringRoomReady(
		ready,
		"conversation-other",
		scopeABaseTime.Add(2*time.Minute),
	); !errors.Is(err, gatheringerrors.ErrGatheringRoomProvisionFailed) {
		t.Fatalf("rebind error = %v", err)
	}
	afterFailure, err := model.MarkGatheringRoomFailed(
		ready,
		scopeABaseTime.Add(3*time.Minute),
	)
	if err != nil || afterFailure.Version != ready.Version ||
		afterFailure.RoomBindingStatus != contract.GatheringRoomBindingStatusReady {
		t.Fatalf("ready binding downgraded: value=%+v err=%v", afterFailure, err)
	}
}
