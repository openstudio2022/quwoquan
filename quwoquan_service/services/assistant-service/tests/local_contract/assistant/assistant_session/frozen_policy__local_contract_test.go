// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md
package local_contract

import (
	"context"
	"errors"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	modeldouble "quwoquan_service/services/assistant-service/tests/support/modeldouble"
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
	selection.ReleaseDigest = testPolicyReleaseDigest
	return selection, nil
}

func TestStartRunFreezesPolicyBeforeInsertAndReplayNeverRebuckets(t *testing.T) {
	t.Parallel()
	store := persistence.NewMemorySessionRunStore()
	resolver := &countingFrozenPolicyResolver{}
	service := orchestration.NewAssistantService(
		nil,
		nil,
		orchestration.WithSessionRunStore(store),
		orchestration.WithFrozenPolicyResolver(resolver),
		orchestration.WithAgentLoop(orchestration.NewAgentLoop(
			nil,
			orchestration.ReactRuntime{
				Model: modeldouble.DeterministicModelProvider{},
			},
			nil,
		)),
	)
	session, err := service.CreateSession(
		t.Context(),
		"account-1",
		assistant.CreateSessionInput{ClientRequestID: "session-1"},
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
		session.SessionID,
		input,
	)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.CreateTurn(
		t.Context(),
		"account-1",
		session.SessionID,
		input,
	)
	if err != nil {
		t.Fatal(err)
	}
	if resolver.calls != 1 ||
		first.TurnID != replay.TurnID ||
		first.FrozenPolicySelection.ReleaseDigest != testPolicyReleaseDigest ||
		replay.FrozenPolicySelection.ReleaseDigest != testPolicyReleaseDigest {
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
		completed.TerminalSnapshot.SelectedPolicyRef.ReleaseDigest != testPolicyReleaseDigest {
		t.Fatalf("terminal policy ref=%+v", completed.TerminalSnapshot)
	}
}

func TestPolicyResolverFailureDoesNotWriteRun(t *testing.T) {
	t.Parallel()
	store := persistence.NewMemorySessionRunStore()
	service := orchestration.NewAssistantService(
		nil,
		nil,
		orchestration.WithSessionRunStore(store),
		orchestration.WithFrozenPolicyResolver(&countingFrozenPolicyResolver{
			err: errors.New("rollout storage unavailable"),
		}),
	)
	session, err := service.CreateSession(
		t.Context(),
		"account-2",
		assistant.CreateSessionInput{ClientRequestID: "session-2"},
	)
	if err != nil {
		t.Fatal(err)
	}
	_, err = service.CreateTurn(
		t.Context(),
		"account-2",
		session.SessionID,
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
		session.SessionID,
		"run-failed-policy",
	); readErr != nil || found {
		t.Fatalf("failed policy selection persisted run: found=%v err=%v", found, readErr)
	}
}
