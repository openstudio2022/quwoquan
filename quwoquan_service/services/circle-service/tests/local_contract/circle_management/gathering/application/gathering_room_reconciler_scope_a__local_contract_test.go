package application_test

import (
	"context"
	"errors"
	"testing"
	"time"

	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
func TestScopeAReconcilerPersistsFailureAndReliablyRetriesRoomEnsure(t *testing.T) {
	store := newScopeACommitStore()
	draft := scopeAMustCreateModelDraft(t, time.Now().UTC())
	store.values[draft.ID] = draft
	candidates := &scopeAReconciliationStore{
		aggregate:   store,
		checkpoints: make(map[string]int64),
	}
	conversations := &scopeAConversationPort{
		ensureResults: []scopeAEnsureResult{
			{err: errors.New("Chat temporarily unavailable")},
			{conversationID: "conversation-retried"},
		},
	}
	reconciler := app.NewReconciler(store, candidates, conversations)

	if _, err := reconciler.ReconcileOnce(context.Background(), 10); err == nil {
		t.Fatal("first room ensure unexpectedly succeeded")
	}
	failed, _, _ := store.Load(context.Background(), draft.ID)
	if failed.RoomBindingStatus != contract.GatheringRoomBindingStatusFailed ||
		failed.Version != draft.Version+1 ||
		candidates.checkpoints[draft.ID] != 0 ||
		store.outboxCount() != 1 {
		t.Fatalf("failed ensure was not retryable: %+v checkpoints=%+v", failed, candidates.checkpoints)
	}

	if _, err := reconciler.ReconcileOnce(context.Background(), 10); err != nil {
		t.Fatalf("retry room ensure: %v", err)
	}
	ready, _, _ := store.Load(context.Background(), draft.ID)
	if ready.RoomBindingStatus != contract.GatheringRoomBindingStatusReady ||
		ready.ConversationID != "conversation-retried" ||
		candidates.checkpoints[draft.ID] != ready.Version ||
		conversations.ensureCalls != 2 ||
		store.outboxCount() != 2 {
		t.Fatalf(
			"ready retry invariant failed: value=%+v checkpoints=%+v ensure=%d",
			ready,
			candidates.checkpoints,
			conversations.ensureCalls,
		)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-002
func TestScopeAReconcilerNeverInfersOccurredOrCompletesLifecycle(t *testing.T) {
	store := newScopeACommitStore()
	current := scopeAMustCreateModelDraft(t, time.Now().UTC().Add(-8*time.Hour))
	current.LifecycleStatus = contract.GatheringLifecycleStatusPublished
	current.RoomBindingStatus = contract.GatheringRoomBindingStatusReady
	current.ConversationID = "conversation-existing"
	current.Schedule.StartAt = time.Now().UTC().Add(-4 * time.Hour)
	current.Schedule.EndAt = time.Now().UTC().Add(-2 * time.Hour)
	store.values[current.ID] = current
	candidates := &scopeAReconciliationStore{
		aggregate:   store,
		checkpoints: make(map[string]int64),
	}
	conversations := &scopeAConversationPort{
		ensureResults: []scopeAEnsureResult{{conversationID: "conversation-existing"}},
	}
	reconciler := app.NewReconciler(store, candidates, conversations)

	if _, err := reconciler.ReconcileOnce(context.Background(), 10); err != nil {
		t.Fatalf("reconcile ended Gathering: %v", err)
	}
	unchanged, _, _ := store.Load(context.Background(), current.ID)
	if unchanged.LifecycleStatus != contract.GatheringLifecycleStatusPublished ||
		unchanged.Outcome.Status != "" ||
		unchanged.Version != current.Version ||
		conversations.ensureCalls != 1 {
		t.Fatalf("reconciler inferred lifecycle outcome: %+v", unchanged)
	}
}

type scopeAReconciliationStore struct {
	aggregate   *scopeACommitStore
	checkpoints map[string]int64
}

func (store *scopeAReconciliationStore) ListReconciliationCandidates(
	_ context.Context,
	limit int,
) ([]model.Gathering, error) {
	store.aggregate.mu.Lock()
	defer store.aggregate.mu.Unlock()
	result := make([]model.Gathering, 0, limit)
	for _, value := range store.aggregate.values {
		if value.Version <= store.checkpoints[value.ID] {
			continue
		}
		result = append(result, value)
		if len(result) == limit {
			break
		}
	}
	return result, nil
}

func (store *scopeAReconciliationStore) SaveReconciliationCheckpoint(
	_ context.Context,
	gatheringID string,
	version int64,
	_ time.Time,
) error {
	if version > store.checkpoints[gatheringID] {
		store.checkpoints[gatheringID] = version
	}
	return nil
}

type scopeAEnsureResult struct {
	conversationID string
	err            error
}

type scopeAConversationPort struct {
	ensureResults []scopeAEnsureResult
	ensureCalls   int
	projectCalls  int
}

func (port *scopeAConversationPort) EnsureGatheringConversation(
	_ context.Context,
	_ ports.EnsureGatheringConversationCommand,
) (string, error) {
	port.ensureCalls++
	if len(port.ensureResults) == 0 {
		return "", errors.New("unexpected EnsureGatheringConversation call")
	}
	result := port.ensureResults[0]
	port.ensureResults = port.ensureResults[1:]
	return result.conversationID, result.err
}

func (port *scopeAConversationPort) ProjectGatheringMembership(
	_ context.Context,
	command ports.ProjectGatheringMembershipCommand,
) error {
	port.projectCalls++
	if command.SourceType == "participation" {
		return errors.New("Scope A fixture has no participation projection")
	}
	return nil
}

func scopeAMustCreateModelDraft(t *testing.T, createdAt time.Time) model.Gathering {
	t.Helper()
	command := scopeACreateCommand(createdAt)
	value, err := model.CreateGatheringDraft(model.CreateGatheringDraftInput{
		ID:                 "gathering-reconciler",
		CreatedByPersonaID: "persona-owner",
		HostBinding:        command.HostBinding,
		Purpose:            command.Purpose,
		Schedule:           command.Schedule,
		Place:              command.Place,
		PolicySet:          command.PolicySet,
		CreatedAt:          createdAt,
	})
	if err != nil {
		t.Fatalf("create reconciler draft: %v", err)
	}
	return value
}

var _ ports.ReconciliationStore = (*scopeAReconciliationStore)(nil)
var _ ports.ConversationPort = (*scopeAConversationPort)(nil)
