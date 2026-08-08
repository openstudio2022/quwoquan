package runruntime

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"
)

type HookPhase string

const (
	HookPrePlan        HookPhase = "pre_plan"
	HookPostPlan       HookPhase = "post_plan"
	HookPreToolUse     HookPhase = "pre_tool_use"
	HookPostToolUse    HookPhase = "post_tool_use"
	HookPreCompact     HookPhase = "pre_compact"
	HookPostCompact    HookPhase = "post_compact"
	HookBeforeComplete HookPhase = "before_complete"
	HookOnBlocked      HookPhase = "on_blocked"
	HookOnStop         HookPhase = "on_stop"
)

type HookDecision string

const (
	HookAllow               HookDecision = "allow"
	HookBlock               HookDecision = "block"
	HookRequireConfirmation HookDecision = "require_confirmation"
)

type HookInput struct {
	InvocationID         string
	Phase                HookPhase
	Run                  Run
	RunRevision          int64
	Outcome              string
	TaskID               string
	ToolName             string
	Data                 map[string]any
	ProtectedFactsDigest string
}

type HookResult struct {
	Decision             HookDecision
	Reason               string
	ConfirmationRef      string
	Data                 map[string]any
	ProtectedFactsDigest string
}

type Hook interface {
	Name() string
	Phases() []HookPhase
	Invoke(context.Context, HookInput) (HookResult, error)
}

type RegisteredHook struct {
	Priority int
	Hook     Hook
}

type HookRegistry struct {
	byPhase   map[HookPhase][]RegisteredHook
	byName    map[string]RegisteredHook
	verifiers *VerifierRegistry
}

type executionHookContext struct {
	registry *HookRegistry
	run      Run
}

type executionHookContextKey struct{}

// WithExecutionHooks freezes the Run and its hook registry into one execution
// claim. The context is process-local wiring only; hook decisions are still
// projected through the durable Run state machine by the worker.
func WithExecutionHooks(
	ctx context.Context,
	registry *HookRegistry,
	run Run,
) context.Context {
	return context.WithValue(ctx, executionHookContextKey{}, executionHookContext{
		registry: registry,
		run:      run,
	})
}

// InvokeExecutionHook is the sole AgentLoop entry point for lifecycle hooks.
// It deliberately exposes decision summaries and bounded structured data, not
// provider reasoning or chain-of-thought.
func InvokeExecutionHook(
	ctx context.Context,
	phase HookPhase,
	taskID string,
	toolName string,
	data map[string]any,
) (HookResult, error) {
	wiring, ok := ctx.Value(executionHookContextKey{}).(executionHookContext)
	if !ok || wiring.registry == nil {
		return HookResult{
			Decision: HookAllow,
			Data:     cloneMap(data),
		}, nil
	}
	startedAt := time.Now()
	result, err := wiring.registry.Run(ctx, HookInput{
		InvocationID:         StableHookInvocationID(wiring.run.RunID, phase, wiring.run.Revision),
		Phase:                phase,
		Run:                  wiring.run,
		RunRevision:          wiring.run.Revision,
		TaskID:               strings.TrimSpace(taskID),
		ToolName:             strings.TrimSpace(toolName),
		Data:                 cloneMap(data),
		ProtectedFactsDigest: ProtectedRunFactsDigest(wiring.run),
	})
	observeHookInvocation(phase, result.Decision, startedAt, err)
	return result, err
}

// StableHookInvocationID is the durable idempotency identity for one hook
// phase at one committed AssistantRun revision. Hook relays must preserve it
// across retries, owner takeover, acknowledgement loss, and process restart.
func StableHookInvocationID(runID string, phase HookPhase, revision int64) string {
	runID = strings.TrimSpace(runID)
	if runID == "" || !validHookPhase(phase) || revision <= 0 {
		return ""
	}
	return runID + ":" + string(phase) + ":" + int64String(revision)
}

func NewHookRegistry(hooks ...RegisteredHook) (*HookRegistry, error) {
	verifiers, err := NewPlatformVerifierRegistry(nil)
	if err != nil {
		return nil, err
	}
	return newHookRegistry(verifiers, hooks...)
}

func newHookRegistry(
	verifiers *VerifierRegistry,
	hooks ...RegisteredHook,
) (*HookRegistry, error) {
	if verifiers == nil {
		return nil, errors.New("assistant run verifier registry is required")
	}
	registry := &HookRegistry{
		byPhase:   map[HookPhase][]RegisteredHook{},
		byName:    map[string]RegisteredHook{},
		verifiers: verifiers,
	}
	seen := map[string]struct{}{}
	for _, registration := range hooks {
		if registration.Hook == nil || strings.TrimSpace(registration.Hook.Name()) == "" {
			return nil, errors.New("assistant run hook name is required")
		}
		name := registration.Hook.Name()
		if _, ok := seen[name]; ok {
			return nil, fmt.Errorf("duplicate assistant run hook %q", name)
		}
		seen[name] = struct{}{}
		registry.byName[name] = registration
		for _, phase := range registration.Hook.Phases() {
			if !validHookPhase(phase) {
				return nil, fmt.Errorf("invalid assistant run hook phase %q", phase)
			}
			registry.byPhase[phase] = append(registry.byPhase[phase], registration)
		}
	}
	for phase := range registry.byPhase {
		sort.SliceStable(registry.byPhase[phase], func(left, right int) bool {
			return registry.byPhase[phase][left].Priority < registry.byPhase[phase][right].Priority
		})
	}
	return registry, nil
}

func (r *HookRegistry) Run(ctx context.Context, input HookInput) (HookResult, error) {
	if r == nil || !validHookPhase(input.Phase) {
		return HookResult{}, errors.New("assistant run hook registry or phase is invalid")
	}
	result := HookResult{
		Decision:             HookAllow,
		Data:                 cloneMap(input.Data),
		ProtectedFactsDigest: input.ProtectedFactsDigest,
	}
	for _, registration := range r.byPhase[input.Phase] {
		nextInput := input
		nextInput.Data = cloneMap(result.Data)
		nextInput.ProtectedFactsDigest = result.ProtectedFactsDigest
		next, err := registration.Hook.Invoke(ctx, nextInput)
		if err != nil {
			return HookResult{}, fmt.Errorf("assistant run hook %s: %w", registration.Hook.Name(), err)
		}
		if next.Data != nil {
			result.Data = cloneMap(next.Data)
		}
		if next.ProtectedFactsDigest != "" {
			result.ProtectedFactsDigest = next.ProtectedFactsDigest
		}
		if result.ProtectedFactsDigest != input.ProtectedFactsDigest {
			return HookResult{}, errors.New("protected canonical facts changed during lifecycle hook")
		}
		if next.Decision != "" && next.Decision != HookAllow &&
			next.Decision != HookBlock && next.Decision != HookRequireConfirmation {
			return HookResult{}, fmt.Errorf(
				"assistant run hook %s returned invalid decision %q",
				registration.Hook.Name(),
				next.Decision,
			)
		}
		if next.Decision == HookBlock || next.Decision == HookRequireConfirmation {
			result.Decision = next.Decision
			result.Reason = strings.TrimSpace(next.Reason)
			result.ConfirmationRef = strings.TrimSpace(next.ConfirmationRef)
			if next.Decision == HookRequireConfirmation && result.ConfirmationRef == "" {
				return HookResult{}, fmt.Errorf(
					"assistant run hook %s omitted confirmation reference",
					registration.Hook.Name(),
				)
			}
			return result, nil
		}
	}
	return result, nil
}

func validHookPhase(phase HookPhase) bool {
	switch phase {
	case HookPrePlan, HookPostPlan, HookPreToolUse, HookPostToolUse,
		HookPreCompact, HookPostCompact, HookBeforeComplete, HookOnBlocked, HookOnStop:
		return true
	default:
		return false
	}
}
