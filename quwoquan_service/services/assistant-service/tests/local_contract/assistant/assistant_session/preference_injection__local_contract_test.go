// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-001
package local_contract

import (
	"context"
	prompting "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/prompting"
	"strings"
	"testing"

	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
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
	runtime := assistantruntest.NewMemoryRuntime()
	commands := runruntime.NewCommandService(
		runtime,
		runruntime.SessionAuthorizerFunc(func(context.Context, string, string) error { return nil }),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		nil,
		nil,
		testRunPolicyResolver(),
	)
	useCases := runapplication.NewUseCases(
		commands,
		runapplication.WithPreferenceSnapshots(preferences),
	)
	const sessionA = "session-preference-a"
	const sessionB = "session-preference-b"
	preferences.sessionBySession[sessionA] = []preferencemodel.Snapshot{
		{
			PreferenceID: "apf_session_a",
			Scope:        preferencemodel.ScopeSession,
			Kind:         preferencemodel.KindReplyLength,
			Value:        "concise",
			Version:      2,
		},
	}
	const question = "请解释今天的安排"
	runA, err := useCases.Start(
		t.Context(),
		"persona-owner",
		sessionA,
		"trace-preference-a",
		runapplication.StartInput{
			ClientRequestID: "create-preference-run-a",
			Intent: rundomain.Intent{
				Kind:   "answer",
				Answer: &rundomain.AnswerIntent{Text: question},
			},
			TrustedPersonaID: "persona-owner",
		},
	)
	if err != nil {
		t.Fatalf("Start(A) error = %v", err)
	}
	if runA.InputText != question {
		t.Fatalf("run A question mutated: %q", runA.InputText)
	}
	if len(runA.SessionPreferenceFacts) != 1 ||
		runA.SessionPreferenceFacts[0].Value != "concise" {
		t.Fatalf("run A session preferences = %#v", runA.SessionPreferenceFacts)
	}
	if len(runA.LongTermPreferenceFacts) != 1 ||
		runA.LongTermPreferenceFacts[0].Value != "warm" {
		t.Fatalf("run A long-term preferences = %#v", runA.LongTermPreferenceFacts)
	}
	runB, err := useCases.Start(
		t.Context(),
		"persona-owner",
		sessionB,
		"trace-preference-b",
		runapplication.StartInput{
			ClientRequestID: "create-preference-run-b",
			Intent: rundomain.Intent{
				Kind:   "answer",
				Answer: &rundomain.AnswerIntent{Text: question},
			},
			TrustedPersonaID: "persona-owner",
		},
	)
	if err != nil {
		t.Fatalf("Start(B) error = %v", err)
	}
	if runB.InputText != question {
		t.Fatalf("run B question mutated: %q", runB.InputText)
	}
	if len(runB.SessionPreferenceFacts) != 0 {
		t.Fatalf(
			"session B inherited session A session preference: %#v",
			runB.SessionPreferenceFacts,
		)
	}
	if len(runB.LongTermPreferenceFacts) != 1 ||
		runB.LongTermPreferenceFacts[0].Value != "warm" {
		t.Fatalf("run B long-term preferences = %#v", runB.LongTermPreferenceFacts)
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
