// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-001
package local_contract

import (
	"context"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/domain/model"
)

type migratedPreferenceInjectionPreferenceSnapshotReader struct {
	sessionByConversation map[string][]preferencemodel.Snapshot
	longTerm              []preferencemodel.Snapshot
}

func (r *migratedPreferenceInjectionPreferenceSnapshotReader) ResolveActiveSnapshots(
	_ context.Context,
	_ string,
	conversationID string,
) ([]preferencemodel.Snapshot, []preferencemodel.Snapshot, error) {
	return r.sessionByConversation[conversationID], r.longTerm, nil
}

func TestCreateTurnSnapshotsPreferencesWithoutMutatingQuestion(t *testing.T) {
	store := persistence.NewMemoryConversationRunStore()
	preferences := &migratedPreferenceInjectionPreferenceSnapshotReader{
		sessionByConversation: map[string][]preferencemodel.Snapshot{},
		longTerm: []preferencemodel.Snapshot{
			{
				PreferenceID: "apf_long_term",
				Scope:        preferencemodel.ScopeLongTerm,
				Kind:         preferencemodel.KindTone,
				Value:        "warm",
				Version:      1,
			},
		},
	}
	service := application.NewAssistantService(
		nil,
		nil,
		application.WithConversationRunStore(store),
		application.WithPreferenceSnapshotReader(preferences),
		testFrozenPolicyOption(),
	)
	conversationA, err := service.CreateConversation(
		t.Context(),
		"persona-owner",
		assistant.CreateConversationInput{ClientRequestID: "create-preference-conversation-a"},
	)
	if err != nil {
		t.Fatalf("CreateConversation(A) error = %v", err)
	}
	conversationB, err := service.CreateConversation(
		t.Context(),
		"persona-owner",
		assistant.CreateConversationInput{ClientRequestID: "create-preference-conversation-b"},
	)
	if err != nil {
		t.Fatalf("CreateConversation(B) error = %v", err)
	}
	preferences.sessionByConversation[conversationA.ConversationID] = []preferencemodel.Snapshot{
		{
			PreferenceID: "apf_session_a",
			Scope:        preferencemodel.ScopeSession,
			Kind:         preferencemodel.KindReplyLength,
			Value:        "concise",
			Version:      2,
		},
	}
	const question = "请解释今天的安排"
	turnA, err := service.CreateTurn(
		t.Context(),
		"persona-owner",
		conversationA.ConversationID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: question},
			ClientRequestID: "create-preference-turn-a",
			RequestContext:  testRunRequestContext("persona-owner"),
		},
	)
	if err != nil {
		t.Fatalf("CreateTurn(A) error = %v", err)
	}
	if turnA.Input.Text != question {
		t.Fatalf("turn A question mutated: %q", turnA.Input.Text)
	}
	if len(turnA.SessionPreferenceFacts) != 1 ||
		turnA.SessionPreferenceFacts[0].Value != "concise" {
		t.Fatalf("turn A session preferences = %#v", turnA.SessionPreferenceFacts)
	}
	if len(turnA.LongTermPreferenceFacts) != 1 ||
		turnA.LongTermPreferenceFacts[0].Value != "warm" {
		t.Fatalf("turn A long-term preferences = %#v", turnA.LongTermPreferenceFacts)
	}
	turnB, err := service.CreateTurn(
		t.Context(),
		"persona-owner",
		conversationB.ConversationID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: question},
			ClientRequestID: "create-preference-turn-b",
			RequestContext:  testRunRequestContext("persona-owner"),
		},
	)
	if err != nil {
		t.Fatalf("CreateTurn(B) error = %v", err)
	}
	if turnB.Input.Text != question {
		t.Fatalf("turn B question mutated: %q", turnB.Input.Text)
	}
	if len(turnB.SessionPreferenceFacts) != 0 {
		t.Fatalf(
			"conversation B inherited conversation A session preference: %#v",
			turnB.SessionPreferenceFacts,
		)
	}
	if len(turnB.LongTermPreferenceFacts) != 1 ||
		turnB.LongTermPreferenceFacts[0].Value != "warm" {
		t.Fatalf("turn B long-term preferences = %#v", turnB.LongTermPreferenceFacts)
	}
}

func TestFormatModelPreferencesSessionOverridesLongTerm(t *testing.T) {
	prompt := application.FormatModelPreferencesForPrompt(
		[]preferencemodel.Snapshot{
			{
				Scope: preferencemodel.ScopeSession,
				Kind:  preferencemodel.KindReplyLength,
				Value: "concise",
			},
		},
		[]preferencemodel.Snapshot{
			{
				Scope: preferencemodel.ScopeLongTerm,
				Kind:  preferencemodel.KindReplyLength,
				Value: "detailed",
			},
			{
				Scope: preferencemodel.ScopeLongTerm,
				Kind:  preferencemodel.KindTone,
				Value: "professional",
			},
		},
	)
	if !strings.Contains(prompt, "回答保持简洁") {
		t.Fatalf("prompt missing session preference: %q", prompt)
	}
	if strings.Contains(prompt, "充分细节") {
		t.Fatalf("long-term preference must not override session: %q", prompt)
	}
	if !strings.Contains(prompt, "语气专业准确") {
		t.Fatalf("prompt missing long-term preference: %q", prompt)
	}
}

type migratedPreferenceInjectionCapturingModelProvider struct {
	request application.ModelCompletionRequest
}

func (p *migratedPreferenceInjectionCapturingModelProvider) Complete(
	_ context.Context,
	request application.ModelCompletionRequest,
) (application.ModelCompletionResult, error) {
	p.request = request
	return application.ModelCompletionResult{Content: "已完成"}, nil
}

func (p *migratedPreferenceInjectionCapturingModelProvider) Stream(
	ctx context.Context,
	request application.ModelCompletionRequest,
	emit func(application.ModelTextDelta) error,
) (application.ModelCompletionResult, error) {
	result, err := p.Complete(ctx, request)
	if err != nil {
		return application.ModelCompletionResult{}, err
	}
	if err := emit(application.ModelTextDelta{Text: result.Content}); err != nil {
		return application.ModelCompletionResult{}, err
	}
	return result, nil
}

func TestProviderBackedModelRequestSeparatesPreferencesFromOriginalQuestion(t *testing.T) {
	backend := &migratedPreferenceInjectionCapturingModelProvider{}
	_, err := (application.ProviderBackedModelProvider{Backend: backend}).Complete(
		t.Context(),
		application.ModelRequest{
			Stage:        string(application.ModelStageFinal),
			Prompt:       "请输出最终回答。",
			UserQuestion: "请按我的问题回答，不要改写。",
			Observation:  map[string]any{},
			SessionPreferenceFacts: []preferencemodel.Snapshot{
				{
					Scope: preferencemodel.ScopeSession,
					Kind:  preferencemodel.KindReplyLength,
					Value: "concise",
				},
			},
		},
	)
	if err != nil {
		t.Fatalf("Complete() error = %v", err)
	}
	if len(backend.request.Messages) != 2 {
		t.Fatalf("outbound messages = %#v", backend.request.Messages)
	}
	prompt := backend.request.Messages[1].Content
	if !strings.Contains(prompt, "回答保持简洁") {
		t.Fatalf("outbound request missing preference instruction: %q", prompt)
	}
	if !strings.Contains(
		prompt,
		"用户问题：请按我的问题回答，不要改写。\n工具观察：{}",
	) {
		t.Fatalf("outbound request rewrote original question: %q", prompt)
	}
}
