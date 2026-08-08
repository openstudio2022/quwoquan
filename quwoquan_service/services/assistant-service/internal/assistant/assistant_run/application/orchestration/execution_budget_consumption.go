package orchestration

import (
	"context"
	"sync"
)

// ExecutionBudgetConsumption is the absolute, provider-neutral usage observed
// across the entire durable Run. It contains no prompt, model, account, or
// provider identity and is safe to persist in the Run-owned checkpoint.
type ExecutionBudgetConsumption struct {
	ToolCalls int64
	Tokens    int64
	CostUnits int64
}

type executionBudgetConsumptionSnapshot struct {
	Sequence    int64
	Consumption ExecutionBudgetConsumption
}

type executionBudgetConsumptionSink func(
	executionBudgetConsumptionSnapshot,
) error

type executionBudgetConsumptionState struct {
	mu               sync.Mutex
	sequence         int64
	consumption      ExecutionBudgetConsumption
	pendingToolCalls int64
	sink             executionBudgetConsumptionSink
	persistenceErr   error
}

type executionToolCallReservation struct {
	state     *executionBudgetConsumptionState
	committed bool
}

type executionBudgetConsumptionContextKey struct{}

func withExecutionBudgetConsumption(
	ctx context.Context,
	initial ExecutionBudgetConsumption,
	initialSequence int64,
	sink executionBudgetConsumptionSink,
) context.Context {
	if initialSequence < 0 {
		initialSequence = 0
	}
	return context.WithValue(
		ctx,
		executionBudgetConsumptionContextKey{},
		&executionBudgetConsumptionState{
			sequence:    initialSequence,
			consumption: initial,
			sink:        sink,
		},
	)
}

func executionBudgetConsumptionStateFromContext(
	ctx context.Context,
) (*executionBudgetConsumptionState, bool) {
	if ctx == nil {
		return nil, false
	}
	state, ok := ctx.Value(executionBudgetConsumptionContextKey{}).(*executionBudgetConsumptionState)
	return state, ok && state != nil
}

// AgentExecutionBudgetConsumptionFromContext returns the current absolute
// usage for tests and bounded observability. Callers receive a value copy and
// cannot mutate the in-flight budget authority.
func AgentExecutionBudgetConsumptionFromContext(
	ctx context.Context,
) (ExecutionBudgetConsumption, bool) {
	state, ok := executionBudgetConsumptionStateFromContext(ctx)
	if !ok {
		return ExecutionBudgetConsumption{}, false
	}
	state.mu.Lock()
	defer state.mu.Unlock()
	return state.consumption, true
}

func executionBudgetConsumptionPersistenceError(ctx context.Context) error {
	state, ok := executionBudgetConsumptionStateFromContext(ctx)
	if !ok {
		return nil
	}
	state.mu.Lock()
	defer state.mu.Unlock()
	return state.persistenceErr
}

func (state *executionBudgetConsumptionState) consumeModel(
	policy AgentExecutionPolicy,
	tokens int64,
	costUnits int64,
) error {
	if state == nil {
		return nil
	}
	if tokens < 0 {
		tokens = 0
	}
	if costUnits < 0 {
		costUnits = 0
	}
	state.mu.Lock()
	defer state.mu.Unlock()
	next := state.consumption
	next.Tokens += tokens
	next.CostUnits += costUnits
	if err := state.persistNext(next); err != nil {
		return err
	}
	if !policy.StopOnBudgetExhaustion {
		return nil
	}
	if next.Tokens > policy.MaxTokens {
		return ExecutionBudgetError{
			Dimension: "tokens",
			Limit:     policy.MaxTokens,
			Consumed:  next.Tokens,
		}
	}
	if next.CostUnits > policy.MaxCostUnits {
		return ExecutionBudgetError{
			Dimension: "cost_units",
			Limit:     policy.MaxCostUnits,
			Consumed:  next.CostUnits,
		}
	}
	return nil
}

func (state *executionBudgetConsumptionState) reserveToolCall(
	policy AgentExecutionPolicy,
) (*executionToolCallReservation, error) {
	if state == nil {
		return &executionToolCallReservation{}, nil
	}
	state.mu.Lock()
	defer state.mu.Unlock()
	nextToolCalls := state.consumption.ToolCalls + state.pendingToolCalls + 1
	if policy.StopOnBudgetExhaustion &&
		nextToolCalls > int64(policy.MaxToolCalls) {
		return nil, ExecutionBudgetError{
			Dimension: "tool_calls",
			Limit:     int64(policy.MaxToolCalls),
			Consumed:  nextToolCalls,
		}
	}
	state.pendingToolCalls++
	return &executionToolCallReservation{state: state}, nil
}

// Commit records one actual ToolExecutor invocation after it returns. The
// in-memory reservation prevents concurrent Subagents from overcommitting the
// global allowance without persisting a call that never happened.
func (reservation *executionToolCallReservation) Commit() error {
	if reservation == nil || reservation.state == nil || reservation.committed {
		return nil
	}
	state := reservation.state
	state.mu.Lock()
	defer state.mu.Unlock()
	if state.pendingToolCalls <= 0 {
		return ErrExecutionBudgetExhausted
	}
	next := state.consumption
	next.ToolCalls++
	if err := state.persistNext(next); err != nil {
		return err
	}
	state.pendingToolCalls--
	reservation.committed = true
	return nil
}

func (state *executionBudgetConsumptionState) persistNext(
	next ExecutionBudgetConsumption,
) error {
	snapshot := executionBudgetConsumptionSnapshot{
		Sequence:    state.sequence + 1,
		Consumption: next,
	}
	if state.sink != nil {
		if err := state.sink(snapshot); err != nil {
			if state.persistenceErr == nil {
				state.persistenceErr = err
			}
			return err
		}
	}
	state.sequence = snapshot.Sequence
	state.consumption = snapshot.Consumption
	return nil
}
