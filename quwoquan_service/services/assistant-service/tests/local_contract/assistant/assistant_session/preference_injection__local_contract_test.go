// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-001
package local_contract

import (
	"context"
	prompting "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/prompting"
	"strings"
	"testing"

	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
)

type assistantSessionPreferenceInjectionPreferenceSnapshotReader struct {
	sessionBySession map[string][]preferencemodel.Snapshot
	longTerm         []preferencemodel.Snapshot
}

func (r *assistantSessionPreferenceInjectionPreferenceSnapshotReader) ResolveActiveSnapshots(
	_ context.Context,
	_ string,
	sessionID string,
) ([]preferencemodel.Snapshot, []preferencemodel.Snapshot, error) {
	return r.sessionBySession[sessionID], r.longTerm, nil
}

func TestCreateTurnSnapshotsPreferencesWithoutMutatingQuestion(t *testing.T) {
	store := persistence.NewMemorySessionRunStore()
	preferences := &assistantSessionPreferenceInjectionPreferenceSnapshotReader{
		sessionBySession: map[string][]preferencemodel.Snapshot{},
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
	service := orchestration.NewAssistantService(
		nil,
		nil,
		orchestration.WithSessionRunStore(store),
		orchestration.WithPreferenceSnapshotReader(preferences),
		testFrozenPolicyOption(),
	)
	sessionA, err := service.CreateSession(
		t.Context(),
		"persona-owner",
		assistant.CreateSessionInput{ClientRequestID: "create-preference-session-a"},
	)
	if err != nil {
		t.Fatalf("CreateSession(A) error = %v", err)
	}
	sessionB, err := service.CreateSession(
		t.Context(),
		"persona-owner",
		assistant.CreateSessionInput{ClientRequestID: "create-preference-session-b"},
	)
	if err != nil {
		t.Fatalf("CreateSession(B) error = %v", err)
	}
	preferences.sessionBySession[sessionA.SessionID] = []preferencemodel.Snapshot{
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
		sessionA.SessionID,
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
		sessionB.SessionID,
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
			"session B inherited session A session preference: %#v",
			turnB.SessionPreferenceFacts,
		)
	}
	if len(turnB.LongTermPreferenceFacts) != 1 ||
		turnB.LongTermPreferenceFacts[0].Value != "warm" {
		t.Fatalf("turn B long-term preferences = %#v", turnB.LongTermPreferenceFacts)
	}
}

func TestFormatModelPreferencesSessionOverridesLongTerm(t *testing.T) {
	prompt := prompting.FormatModelPreferencesForPrompt(
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

type assistantSessionPreferenceInjectionCapturingModelProvider struct {
	request ports.ModelCompletionRequest
}

func (p *assistantSessionPreferenceInjectionCapturingModelProvider) Complete(
	_ context.Context,
	request ports.ModelCompletionRequest,
) (ports.ModelCompletionResult, error) {
	p.request = request
	return ports.ModelCompletionResult{Content: "已完成"}, nil
}

func (p *assistantSessionPreferenceInjectionCapturingModelProvider) Stream(
	ctx context.Context,
	request ports.ModelCompletionRequest,
	emit func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
	result, err := p.Complete(ctx, request)
	if err != nil {
		return ports.ModelCompletionResult{}, err
	}
	if err := emit(ports.ModelTextDelta{Text: result.Content}); err != nil {
		return ports.ModelCompletionResult{}, err
	}
	return result, nil
}

func TestProviderBackedModelRequestSeparatesPreferencesFromOriginalQuestion(t *testing.T) {
	backend := &assistantSessionPreferenceInjectionCapturingModelProvider{}
	_, err := (orchestration.ProviderBackedModelProvider{Backend: backend}).Complete(
		t.Context(),
		orchestration.ModelRequest{
			Stage:           string(ports.ModelStageFinal),
			Prompt:          "请输出最终回答。",
			UserQuestion:    "请按我的问题回答，不要改写。",
			ProblemClass:    "general",
			SearchIntensity: "medium",
			Observation:     map[string]any{},
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
