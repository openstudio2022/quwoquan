// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md
package local_contract

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
)

type countingFrozenPolicyResolver struct {
	calls int
	err   error
}

func (resolver *countingFrozenPolicyResolver) ResolveFrozenPolicy(
	_ context.Context,
	policyID string,
	_ string,
	skillID string,
	domainID string,
) (assistant.AssistantFrozenPolicySelection, error) {
	resolver.calls++
	if resolver.err != nil {
		return assistant.AssistantFrozenPolicySelection{}, resolver.err
	}
	selection := testFrozenPolicySelection(policyID, skillID, domainID)
	selection.ReleaseVersion = fmt.Sprintf("release-call-%d", resolver.calls)
	return selection, nil
}

func TestStartRunFreezesPolicyBeforeInsertAndReplayNeverRebuckets(t *testing.T) {
	t.Parallel()
	store := persistence.NewMemoryConversationRunStore()
	resolver := &countingFrozenPolicyResolver{}
	service := application.NewAssistantService(
		nil,
		nil,
		application.WithConversationRunStore(store),
		application.WithFrozenPolicyResolver(resolver),
		application.WithAgentLoop(application.NewAgentLoop(
			nil,
			application.ReactRuntime{
				Model: application.DeterministicModelProvider{},
			},
			nil,
		)),
	)
	conversation, err := service.CreateConversation(
		t.Context(),
		"account-1",
		assistant.CreateConversationInput{ClientRequestID: "conversation-1"},
	)
	if err != nil {
		t.Fatal(err)
	}
	input := assistant.CreateTurnInput{
		SkillID:         "general_qa",
		DomainID:        "assistant",
		Input:           assistant.AssistantTurnInput{Text: "测试冻结策略"},
		ClientRequestID: "run-1",
		RequestContext:  testRunRequestContext("persona-1"),
	}
	first, err := service.CreateTurn(
		t.Context(),
		"account-1",
		conversation.ConversationID,
		input,
	)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.CreateTurn(
		t.Context(),
		"account-1",
		conversation.ConversationID,
		input,
	)
	if err != nil {
		t.Fatal(err)
	}
	if resolver.calls != 1 ||
		first.TurnID != replay.TurnID ||
		first.FrozenPolicySelection.ReleaseVersion != "release-call-1" ||
		replay.FrozenPolicySelection.ReleaseVersion != "release-call-1" {
		t.Fatalf("calls=%d first=%+v replay=%+v", resolver.calls, first, replay)
	}

	if _, err := service.ExecuteTurn(t.Context(), "account-1", first.TurnID); err != nil {
		t.Fatal(err)
	}
	completed, err := service.GetTurn(t.Context(), "account-1", first.TurnID)
	if err != nil {
		t.Fatal(err)
	}
	if completed.TerminalSnapshot == nil ||
		completed.TerminalSnapshot.SelectedPolicyRef == nil ||
		completed.TerminalSnapshot.SelectedPolicyRef.Version != "release-call-1" {
		t.Fatalf("terminal policy ref=%+v", completed.TerminalSnapshot)
	}
}

func TestPolicyResolverFailureDoesNotWriteRun(t *testing.T) {
	t.Parallel()
	store := persistence.NewMemoryConversationRunStore()
	service := application.NewAssistantService(
		nil,
		nil,
		application.WithConversationRunStore(store),
		application.WithFrozenPolicyResolver(&countingFrozenPolicyResolver{
			err: errors.New("rollout storage unavailable"),
		}),
	)
	conversation, err := service.CreateConversation(
		t.Context(),
		"account-2",
		assistant.CreateConversationInput{ClientRequestID: "conversation-2"},
	)
	if err != nil {
		t.Fatal(err)
	}
	_, err = service.CreateTurn(
		t.Context(),
		"account-2",
		conversation.ConversationID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: "must fail"},
			ClientRequestID: "run-failed-policy",
			RequestContext:  testRunRequestContext("persona-2"),
		},
	)
	if err == nil {
		t.Fatal("policy resolver failure must reject StartRun")
	}
	if _, found, readErr := store.GetTurnByClientRequest(
		t.Context(),
		"account-2",
		conversation.ConversationID,
		"run-failed-policy",
	); readErr != nil || found {
		t.Fatalf("failed policy selection persisted run: found=%v err=%v", found, readErr)
	}
}
