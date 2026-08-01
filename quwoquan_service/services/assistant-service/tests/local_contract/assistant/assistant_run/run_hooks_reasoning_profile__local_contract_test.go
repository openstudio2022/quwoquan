package assistant_run_test

import (
	"context"
	"errors"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

type hookStub struct {
	name   string
	phases []runruntime.HookPhase
	invoke func(runruntime.HookInput) runruntime.HookResult
}

func (h hookStub) Name() string                   { return h.name }
func (h hookStub) Phases() []runruntime.HookPhase { return h.phases }
func (h hookStub) Invoke(_ context.Context, input runruntime.HookInput) (runruntime.HookResult, error) {
	return h.invoke(input), nil
}

func TestRunHooksCanTransformAndBlockButCannotRewriteProtectedFacts(t *testing.T) {
	registry, err := runruntime.NewHookRegistry(
		runruntime.RegisteredHook{Priority: 20, Hook: hookStub{
			name:   "approval",
			phases: []runruntime.HookPhase{runruntime.HookPreToolUse},
			invoke: func(input runruntime.HookInput) runruntime.HookResult {
				return runruntime.HookResult{
					Decision: runruntime.HookRequireConfirmation,
					Reason:   "device write requires confirmation",
					Data:     input.Data,
				}
			},
		}},
		runruntime.RegisteredHook{Priority: 10, Hook: hookStub{
			name:   "normalize",
			phases: []runruntime.HookPhase{runruntime.HookPreToolUse},
			invoke: func(input runruntime.HookInput) runruntime.HookResult {
				input.Data["normalized"] = true
				return runruntime.HookResult{Decision: runruntime.HookAllow, Data: input.Data}
			},
		}},
	)
	if err != nil {
		t.Fatal(err)
	}
	result, err := registry.Run(context.Background(), runruntime.HookInput{
		Phase: runruntime.HookPreToolUse,
		Data:  map[string]any{"tool": "calendar_write"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.Decision != runruntime.HookRequireConfirmation || result.Data["normalized"] != true {
		t.Fatalf("hook result = %#v", result)
	}

	compactionRegistry, err := runruntime.NewHookRegistry(runruntime.RegisteredHook{Hook: hookStub{
		name:   "bad_compactor",
		phases: []runruntime.HookPhase{runruntime.HookPostCompact},
		invoke: func(input runruntime.HookInput) runruntime.HookResult {
			return runruntime.HookResult{
				Decision:             runruntime.HookAllow,
				ProtectedFactsDigest: "rewritten",
			}
		},
	}})
	if err != nil {
		t.Fatal(err)
	}
	_, err = compactionRegistry.Run(context.Background(), runruntime.HookInput{
		Phase:                runruntime.HookPostCompact,
		ProtectedFactsDigest: "canonical",
	})
	if err == nil {
		t.Fatal("post-compact hook rewrote protected facts")
	}
}

func TestReasoningProfilesAreCapabilityNegotiatedAndNotProviderNamed(t *testing.T) {
	configs := make([]runruntime.ReasoningProfileConfig, 0, 4)
	for _, profile := range []generated.AssistantReasoningProfile{
		generated.AssistantReasoningProfileFast,
		generated.AssistantReasoningProfileBalanced,
		generated.AssistantReasoningProfileDeep,
		generated.AssistantReasoningProfileBackgroundLong,
	} {
		config := runruntime.ReasoningProfileConfig{
			Profile: profile,
			Capability: runruntime.CapabilityRequirements{
				ToolCalling:     true,
				ReasoningEffort: true,
			},
			Budget: runruntime.ReasoningBudget{
				MaxDuration:  5 * time.Minute,
				MaxTokens:    10_000,
				MaxToolCalls: 10,
				MaxSubagents: 2,
				MaxSources:   10,
			},
			ReflectionEverySteps: 3,
			CheckpointEvery:      time.Minute,
			StopRules: runruntime.ReasoningStopRules{
				RequireDefinitionOfDone: true,
				RequireEvidence:         true,
				RequireVerifier:         true,
				StopOnBudgetExhaustion:  true,
			},
		}
		if profile == generated.AssistantReasoningProfileBackgroundLong {
			config.Capability.Background = true
			config.Capability.Compaction = true
		}
		configs = append(configs, config)
	}
	catalog, err := runruntime.NewReasoningProfileCatalog(configs)
	if err != nil {
		t.Fatal(err)
	}
	background, err := catalog.Resolve(generated.AssistantReasoningProfileBackgroundLong)
	if err != nil || !background.Capability.Background || !background.StopRules.RequireVerifier {
		t.Fatalf("background profile = %#v, error = %v", background, err)
	}

	configs[3].Capability.Compaction = false
	if _, err := runruntime.NewReasoningProfileCatalog(configs); err == nil {
		t.Fatal("background_long without compaction was accepted")
	}
	if _, err := catalog.Resolve(generated.AssistantReasoningProfile("provider-model-name")); err == nil || errors.Is(err, context.Canceled) {
		t.Fatalf("unknown provider-specific profile error = %v", err)
	}
}
