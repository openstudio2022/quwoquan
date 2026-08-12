package tool

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/santhosh-tekuri/jsonschema/v6"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
)

type Request struct {
	ToolUseID              string
	IdempotencyKey         string
	IdempotencyMode        string
	ToolName               string
	Input                  map[string]any
	History                []string
	RunID                  string
	TurnID                 string
	AccountID              string
	PersonaID              string
	SurfaceKind            string
	SurfaceID              string
	DelegatedGrant         string
	ToolCatalogDigest      string
	RuntimeCandidateDigest string
	ContractGraphDigest    string
	MaximumToolCalls       int
}

type Result struct {
	Output         map[string]any
	TypedProposal  any
	ApprovalIntent *presentation.ActionIntent
}

type Handler func(context.Context, Request) (Result, error)

// UnavailableBinding records why one canonical cloud tool is deliberately not
// executable in the current runtime composition. It is not a handler and it is
// never exposed to the model. The composition root must provide this fact
// explicitly; an omitted handler without this evidence remains a startup error.
type UnavailableBinding struct {
	BindingKind string
	Reason      string
}

// RetryableFailure 由 handler 返回的错误可选实现，用于声明该失败是否值得在同一轮内重试。
// 未实现该接口的错误按不可重试处理，避免把契约错误当成瞬时抖动反复打上游。
type RetryableFailure interface {
	RetryableToolFailure() bool
}

// CanonicalFailure is the dependency-neutral failure envelope returned by a
// tool adapter when the canonical error contract is known. It prevents the
// coordinator from importing every tool implementation merely to classify its
// errors, while keeping URL, credentials and provider details out of the Run
// journal.
type CanonicalFailure struct {
	Code      string
	Origin    rtfailures.Origin
	Kind      rtfailures.Kind
	Nature    rtfailures.Nature
	Reason    string
	Retryable bool
	Cause     error
}

func (f CanonicalFailure) Error() string {
	if strings.TrimSpace(f.Code) == "" {
		return "canonical tool failure"
	}
	return f.Code
}

func (f CanonicalFailure) Unwrap() error { return f.Cause }

func (f CanonicalFailure) RetryableToolFailure() bool { return f.Retryable }

// ExecutionFailure 是工具执行耗尽预算后的统一失败形状。它携带该工具声明的恢复语义，
// 让上层用同一份 metadata 决定「失败本轮 / 跳过该工具 / 降级作答」，不再各自判断。
type ExecutionFailure struct {
	ToolName string
	Attempts int
	Recovery RecoveryPolicy
	Cause    error
}

func (f ExecutionFailure) Error() string {
	return fmt.Sprintf(
		"tool %q failed after %d attempt(s): %v",
		f.ToolName,
		f.Attempts,
		f.Cause,
	)
}

func (f ExecutionFailure) Unwrap() error { return f.Cause }

type Registry struct {
	metadata map[string]Metadata
	handlers map[string]Handler
}

func NewRegistry() Registry {
	return Registry{metadata: map[string]Metadata{}, handlers: map[string]Handler{}}
}

func (r Registry) IsZero() bool {
	return len(r.metadata) == 0 && len(r.handlers) == 0
}

func (r Registry) Metadata(toolName string) (Metadata, bool) {
	meta, ok := r.metadata[strings.TrimSpace(toolName)]
	if !ok {
		return Metadata{}, false
	}
	return mustCloneMetadata(meta), true
}

func (r Registry) ValidateInput(toolName string, input map[string]any) error {
	meta, ok := r.Metadata(toolName)
	if !ok {
		return fmt.Errorf("tool %q is not registered", toolName)
	}
	return validateSchema(meta.InputSchema, input, "input")
}

func (r *Registry) Register(meta Metadata, handler Handler) {
	meta = mustCloneMetadata(meta)
	if err := validateIdempotencyMetadata(meta); err != nil {
		panic(err)
	}
	if err := validateConfirmationMetadata(meta); err != nil {
		panic(err)
	}
	if r.metadata == nil {
		r.metadata = map[string]Metadata{}
	}
	if r.handlers == nil {
		r.handlers = map[string]Handler{}
	}
	r.metadata[meta.ToolName] = meta
	r.handlers[meta.ToolName] = handler
}

// RegisterDeviceAction registers proposal-only metadata. The cloud runtime must
// never own a handler for device_action; execution happens through the
// capability-gated native bridge after explicit user confirmation.
func (r *Registry) RegisterDeviceAction(meta Metadata) {
	meta = mustCloneMetadata(meta)
	if meta.Placement != PlacementDeviceAction || !meta.RequiresConfirmation ||
		meta.ReadOnly {
		panic("device action metadata must be confirmed and mutating")
	}
	if err := validateIdempotencyMetadata(meta); err != nil {
		panic(err)
	}
	if err := validateConfirmationMetadata(meta); err != nil {
		panic(err)
	}
	if r.metadata == nil {
		r.metadata = map[string]Metadata{}
	}
	if r.handlers == nil {
		r.handlers = map[string]Handler{}
	}
	r.metadata[meta.ToolName] = meta
	delete(r.handlers, meta.ToolName)
}

func mustCloneMetadata(meta Metadata) Metadata {
	cloned, err := meta.Clone()
	if err != nil {
		panic(err)
	}
	return cloned
}

func validateIdempotencyMetadata(meta Metadata) error {
	mode := strings.TrimSpace(meta.Idempotency)
	switch mode {
	case IdempotencyNone:
		if !meta.ReadOnly {
			return fmt.Errorf(
				"tool %q is mutating but does not require an idempotency key",
				meta.ToolName,
			)
		}
	case IdempotencyReadOnly, IdempotencyContentAddressed:
		if !meta.ReadOnly {
			return fmt.Errorf(
				"tool %q declares %q but is not read-only",
				meta.ToolName,
				mode,
			)
		}
	case IdempotencyKey:
		// An idempotency-key tool may be read-only, but every mutating tool must
		// use this mode so retries can never create a second side effect.
	default:
		return fmt.Errorf(
			"tool %q declares unsupported idempotency mode %q",
			meta.ToolName,
			mode,
		)
	}
	if meta.Placement == PlacementDeviceAction && mode != IdempotencyKey {
		return fmt.Errorf(
			"device action tool %q must declare %q idempotency",
			meta.ToolName,
			IdempotencyKey,
		)
	}
	return nil
}

func validateConfirmationMetadata(meta Metadata) error {
	confirmation := meta.Confirmation
	if !meta.RequiresConfirmation {
		if strings.TrimSpace(confirmation.TemplateRef) != "" ||
			len(confirmation.DisplayFields) > 0 {
			return fmt.Errorf("tool %q has confirmation UI but does not require confirmation", meta.ToolName)
		}
		return nil
	}
	if strings.TrimSpace(confirmation.TemplateRef) == "" ||
		strings.TrimSpace(confirmation.Title) == "" ||
		strings.TrimSpace(confirmation.Description) == "" ||
		strings.TrimSpace(confirmation.CompletionSummary) == "" ||
		len(confirmation.DisplayFields) == 0 {
		return fmt.Errorf("tool %q confirmation metadata is incomplete", meta.ToolName)
	}
	properties, _ := meta.InputSchema["properties"].(map[string]any)
	seen := map[string]struct{}{}
	for _, field := range confirmation.DisplayFields {
		key := strings.TrimSpace(field.InputKey)
		if key == "" || strings.TrimSpace(field.Label) == "" {
			return fmt.Errorf("tool %q confirmation field is invalid", meta.ToolName)
		}
		if _, ok := properties[key]; !ok {
			return fmt.Errorf("tool %q confirmation field %q is not in input schema", meta.ToolName, key)
		}
		if _, duplicate := seen[key]; duplicate {
			return fmt.Errorf("tool %q confirmation field %q is duplicated", meta.ToolName, key)
		}
		seen[key] = struct{}{}
	}
	return nil
}

func (r Registry) Execute(ctx context.Context, req Request) (Result, error) {
	meta, ok := r.metadata[req.ToolName]
	if !ok {
		return Result{}, fmt.Errorf("tool %q is not registered", req.ToolName)
	}
	if err := validateSchema(meta.InputSchema, req.Input, "input"); err != nil {
		return Result{}, err
	}
	if err := detectLoop(req.ToolName, req.History, meta.Resilience.LoopDetectionWindow); err != nil {
		return Result{}, err
	}
	if meta.RequiresIdempotencyKey() && strings.TrimSpace(req.IdempotencyKey) == "" {
		return Result{}, fmt.Errorf(
			"tool %q requires an idempotency key",
			req.ToolName,
		)
	}
	canonicalInput, err := cloneCanonicalInput(req.Input)
	if err != nil {
		return Result{}, err
	}
	req.Input = canonicalInput
	req.IdempotencyMode = meta.Idempotency
	handler, ok := r.handlers[req.ToolName]
	if !ok {
		return Result{}, fmt.Errorf("tool %q has no handler", req.ToolName)
	}
	attempts := meta.Resilience.MaxAttempts
	if attempts <= 0 {
		attempts = 1
	}
	var lastErr error
	completedAttempts := 0
	for attempt := 1; attempt <= attempts; attempt++ {
		completedAttempts = attempt
		attemptReq := req
		attemptReq.Input, err = cloneCanonicalInput(req.Input)
		if err != nil {
			return Result{}, err
		}
		attemptReq.History = append([]string(nil), req.History...)
		result, err := invokeWithTimeout(
			ctx,
			handler,
			attemptReq,
			meta.Resilience.TimeoutMs,
		)
		if err == nil {
			if err := validateSchema(meta.OutputSchema, result.Output, "output"); err != nil {
				// 输出契约不符是确定性错误，重试只会重复同一份坏数据。
				return Result{}, ExecutionFailure{
					ToolName: req.ToolName,
					Attempts: attempt,
					Recovery: meta.Recovery,
					Cause:    err,
				}
			}
			return result, nil
		}
		lastErr = err
		if attempt == attempts || !retryableToolFailure(err) {
			break
		}
		if err := waitRetryBackoff(ctx, meta.Resilience.RetryBackoffMs); err != nil {
			lastErr = err
			break
		}
	}
	return Result{}, ExecutionFailure{
		ToolName: req.ToolName,
		Attempts: completedAttempts,
		Recovery: meta.Recovery,
		Cause:    lastErr,
	}
}

func cloneCanonicalInput(input map[string]any) (map[string]any, error) {
	payload, err := json.Marshal(input)
	if err != nil {
		return nil, fmt.Errorf("tool input is not JSON encodable: %w", err)
	}
	var cloned map[string]any
	if err := json.Unmarshal(payload, &cloned); err != nil {
		return nil, fmt.Errorf("tool input is not canonical JSON: %w", err)
	}
	return cloned, nil
}

// invokeWithTimeout 让每次尝试独立受 TimeoutMs 约束；TimeoutMs<=0 表示沿用调用方期限。
func invokeWithTimeout(
	ctx context.Context,
	handler Handler,
	req Request,
	timeoutMs int,
) (Result, error) {
	if timeoutMs <= 0 {
		return handler(ctx, req)
	}
	attemptCtx, cancel := context.WithTimeout(
		ctx,
		time.Duration(timeoutMs)*time.Millisecond,
	)
	defer cancel()
	return handler(attemptCtx, req)
}

func waitRetryBackoff(ctx context.Context, backoffMs int) error {
	if backoffMs <= 0 {
		return ctx.Err()
	}
	timer := time.NewTimer(time.Duration(backoffMs) * time.Millisecond)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func retryableToolFailure(err error) bool {
	if errors.Is(err, context.DeadlineExceeded) {
		return true
	}
	if errors.Is(err, context.Canceled) {
		return false
	}
	var retryable RetryableFailure
	if errors.As(err, &retryable) {
		return retryable.RetryableToolFailure()
	}
	return false
}

func validateKeys(values map[string]any, keys []string, label string) error {
	for _, key := range keys {
		if _, ok := values[key]; !ok {
			return fmt.Errorf("tool %s missing required key %q", label, key)
		}
	}
	return nil
}

func validateSchema(schema map[string]any, value map[string]any, label string) error {
	if schema == nil {
		return fmt.Errorf("tool %s schema is missing", label)
	}
	compiler := jsonschema.NewCompiler()
	location := "mem://assistant-tool/" + label + ".json"
	if err := compiler.AddResource(location, schema); err != nil {
		return fmt.Errorf("tool %s schema is invalid: %w", label, err)
	}
	compiled, err := compiler.Compile(location)
	if err != nil {
		return fmt.Errorf("tool %s schema is invalid: %w", label, err)
	}
	payload, err := json.Marshal(value)
	if err != nil {
		return fmt.Errorf("tool %s is not JSON encodable: %w", label, err)
	}
	var canonical any
	if err := json.Unmarshal(payload, &canonical); err != nil {
		return fmt.Errorf("tool %s is not canonical JSON: %w", label, err)
	}
	if err := compiled.Validate(canonical); err != nil {
		return fmt.Errorf("tool %s violates schema: %w", label, err)
	}
	return nil
}

func detectLoop(toolName string, history []string, window int) error {
	if window <= 0 || len(history) < window {
		return nil
	}
	count := 0
	for i := len(history) - 1; i >= 0 && len(history)-i <= window; i-- {
		if history[i] == toolName {
			count++
		}
	}
	if count >= window {
		return fmt.Errorf("tool %q loop detected", toolName)
	}
	return nil
}

// BaseRegistry 不提供任何可执行工具。
//
// 所有工具都必须由 composition root 显式绑定经过端到端验证的真实 adapter。
// 设备动作在存在确认命令、端侧 continuation 与审计闭环前不得登记，避免把 proposal
// 冒充为已执行动作。检索类同样不得提供合成文档、fixture 或失败后伪成功。
func BaseRegistry() Registry {
	return NewRegistry()
}

// RegisterCanonical reconciles the canonical catalog with the current runtime
// composition. Device actions remain proposal-only. Every cloud tool must have
// exactly one real handler or one explicit unavailable binding; silent handler
// omissions, handler/unavailable conflicts and undeclared names all fail before
// the registry is mutated.
func RegisterCanonical(
	registry *Registry,
	handlers map[string]Handler,
	unavailable map[string]UnavailableBinding,
) error {
	if registry == nil {
		return errors.New("canonical tool registry is required")
	}
	catalog := CanonicalMetadata()
	canonical := make(map[string]Metadata, len(catalog))
	for _, meta := range catalog {
		canonical[meta.ToolName] = meta
	}
	for rawName, handler := range handlers {
		name := strings.TrimSpace(rawName)
		meta, found := canonical[name]
		if !found || name != rawName {
			return fmt.Errorf("tool handler %q is absent from the canonical catalog", rawName)
		}
		if meta.Placement == PlacementDeviceAction {
			return fmt.Errorf("device action tool %q cannot register a cloud handler", name)
		}
		if handler == nil {
			return fmt.Errorf("canonical tool %q registered a nil handler", name)
		}
	}
	for rawName, binding := range unavailable {
		name := strings.TrimSpace(rawName)
		meta, found := canonical[name]
		if !found || name != rawName {
			return fmt.Errorf("unavailable tool %q is absent from the canonical catalog", rawName)
		}
		if meta.Placement == PlacementDeviceAction {
			return fmt.Errorf("device action tool %q cannot be a cloud unavailable binding", name)
		}
		if strings.TrimSpace(binding.BindingKind) == "" ||
			strings.TrimSpace(binding.Reason) == "" {
			return fmt.Errorf("canonical tool %q unavailable binding is incomplete", name)
		}
		if _, conflict := handlers[name]; conflict {
			return fmt.Errorf("canonical tool %q has both a handler and unavailable binding", name)
		}
	}
	for _, meta := range catalog {
		if meta.Placement == PlacementDeviceAction {
			continue
		}
		handler, ok := handlers[meta.ToolName]
		if ok && handler != nil {
			continue
		}
		if _, explicitlyUnavailable := unavailable[meta.ToolName]; explicitlyUnavailable {
			continue
		}
		return fmt.Errorf(
			"canonical tool %q has no registered handler or unavailable binding",
			meta.ToolName,
		)
	}
	for _, meta := range catalog {
		if meta.Placement == PlacementDeviceAction {
			registry.RegisterDeviceAction(meta)
			continue
		}
		if _, explicitlyUnavailable := unavailable[meta.ToolName]; explicitlyUnavailable {
			continue
		}
		handler := handlers[meta.ToolName]
		if handler == nil {
			return fmt.Errorf(
				"canonical tool %q has no registered handler",
				meta.ToolName,
			)
		}
		registry.Register(meta, handler)
	}
	return nil
}
