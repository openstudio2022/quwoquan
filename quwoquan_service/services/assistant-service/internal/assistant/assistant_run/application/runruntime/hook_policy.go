package runruntime

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"
)

const (
	HookPolicyAudit                    = "platform.audit"
	HookPolicyPermissionRevalidation   = "platform.permission_revalidation"
	HookPolicyPromptInjectionIsolation = "platform.prompt_injection_isolation"
	HookPolicyBudgetEnforcement        = "platform.budget_enforcement"
	HookPolicyBeforeComplete           = "platform.before_complete"
)

var mandatoryHookPolicyRefs = []string{
	HookPolicyAudit,
	HookPolicyPermissionRevalidation,
	HookPolicyPromptInjectionIsolation,
	HookPolicyBudgetEnforcement,
	HookPolicyBeforeComplete,
}

type HookAuditRecord struct {
	HookPolicyRef        string
	InvocationID         string
	Phase                HookPhase
	RunDigest            string
	RunRevision          int64
	Outcome              string
	TaskID               string
	ToolName             string
	ProtectedFactsDigest string
	RecordedAt           time.Time
}

type HookAuditSink interface {
	RecordHookAudit(context.Context, HookAuditRecord) error
}

type HookAuditSinkFunc func(context.Context, HookAuditRecord) error

func (record HookAuditSinkFunc) RecordHookAudit(
	ctx context.Context,
	entry HookAuditRecord,
) error {
	return record(ctx, entry)
}

type SlogHookAuditSink struct {
	Logger *slog.Logger
}

func (sink SlogHookAuditSink) RecordHookAudit(
	ctx context.Context,
	record HookAuditRecord,
) error {
	logger := sink.Logger
	if logger == nil {
		logger = slog.Default()
	}
	logger.InfoContext(
		ctx,
		"assistant lifecycle hook audited",
		slog.String("hook_policy_ref", record.HookPolicyRef),
		slog.String("invocation_id", record.InvocationID),
		slog.String("phase", string(record.Phase)),
		slog.String("run_digest", record.RunDigest),
		slog.Int64("run_revision", record.RunRevision),
		slog.String("outcome", record.Outcome),
		slog.String("task_id", record.TaskID),
		slog.String("tool_name", record.ToolName),
		slog.String("protected_facts_digest", record.ProtectedFactsDigest),
	)
	return nil
}

// NewProductionHookRegistry installs the mandatory platform-owned lifecycle
// policies. Skill packages can reference these IDs but cannot provide Hook
// code or expand their permissions.
func NewProductionHookRegistry(
	model ConstrainedVerificationModel,
	auditSink HookAuditSink,
) (*HookRegistry, error) {
	if auditSink == nil {
		return nil, errors.New("assistant lifecycle hook audit sink is required")
	}
	verifiers, err := NewPlatformVerifierRegistry(model)
	if err != nil {
		return nil, err
	}
	registry, err := newHookRegistry(
		verifiers,
		RegisteredHook{Priority: 0, Hook: auditLifecycleHook{sink: auditSink}},
		RegisteredHook{Priority: 10, Hook: permissionRevalidationHook{}},
		RegisteredHook{Priority: 20, Hook: promptInjectionIsolationHook{}},
		RegisteredHook{Priority: 30, Hook: budgetEnforcementHook{}},
		RegisteredHook{Priority: 40, Hook: beforeCompleteHook{}},
	)
	if err != nil {
		return nil, err
	}
	if err := registry.ValidatePolicyRefs(mandatoryHookPolicyRefs); err != nil {
		return nil, err
	}
	return registry, nil
}

func (registry *HookRegistry) VerifyCompletion(
	ctx context.Context,
	definition DefinitionOfDone,
	input VerificationInput,
) VerificationVerdict {
	if registry == nil || registry.verifiers == nil {
		return VerificationVerdict{
			Missing:         uniqueSorted(definition.VerificationRequirements),
			DecisionSummary: "Definition of Done verifier registry is unavailable",
		}
	}
	return registry.verifiers.Verify(ctx, definition, input)
}

func (registry *HookRegistry) ValidatePolicyRefs(refs []string) error {
	if registry == nil || len(registry.byName) == 0 || len(refs) == 0 {
		return errors.New("Skill orchestration hook policy refs are empty")
	}
	referenced := map[string]struct{}{}
	for _, ref := range refs {
		ref = strings.TrimSpace(ref)
		if _, duplicate := referenced[ref]; duplicate {
			return fmt.Errorf("duplicate Skill Hook policy ref %q", ref)
		}
		if _, registered := registry.byName[ref]; !registered {
			return fmt.Errorf("Skill references unknown platform Hook policy %q", ref)
		}
		referenced[ref] = struct{}{}
	}
	for _, required := range mandatoryHookPolicyRefs {
		if _, present := referenced[required]; !present {
			return fmt.Errorf("Skill omits mandatory Hook policy %q", required)
		}
	}
	if len(referenced) != len(mandatoryHookPolicyRefs) {
		return errors.New("Skill Hook policy refs contain a non-mandatory policy")
	}
	return nil
}

func (registry *HookRegistry) ValidateVerifierRefs(
	requirements []string,
	refs []string,
) error {
	if registry == nil || registry.verifiers == nil {
		return errors.New("platform verifier registry is unavailable")
	}
	return registry.verifiers.ValidateProfileRefs(requirements, refs)
}

type auditLifecycleHook struct{ sink HookAuditSink }

func (hook auditLifecycleHook) Name() string { return HookPolicyAudit }

func (hook auditLifecycleHook) Phases() []HookPhase {
	return []HookPhase{
		HookPrePlan,
		HookPostPlan,
		HookPreToolUse,
		HookPostToolUse,
		HookPreCompact,
		HookPostCompact,
		HookBeforeComplete,
		HookOnBlocked,
		HookOnStop,
	}
}

func (hook auditLifecycleHook) Invoke(
	ctx context.Context,
	input HookInput,
) (HookResult, error) {
	if hook.sink == nil {
		return HookResult{}, errors.New("assistant lifecycle audit sink is unavailable")
	}
	if err := hook.sink.RecordHookAudit(ctx, HookAuditRecord{
		HookPolicyRef:        hook.Name(),
		InvocationID:         strings.TrimSpace(input.InvocationID),
		Phase:                input.Phase,
		RunDigest:            auditRunDigest(input.Run.RunID),
		RunRevision:          input.RunRevision,
		Outcome:              strings.TrimSpace(input.Outcome),
		TaskID:               strings.TrimSpace(input.TaskID),
		ToolName:             strings.TrimSpace(input.ToolName),
		ProtectedFactsDigest: strings.TrimSpace(input.ProtectedFactsDigest),
		RecordedAt:           time.Now().UTC(),
	}); err != nil {
		return HookResult{}, fmt.Errorf("persist lifecycle hook audit: %w", err)
	}
	return allowHookResult(input), nil
}

type permissionRevalidationHook struct{}

func (permissionRevalidationHook) Name() string {
	return HookPolicyPermissionRevalidation
}

func (permissionRevalidationHook) Phases() []HookPhase {
	return []HookPhase{HookPrePlan, HookPreToolUse}
}

func (permissionRevalidationHook) Invoke(
	_ context.Context,
	input HookInput,
) (HookResult, error) {
	revalidated, ok := input.Data["authorizationRevalidated"].(bool)
	if !ok || !revalidated || strings.TrimSpace(stringMapValue(input.Data, "skillId")) == "" {
		return blockHookResult(input, "current Skill authorization was not revalidated"), nil
	}
	if input.Phase == HookPreToolUse {
		toolName := strings.TrimSpace(stringMapValue(input.Data, "toolName"))
		if toolName == "" || toolName != strings.TrimSpace(input.ToolName) {
			return blockHookResult(input, "current Tool authorization proof is not bound to the tool call"), nil
		}
	}
	return allowHookResult(input), nil
}

type promptInjectionIsolationHook struct{}

func (promptInjectionIsolationHook) Name() string {
	return HookPolicyPromptInjectionIsolation
}

func (promptInjectionIsolationHook) Phases() []HookPhase {
	return []HookPhase{
		HookPrePlan,
		HookPostPlan,
		HookPreToolUse,
		HookPostToolUse,
		HookPreCompact,
		HookPostCompact,
		HookBeforeComplete,
	}
}

func (promptInjectionIsolationHook) Invoke(
	_ context.Context,
	input HookInput,
) (HookResult, error) {
	data, removed := isolateUntrustedInstructions(input.Data)
	if removed > 0 {
		data["promptInjectionIsolation"] = map[string]any{
			"removedProtectedFieldCount": removed,
		}
	}
	result := allowHookResult(input)
	result.Data = data
	return result, nil
}

type budgetEnforcementHook struct{}

func (budgetEnforcementHook) Name() string { return HookPolicyBudgetEnforcement }

func (budgetEnforcementHook) Phases() []HookPhase {
	return []HookPhase{HookPrePlan, HookPreToolUse, HookBeforeComplete}
}

func (budgetEnforcementHook) Invoke(
	_ context.Context,
	input HookInput,
) (HookResult, error) {
	if exhausted, _ := input.Data["budgetExhausted"].(bool); exhausted {
		return blockHookResult(input, "the frozen Run budget is exhausted"), nil
	}
	if input.Run.Checkpoint == nil {
		return allowHookResult(input), nil
	}
	consumption := input.Run.Checkpoint.BudgetConsumption
	budget := input.Run.ReasoningPolicy.Budget
	overrun := (budget.MaxTokens > 0 && consumption.Tokens > budget.MaxTokens) ||
		(budget.MaxCostUnits > 0 && consumption.CostUnits > budget.MaxCostUnits) ||
		(budget.MaxToolCalls >= 0 && consumption.ToolCalls > int64(budget.MaxToolCalls))
	if overrun {
		return blockHookResult(input, "the durable Run budget ledger exceeds the frozen profile"), nil
	}
	if input.Phase != HookBeforeComplete && !budgetDeadlineAllows(input.Run, time.Now().UTC()) {
		return blockHookResult(input, "the frozen Run deadline has elapsed"), nil
	}
	return allowHookResult(input), nil
}

type beforeCompleteHook struct{}

func (beforeCompleteHook) Name() string { return HookPolicyBeforeComplete }

func (beforeCompleteHook) Phases() []HookPhase { return []HookPhase{HookBeforeComplete} }

func (beforeCompleteHook) Invoke(
	_ context.Context,
	input HookInput,
) (HookResult, error) {
	verification, ok := input.Data["verification"].(map[string]any)
	if !ok {
		return blockHookResult(input, "completion has no verifier verdict"), nil
	}
	accepted, ok := verification["accepted"].(bool)
	if !ok || !accepted || emptyStructuredValue(verification["evidence"]) {
		return blockHookResult(input, "Definition of Done is not supported by verifier evidence"), nil
	}
	return allowHookResult(input), nil
}

func allowHookResult(input HookInput) HookResult {
	return HookResult{
		Decision:             HookAllow,
		Data:                 cloneMap(input.Data),
		ProtectedFactsDigest: input.ProtectedFactsDigest,
	}
}

func blockHookResult(input HookInput, reason string) HookResult {
	result := allowHookResult(input)
	result.Decision = HookBlock
	result.Reason = strings.TrimSpace(reason)
	return result
}

func isolateUntrustedInstructions(input map[string]any) (map[string]any, int) {
	protected := map[string]struct{}{
		"authorization": {}, "allowedtools": {}, "capabilitypolicy": {}, "chainofthought": {},
		"connectorgrant": {}, "consent": {}, "definitionofdone": {}, "instructions": {},
		"modeldelta": {}, "protectedfactsdigest": {}, "reasoningtext": {}, "system": {},
		"systeminstruction": {}, "systemprompt": {}, "toolpolicy": {},
	}
	removed := 0
	var sanitize func(any) any
	sanitize = func(value any) any {
		switch typed := value.(type) {
		case map[string]any:
			result := make(map[string]any, len(typed))
			for key, child := range typed {
				if _, blocked := protected[normalizedStructuredKey(key)]; blocked {
					removed++
					continue
				}
				result[key] = sanitize(child)
			}
			return result
		case []any:
			result := make([]any, len(typed))
			for index, child := range typed {
				result[index] = sanitize(child)
			}
			return result
		case []map[string]any:
			result := make([]map[string]any, 0, len(typed))
			for _, child := range typed {
				cleaned, _ := sanitize(child).(map[string]any)
				result = append(result, cleaned)
			}
			return result
		default:
			return value
		}
	}
	cleaned, _ := sanitize(input).(map[string]any)
	if cleaned == nil {
		cleaned = map[string]any{}
	}
	return cleaned, removed
}

func budgetDeadlineAllows(run Run, now time.Time) bool {
	if run.ReasoningPolicy.Budget.MaxDuration <= 0 || run.CreatedAt.IsZero() {
		return true
	}
	return now.Before(run.CreatedAt.UTC().Add(run.ReasoningPolicy.Budget.MaxDuration))
}

func stringMapValue(values map[string]any, key string) string {
	value, _ := values[key].(string)
	return value
}

func auditRunDigest(runID string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(runID)))
	return "sha256:" + hex.EncodeToString(digest[:])
}
