package runruntime

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
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
	Phase                HookPhase
	Run                  Run
	TaskID               string
	ToolName             string
	Data                 map[string]any
	ProtectedFactsDigest string
}

type HookResult struct {
	Decision             HookDecision
	Reason               string
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
	byPhase map[HookPhase][]RegisteredHook
}

func NewHookRegistry(hooks ...RegisteredHook) (*HookRegistry, error) {
	registry := &HookRegistry{byPhase: map[HookPhase][]RegisteredHook{}}
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
		if input.Phase == HookPostCompact && result.ProtectedFactsDigest != input.ProtectedFactsDigest {
			return HookResult{}, errors.New("protected canonical facts changed during compaction")
		}
		if next.Decision == HookBlock || next.Decision == HookRequireConfirmation {
			result.Decision = next.Decision
			result.Reason = strings.TrimSpace(next.Reason)
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
