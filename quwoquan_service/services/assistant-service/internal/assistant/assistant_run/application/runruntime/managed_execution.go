package runruntime

import (
	"context"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
)

// ManagedRunExecutor fences one active AgentLoop per Run and exposes that
// execution to the cancellation coordinator. Cancelling the managed execution
// cancels the parent AgentLoop context, which in turn cancels its bounded tool
// and subagent work before the Run is allowed to become terminal.
type ManagedRunExecutor struct {
	delegate RunExecutor

	mu     sync.Mutex
	active map[string]*managedExecution
	fenced map[string]bool
}

func NewManagedRunExecutor(delegate RunExecutor) *ManagedRunExecutor {
	if delegate == nil {
		panic("assistant managed run executor delegate is required")
	}
	return &ManagedRunExecutor{
		delegate: delegate,
		active:   map[string]*managedExecution{},
		fenced:   map[string]bool{},
	}
}

// VerifiesCompletionWithinExecutionBudget preserves the delegate's production
// completion-verification marker across the execution fencing wrapper.
func (m *ManagedRunExecutor) VerifiesCompletionWithinExecutionBudget() bool {
	if m == nil || m.delegate == nil {
		return false
	}
	verifier, ok := m.delegate.(InExecutionCompletionVerifier)
	return ok && verifier.VerifiesCompletionWithinExecutionBudget()
}

func (m *ManagedRunExecutor) Execute(
	ctx context.Context,
	request ExecutionRequest,
	emit func(ExecutionItemUpdate) error,
) (ExecutionResult, error) {
	if m == nil || m.delegate == nil || strings.TrimSpace(request.RunID) == "" {
		return ExecutionResult{}, ErrInvalidRun
	}
	executionCtx, cancel := context.WithCancel(ctx)
	execution := &managedExecution{
		runID:  strings.TrimSpace(request.RunID),
		cancel: cancel,
		done:   make(chan struct{}),
	}
	m.mu.Lock()
	if m.fenced[execution.runID] || m.active[execution.runID] != nil {
		m.mu.Unlock()
		cancel()
		return ExecutionResult{}, ErrExecutionFenced
	}
	m.active[execution.runID] = execution
	m.mu.Unlock()

	result, err := m.delegate.Execute(executionCtx, request, emit)
	m.mu.Lock()
	delete(m.active, execution.runID)
	close(execution.done)
	cancelled := execution.cancelled.Load()
	m.mu.Unlock()
	cancel()
	if cancelled && (err == nil || errors.Is(err, context.Canceled)) {
		return ExecutionResult{}, ErrExecutionCancelled
	}
	return result, err
}

func (m *ManagedRunExecutor) FenceAndList(
	_ context.Context,
	runID string,
) ([]ChildExecution, error) {
	if m == nil {
		return nil, ErrInvalidRun
	}
	runID = strings.TrimSpace(runID)
	if runID == "" {
		return nil, ErrInvalidRun
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.fenced[runID] = true
	if execution := m.active[runID]; execution != nil {
		return []ChildExecution{execution}, nil
	}
	return nil, nil
}

type managedExecution struct {
	runID     string
	cancel    context.CancelFunc
	done      chan struct{}
	cancelled atomic.Bool
	once      sync.Once
}

func (e *managedExecution) ExecutionID() string { return e.runID }

func (e *managedExecution) Kind() ChildExecutionKind { return ChildSubagent }

func (e *managedExecution) Cancel(context.Context) error {
	e.once.Do(func() {
		e.cancelled.Store(true)
		e.cancel()
	})
	return nil
}

func (e *managedExecution) AwaitStopped(ctx context.Context) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-e.done:
		return nil
	}
}

var (
	_ RunExecutor                   = (*ManagedRunExecutor)(nil)
	_ InExecutionCompletionVerifier = (*ManagedRunExecutor)(nil)
	_ ChildExecutionRegistry        = (*ManagedRunExecutor)(nil)
	_ ChildExecution                = (*managedExecution)(nil)
)
