package orchestration

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/reasoning"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

var (
	ErrExecutionCapabilityUnavailable = errors.New("assistant execution capability is unavailable")
	ErrExecutionBudgetExhausted       = errors.New("assistant execution budget is exhausted")
)

// ModelExecutionCapabilities describes provider-neutral behavior that the
// orchestration layer can rely on. It deliberately contains no provider or
// model identifiers and does not imply native tool calling: ToolCalling also
// includes the canonical structured-output fallback.
type ModelExecutionCapabilities struct {
	ToolCalling     bool
	ParallelTools   bool
	ReasoningEffort bool
}

// ModelExecutionCapabilityProvider makes capability negotiation explicit. A
// model that cannot advertise its behavior is rejected when a durable
// ReasoningProfile requires that behavior; the runtime never guesses from a
// concrete provider type or model name.
type ModelExecutionCapabilityProvider interface {
	ModelExecutionCapabilities() ModelExecutionCapabilities
}

// RuntimeExecutionCapabilities are supplied by the execution host rather than
// the model provider. Background execution and compaction are properties of
// the durable Agent runtime, not of a completion endpoint.
type RuntimeExecutionCapabilities struct {
	Background bool
	Compaction bool
}

// AgentExecutionPolicy is the immutable, request-scoped projection of the
// frozen ReasoningProfile. The canonical profile remains owned by runruntime;
// this value only derives the limits needed by AgentLoop.
type AgentExecutionPolicy struct {
	Profile                generated.AssistantReasoningProfile
	MaxDuration            time.Duration
	MaxTokens              int64
	MaxCostUnits           int64
	MaxToolCalls           int
	MaxSubagents           int
	MaxSources             int
	ReflectionEverySteps   int
	SourceBreadth          int
	SourceDepth            int
	CheckpointEvery        time.Duration
	StopOnBudgetExhaustion bool
}

type executionPolicyContextKey struct{}

// WithDurableReasoningProfile negotiates a frozen profile against the actual
// model and the durable execution host, then stores an immutable copy in ctx.
// DurableRunExecutor is expected to call this once before entering AgentLoop.
func (l *AgentLoop) WithDurableReasoningProfile(
	ctx context.Context,
	profile runruntime.ReasoningProfileConfig,
) (context.Context, error) {
	if l == nil {
		return ctx, errors.New("assistant AgentLoop is nil")
	}
	return WithAgentExecutionPolicy(
		ctx,
		profile,
		l.React.Model,
		RuntimeExecutionCapabilities{
			Background: true,
			Compaction: runruntime.ContextCompactionAvailable(ctx),
		},
	)
}

// WithAgentExecutionPolicy is also exposed for bounded non-durable hosts and
// local-contract tests. Callers must truthfully advertise their runtime
// capabilities; missing required behavior fails closed.
func WithAgentExecutionPolicy(
	ctx context.Context,
	profile runruntime.ReasoningProfileConfig,
	model ModelProvider,
	runtimeCapabilities RuntimeExecutionCapabilities,
) (context.Context, error) {
	policy, err := newAgentExecutionPolicy(profile, model, runtimeCapabilities)
	if err != nil {
		return ctx, err
	}
	ctx = context.WithValue(ctx, executionPolicyContextKey{}, policy)
	if _, exists := executionBudgetConsumptionStateFromContext(ctx); !exists {
		ctx = withExecutionBudgetConsumption(
			ctx,
			ExecutionBudgetConsumption{},
			0,
			nil,
		)
	}
	return ctx, nil
}

func newAgentExecutionPolicy(
	profile runruntime.ReasoningProfileConfig,
	model ModelProvider,
	runtimeCapabilities RuntimeExecutionCapabilities,
) (AgentExecutionPolicy, error) {
	if err := validateExecutionProfile(profile); err != nil {
		return AgentExecutionPolicy{}, err
	}
	provider, ok := model.(ModelExecutionCapabilityProvider)
	if !ok {
		return AgentExecutionPolicy{}, fmt.Errorf(
			"%w: model provider does not advertise execution capabilities",
			ErrExecutionCapabilityUnavailable,
		)
	}
	modelCapabilities := provider.ModelExecutionCapabilities()
	if err := requireExecutionCapabilities(
		profile,
		modelCapabilities,
		runtimeCapabilities,
	); err != nil {
		return AgentExecutionPolicy{}, err
	}
	return AgentExecutionPolicy{
		Profile:                profile.Profile,
		MaxDuration:            profile.Budget.MaxDuration,
		MaxTokens:              profile.Budget.MaxTokens,
		MaxCostUnits:           profile.Budget.MaxCostUnits,
		MaxToolCalls:           profile.Budget.MaxToolCalls,
		MaxSubagents:           profile.Budget.MaxSubagents,
		MaxSources:             profile.Budget.MaxSources,
		ReflectionEverySteps:   profile.ReflectionEverySteps,
		SourceBreadth:          profile.SourceBreadth,
		SourceDepth:            profile.SourceDepth,
		CheckpointEvery:        profile.CheckpointEvery,
		StopOnBudgetExhaustion: profile.StopRules.StopOnBudgetExhaustion,
	}, nil
}

func validateExecutionProfile(profile runruntime.ReasoningProfileConfig) error {
	if strings.TrimSpace(profile.Profile.WireName()) == "" ||
		profile.Budget.MaxDuration <= 0 || profile.Budget.MaxTokens <= 0 ||
		profile.Budget.MaxCostUnits <= 0 || profile.Budget.MaxToolCalls < 0 ||
		profile.Budget.MaxSubagents < 0 || profile.Budget.MaxSources <= 0 ||
		profile.ReflectionEverySteps <= 0 || profile.SourceBreadth <= 0 ||
		profile.SourceDepth <= 0 {
		return fmt.Errorf("invalid AgentLoop execution profile %s", profile.Profile)
	}
	return nil
}

func requireExecutionCapabilities(
	profile runruntime.ReasoningProfileConfig,
	model ModelExecutionCapabilities,
	runtime RuntimeExecutionCapabilities,
) error {
	missing := make([]string, 0, 5)
	if profile.Capability.ToolCalling && !model.ToolCalling {
		missing = append(missing, "tool_calling")
	}
	if profile.Capability.ParallelTools && !model.ParallelTools {
		missing = append(missing, "parallel_tools")
	}
	if profile.Capability.ReasoningEffort && !model.ReasoningEffort {
		missing = append(missing, "reasoning_effort")
	}
	if profile.Capability.Background && !runtime.Background {
		missing = append(missing, "background")
	}
	if profile.Capability.Compaction && !runtime.Compaction {
		missing = append(missing, "compaction")
	}
	if len(missing) > 0 {
		return fmt.Errorf(
			"%w for reasoning profile %s: %s",
			ErrExecutionCapabilityUnavailable,
			profile.Profile,
			strings.Join(missing, ","),
		)
	}
	return nil
}

func executionPolicyFromContext(ctx context.Context) (AgentExecutionPolicy, bool) {
	if ctx == nil {
		return AgentExecutionPolicy{}, false
	}
	policy, ok := ctx.Value(executionPolicyContextKey{}).(AgentExecutionPolicy)
	return policy.clone(), ok
}

// AgentExecutionPolicyFromContext returns a copy for observability, tests, and
// adapters that must project the effective request policy. Mutating the copy
// cannot affect an in-flight Run.
func AgentExecutionPolicyFromContext(
	ctx context.Context,
) (AgentExecutionPolicy, bool) {
	return executionPolicyFromContext(ctx)
}

func withExecutionPolicyValue(
	ctx context.Context,
	policy AgentExecutionPolicy,
) context.Context {
	return context.WithValue(ctx, executionPolicyContextKey{}, policy.clone())
}

func (p AgentExecutionPolicy) clone() AgentExecutionPolicy { return p }

func (p AgentExecutionPolicy) reactBudget(skillBudget react.Budget) react.Budget {
	maxToolCalls := skillBudget.MaxToolCalls
	if maxToolCalls < 0 {
		maxToolCalls = 0
	}
	if p.MaxToolCalls < maxToolCalls {
		maxToolCalls = p.MaxToolCalls
	}
	maxIterations := skillBudget.MaxIterations
	profileIterations := p.MaxToolCalls + 1
	if maxIterations <= 0 || profileIterations < maxIterations {
		maxIterations = profileIterations
	}
	if maxIterations <= 0 {
		maxIterations = 1
	}
	return react.Budget{
		MaxIterations: maxIterations,
		MaxToolCalls:  maxToolCalls,
	}
}

func (p AgentExecutionPolicy) maxSubagentCount(fallback int) int {
	if fallback < 0 {
		fallback = 0
	}
	if p.MaxSubagents < fallback {
		return p.MaxSubagents
	}
	return fallback
}

type ExecutionBudgetError struct {
	Dimension string
	Limit     int64
	Consumed  int64
}

func (e ExecutionBudgetError) Error() string {
	return fmt.Sprintf(
		"%s: dimension=%s limit=%d consumed=%d",
		ErrExecutionBudgetExhausted,
		e.Dimension,
		e.Limit,
		e.Consumed,
	)
}

func (e ExecutionBudgetError) Unwrap() error { return ErrExecutionBudgetExhausted }
