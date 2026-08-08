// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"strings"
	"testing"
	"time"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/contextassembly"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

const (
	contextPrivacyPrivateMemory = "privacy-fixture-peanut-allergy"
	contextPrivacyOwnerFact     = "conversation-owner-backed-fact"
)

type contextPrivacyPreferenceReader struct {
	calls int
}

func (reader *contextPrivacyPreferenceReader) ResolveActiveSnapshots(
	context.Context,
	string,
	string,
) ([]preferencemodel.AssistantPreferenceSnapshot, []preferencemodel.AssistantPreferenceSnapshot, error) {
	reader.calls++
	return []preferencemodel.AssistantPreferenceSnapshot{{
			PreferenceID: "session-private",
			Scope:        preferencemodel.ScopeSession,
			Kind:         preferencemodel.KindReplyLength,
			Value:        "concise",
		}}, []preferencemodel.AssistantPreferenceSnapshot{{
			PreferenceID: "memory-private",
			Scope:        preferencemodel.ScopeLongTerm,
			Kind:         preferencemodel.KindDietaryRestrictions,
			Value:        contextPrivacyPrivateMemory,
		}}, nil
}

func TestSharedRunStartDoesNotReadOrFreezePersonalPreferenceSnapshots(t *testing.T) {
	reader := &contextPrivacyPreferenceReader{}
	runtime := assistantruntest.NewMemoryRuntime()
	commands := runruntime.NewCommandService(
		runtime,
		runruntime.SessionResolverFunc(func(context.Context, string, string) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		nil,
		nil,
		runruntime.WithPolicyResolver(testPolicyResolver()),
	)
	useCases := runapplication.NewUseCases(
		commands,
		runapplication.WithPreferenceSnapshots(reader),
	)
	run, err := useCases.Start(
		t.Context(),
		"account-shared",
		"session-shared",
		"trace-shared",
		runapplication.StartInput{
			ClientRequestID: "request-shared",
			Intent: rundomain.Intent{
				Kind:   "answer",
				Answer: &rundomain.AnswerIntent{Text: "帮群里整理行程"},
			},
			TrustedPersonaID: "persona-shared",
			TrustedRequestContext: runruntime.RequestContext{
				SurfaceKind: "conversation",
				SurfaceID:   "conversation-shared",
				PersonaID:   "persona-shared",
			},
		},
	)
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	if reader.calls != 0 {
		t.Fatalf("shared Start read private preference snapshots %d times", reader.calls)
	}
	if len(run.SessionPreferences) != 0 || len(run.LongTermPreferences) != 0 {
		t.Fatalf(
			"shared Run froze private session=%#v longTerm=%#v",
			run.SessionPreferences,
			run.LongTermPreferences,
		)
	}
}

func TestDefaultRecallDoesNotTreatLongTermPreferenceAsAuthorizedContext(t *testing.T) {
	hints, err := contextassembly.NewRecallCoordinator().Recall(
		t.Context(),
		contextassembly.RecallRequest{
			DomainID: "travel",
			Turn: assistant.AssistantTurn{
				TurnID: "turn-private-memory",
				Input:  assistant.AssistantTurnInput{Text: "推荐晚餐"},
				LongTermPreferences: []preferencemodel.AssistantPreferenceSnapshot{{
					PreferenceID: "memory-private",
					Scope:        preferencemodel.ScopeLongTerm,
					Kind:         preferencemodel.KindDietaryRestrictions,
					Value:        contextPrivacyPrivateMemory,
				}},
			},
		},
	)
	if err != nil {
		t.Fatalf("Recall() error = %v", err)
	}
	if len(hints) != 0 {
		t.Fatalf("default recall bypassed SkillContext consent: %#v", hints)
	}
}

type contextPrivacyCapturingBackend struct {
	requests []ports.ModelCompletionRequest
}

func (backend *contextPrivacyCapturingBackend) Complete(
	_ context.Context,
	request ports.ModelCompletionRequest,
) (ports.ModelCompletionResult, error) {
	backend.requests = append(backend.requests, request)
	return ports.ModelCompletionResult{Content: "已完成"}, nil
}

func (backend *contextPrivacyCapturingBackend) Stream(
	ctx context.Context,
	request ports.ModelCompletionRequest,
	emit func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
	result, err := backend.Complete(ctx, request)
	if err != nil {
		return ports.ModelCompletionResult{}, err
	}
	if err := emit(ports.ModelTextDelta{Text: result.Content}); err != nil {
		return ports.ModelCompletionResult{}, err
	}
	return result, nil
}

func TestProviderUsesPrivateMemoryOnlyFromConsentAdmittedSkillContext(t *testing.T) {
	backend := &contextPrivacyCapturingBackend{}
	provider := orchestration.ProviderBackedModelProvider{Backend: backend}
	request := orchestration.ModelRequest{
		Stage:           string(ports.ModelStageFinal),
		Prompt:          "请输出最终回答。",
		UserQuestion:    "推荐晚餐",
		ProblemClass:    "general",
		SearchIntensity: "medium",
		Observation:     map[string]any{},
		SessionPreferences: []preferencemodel.AssistantPreferenceSnapshot{{
			PreferenceID: "typed-style",
			Scope:        preferencemodel.ScopeSession,
			Kind:         preferencemodel.KindReplyLength,
			Value:        "concise",
		}},
		LongTermPreferences: []preferencemodel.AssistantPreferenceSnapshot{{
			PreferenceID: "memory-private",
			Scope:        preferencemodel.ScopeLongTerm,
			Kind:         preferencemodel.KindDietaryRestrictions,
			Value:        contextPrivacyPrivateMemory,
		}},
	}
	if _, err := provider.Complete(t.Context(), request); err != nil {
		t.Fatalf("Complete(without SkillContext) error = %v", err)
	}
	withoutConsent := backend.requests[0].Messages[1].Content
	if strings.Contains(withoutConsent, contextPrivacyPrivateMemory) {
		t.Fatalf("provider bypassed SkillContext consent: %q", withoutConsent)
	}
	if !strings.Contains(withoutConsent, "回答保持简洁") {
		t.Fatalf("typed response-style preference was lost: %q", withoutConsent)
	}

	request.ContextAssembly = &contextassembly.AssemblyResult{
		SkillContextSnapshot: &skillcontext.Snapshot{
			SnapshotID: "context-consent-admitted",
			Segments: []skillcontext.Segment{{
				SegmentID:        "segment-private-memory",
				SlotID:           "turn.preferences",
				Kind:             "memory",
				SourceRef:        "assistant.AssistantPreference:memory-private",
				DescriptorID:     "assistant.preference_context",
				DescriptorDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
				Authority:        assistantgenerated.AssistantContextAuthorityUserDeclared,
				Sensitivity:      assistantgenerated.AssistantContextSensitivityPrivate,
				CapturedAt:       time.Date(2026, 8, 8, 8, 0, 0, 0, time.UTC),
				Digest:           "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
				Value:            map[string]any{"dietaryRestriction": contextPrivacyPrivateMemory},
			}},
		},
	}
	if _, err := provider.Complete(t.Context(), request); err != nil {
		t.Fatalf("Complete(with SkillContext) error = %v", err)
	}
	withConsent := backend.requests[1].Messages[1].Content
	if count := strings.Count(withConsent, contextPrivacyPrivateMemory); count != 1 {
		t.Fatalf("private memory occurrences=%d, want exactly one admitted segment: %q", count, withConsent)
	}
}

type contextPrivacyAssembler struct {
	turns []assistant.AssistantTurn
}

func (assembler *contextPrivacyAssembler) Assemble(
	_ context.Context,
	input contextassembly.AssemblyInput,
) (contextassembly.AssemblyResult, error) {
	assembler.turns = append(assembler.turns, input.Turn)
	return contextassembly.AssemblyResult{
		CanEnterDomain: true,
		DomainID:       input.DomainID,
		ChannelID:      string(input.Channel.ID()),
		MemoryScope:    string(input.Channel.ContextPersistence()),
		SkillContextSnapshot: &skillcontext.Snapshot{
			SnapshotID: "context-owner-backed-conversation",
			Segments: []skillcontext.Segment{{
				SegmentID:        "segment-conversation",
				SlotID:           "conversation.context",
				Kind:             "conversation",
				SourceRef:        "chat.Conversation:conversation-shared",
				DescriptorID:     "chat.conversation_context",
				DescriptorDigest: "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
				Authority:        assistantgenerated.AssistantContextAuthorityDomainCanonical,
				Sensitivity:      assistantgenerated.AssistantContextSensitivityInternal,
				CapturedAt:       time.Date(2026, 8, 8, 8, 0, 0, 0, time.UTC),
				Digest:           "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
				Value:            map[string]any{"fact": contextPrivacyOwnerFact},
			}},
		},
	}, nil
}

type contextPrivacyRecordingModel struct {
	requests []orchestration.ModelRequest
}

func (model *contextPrivacyRecordingModel) Complete(
	_ context.Context,
	request orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	model.requests = append(model.requests, request)
	if request.Stage == string(ports.ModelStageReasoning) {
		return orchestration.ModelResponse{
			StructuredDelta: map[string]any{"nextAction": "answer"},
		}, nil
	}
	return orchestration.ModelResponse{
		Text:            "已根据群聊事实整理。",
		StructuredDelta: map[string]any{"userMarkdown": "已根据群聊事实整理。"},
	}, nil
}

type contextPrivacySubagentPlanner struct {
	turns []assistant.AssistantTurn
}

func (planner *contextPrivacySubagentPlanner) PlanSubagents(
	_ context.Context,
	turn assistant.AssistantTurn,
	_ orchestration.SkillSelection,
) ([]orchestration.SubagentPlan, error) {
	planner.turns = append(planner.turns, turn)
	return nil, nil
}

func TestSharedExecutionAndReplayStripPersonalInputsButKeepOwnerBackedContext(t *testing.T) {
	model := &contextPrivacyRecordingModel{}
	assembler := &contextPrivacyAssembler{}
	planner := &contextPrivacySubagentPlanner{}
	loop := orchestration.NewAgentLoop(
		nil,
		orchestration.ReactRuntime{Model: model},
		func() time.Time { return time.Date(2026, 8, 8, 8, 0, 0, 0, time.UTC) },
	)
	loop.Contexts = assembler
	loop.Subagents = planner
	loop.Catalog = skillfixture.StaticLoader{Manifests: []skillpkg.Manifest{{
		SkillID:      "privacy_context_test",
		DisplayName:  "Privacy Context Test",
		DomainID:     "assistant",
		ProblemClass: "general",
	}}}
	turn := contextPrivacySharedTurn()
	var prepared orchestration.PreparedExecution
	_, failure, err := loop.RunTurnWithPreparedExecution(
		t.Context(),
		turn,
		nil,
		func(value orchestration.PreparedExecution) error {
			prepared = value
			return nil
		},
	)
	if err != nil || failure != nil {
		t.Fatalf("RunTurnWithPreparedExecution() failure=%+v err=%v", failure, err)
	}
	if prepared.ContextSnapshot == nil || len(prepared.ContextSnapshot.Segments) != 1 ||
		prepared.ContextSnapshot.Segments[0].Value["fact"] != contextPrivacyOwnerFact {
		t.Fatalf("owner-backed conversation context was removed: %#v", prepared.ContextSnapshot)
	}

	_, failure, err = loop.RunTurnWithSinkAfterSeq(t.Context(), turn, 50, nil)
	if err != nil || failure != nil {
		t.Fatalf("RunTurnWithSinkAfterSeq() failure=%+v err=%v", failure, err)
	}
	for index, admittedTurn := range append(assembler.turns, planner.turns...) {
		assertContextPrivacySharedTurnSanitized(t, index, admittedTurn)
	}
	if len(model.requests) == 0 {
		t.Fatal("model was not invoked")
	}
	for index, request := range model.requests {
		if len(request.ContextTurns) != 0 || request.ContextSummary != nil ||
			request.PageContext != nil || len(request.SessionPreferences) != 0 ||
			len(request.LongTermPreferences) != 0 ||
			request.FeedbackContext.Decision != "shared_surface_excluded" {
			t.Fatalf("model request %d retained personal context: %#v", index, request)
		}
		if request.ContextAssembly == nil || request.ContextAssembly.SkillContextSnapshot == nil ||
			request.ContextAssembly.SkillContextSnapshot.Segments[0].Value["fact"] != contextPrivacyOwnerFact {
			t.Fatalf("model request %d lost owner-backed context: %#v", index, request.ContextAssembly)
		}
	}
}

func contextPrivacySharedTurn() assistant.AssistantTurn {
	return assistant.AssistantTurn{
		TurnID:         "turn-context-privacy",
		ExecutionRunID: "run-context-privacy",
		SessionID:      "session-context-privacy",
		UserID:         "account-context-privacy",
		SkillID:        "privacy_context_test",
		DomainID:       "assistant",
		Input:          assistant.AssistantTurnInput{Text: "帮群里整理行程"},
		ContextTurns: []assistant.AssistantRunContextTurn{{
			Role: "user", Text: "caller-session-private-turn",
		}},
		ContextSummary: &assistant.AssistantRunContextSummary{
			SummaryID: "summary-private", Text: "caller-session-private-summary",
		},
		PageContext: &assistant.AssistantContextSnapshot{
			PageType: "private_profile",
			PageObjects: []assistant.AssistantPageObjectRef{{
				ObjectTypeRef: "user.PrivateProfile", ObjectID: "private-profile",
			}},
		},
		SessionPreferences: []preferencemodel.AssistantPreferenceSnapshot{{
			PreferenceID: "session-private", Kind: preferencemodel.KindTone, Value: "warm",
		}},
		LongTermPreferences: []preferencemodel.AssistantPreferenceSnapshot{{
			PreferenceID: "memory-private", Kind: preferencemodel.KindDietaryRestrictions, Value: contextPrivacyPrivateMemory,
		}},
		Trigger: assistant.AssistantTurnTrigger{
			Type: "chat_assistant_mentioned", MessageID: "message-shared",
		},
		RequestContext: assistant.AssistantRunRequestContext{
			SurfaceKind: "conversation",
			SurfaceID:   "conversation-shared",
			PersonaID:   "persona-context-privacy",
		},
		FeedbackContextSnapshot: assistant.AssistantFeedbackContextSnapshot{
			Decision: "injected", FeedbackSampleCount: 20,
		},
		FrozenPolicySelection: assistant.AssistantFrozenPolicySelection{
			PolicyID:        "privacy-policy",
			ReleaseDigest:   "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
			Cohort:          "control",
			RolloutRevision: 1,
			RuleID:          "privacy-rule",
			Template: assistant.AssistantFrozenPolicyTemplate{
				TemplateID:      "privacy-template",
				SkillID:         "privacy_context_test",
				DomainID:        "assistant",
				PromptPolicy:    "Use only admitted context.",
				SearchIntensity: "medium",
			},
		},
	}
}

func assertContextPrivacySharedTurnSanitized(
	t *testing.T,
	index int,
	turn assistant.AssistantTurn,
) {
	t.Helper()
	if len(turn.ContextTurns) != 0 || turn.ContextSummary != nil ||
		turn.PageContext != nil || len(turn.SessionPreferences) != 0 ||
		len(turn.LongTermPreferences) != 0 ||
		turn.FeedbackContextSnapshot.Decision != "shared_surface_excluded" {
		t.Fatalf("shared turn %d retained personal context: %#v", index, turn)
	}
}
