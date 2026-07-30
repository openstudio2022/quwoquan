package tool

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
)

type Request struct {
	ToolName string
	Input    map[string]any
	History  []string
}

type Result struct {
	Output map[string]any
}

type Handler func(context.Context, Request) (Result, error)

// RetryableFailure 由 handler 返回的错误可选实现，用于声明该失败是否值得在同一轮内重试。
// 未实现该接口的错误按不可重试处理，避免把契约错误当成瞬时抖动反复打上游。
type RetryableFailure interface {
	RetryableToolFailure() bool
}

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
	return meta, ok
}

func (r Registry) ValidateInput(toolName string, input map[string]any) error {
	meta, ok := r.Metadata(toolName)
	if !ok {
		return fmt.Errorf("tool %q is not registered", toolName)
	}
	return validateKeys(input, meta.RequiredInputKeys(), "input")
}

func (r *Registry) Register(meta Metadata, handler Handler) {
	if r.metadata == nil {
		r.metadata = map[string]Metadata{}
	}
	if r.handlers == nil {
		r.handlers = map[string]Handler{}
	}
	r.metadata[meta.ToolName] = meta
	r.handlers[meta.ToolName] = handler
}

func (r Registry) Execute(ctx context.Context, req Request) (Result, error) {
	meta, ok := r.metadata[req.ToolName]
	if !ok {
		return Result{}, fmt.Errorf("tool %q is not registered", req.ToolName)
	}
	if err := validateKeys(req.Input, meta.RequiredInputKeys(), "input"); err != nil {
		return Result{}, err
	}
	if err := detectLoop(req.ToolName, req.History, meta.Resilience.LoopDetectionWindow); err != nil {
		return Result{}, err
	}
	handler, ok := r.handlers[req.ToolName]
	if !ok {
		return Result{}, fmt.Errorf("tool %q has no handler", req.ToolName)
	}
	attempts := meta.Resilience.MaxAttempts
	if attempts <= 0 {
		attempts = 1
	}
	var lastErr error
	for attempt := 1; attempt <= attempts; attempt++ {
		result, err := invokeWithTimeout(ctx, handler, req, meta.Resilience.TimeoutMs)
		if err == nil {
			if err := validateKeys(result.Output, meta.RequiredOutputKeys(), "output"); err != nil {
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
		Attempts: attempts,
		Recovery: meta.Recovery,
		Cause:    lastErr,
	}
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
