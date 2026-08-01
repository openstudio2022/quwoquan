package publicweb

import (
	"context"
	"fmt"
	"sync"
)

type RunBudgetLimits struct {
	MaxPages int
	MaxBytes int64
}

type RunBudgetSnapshot struct {
	UsedPages    int
	ReservedPage int
	UsedBytes    int64
	ReservedByte int64
}

// RunBudgetGate enforces per-run page and byte limits, including concurrent
// reservations. Durable workers should reconstruct it from the canonical
// checkpoint and persist Snapshot changes at each safe boundary.
type RunBudgetGate struct {
	mu           sync.Mutex
	limits       RunBudgetLimits
	runs         map[string]*runBudgetState
	reservations map[uint64]*runBudgetReservation
	nextID       uint64
}

type runBudgetState struct {
	usedPages    int
	reservedPage int
	usedBytes    int64
	reservedByte int64
}

func NewRunBudgetGate(limits RunBudgetLimits) *RunBudgetGate {
	if limits.MaxPages <= 0 || limits.MaxBytes <= 0 {
		panic("public web run budget limits must be positive")
	}
	return &RunBudgetGate{
		limits:       limits,
		runs:         map[string]*runBudgetState{},
		reservations: map[uint64]*runBudgetReservation{},
	}
}

func (g *RunBudgetGate) ReserveFetch(
	_ context.Context,
	runID string,
	requestedBytes int64,
) (BudgetReservation, error) {
	if requestedBytes <= 0 {
		return nil, ErrBudgetExhausted
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	state := g.runs[runID]
	if state == nil {
		state = &runBudgetState{}
		g.runs[runID] = state
	}
	if state.usedPages+state.reservedPage >= g.limits.MaxPages {
		return nil, ErrBudgetExhausted
	}
	remaining := g.limits.MaxBytes - state.usedBytes - state.reservedByte
	if remaining <= 0 {
		return nil, ErrBudgetExhausted
	}
	if requestedBytes < remaining {
		remaining = requestedBytes
	}
	g.nextID++
	reservation := &runBudgetReservation{
		owner:   g,
		id:      g.nextID,
		runID:   runID,
		allowed: remaining,
	}
	g.reservations[reservation.id] = reservation
	state.reservedPage++
	state.reservedByte += remaining
	return reservation, nil
}

func (g *RunBudgetGate) Snapshot(runID string) RunBudgetSnapshot {
	g.mu.Lock()
	defer g.mu.Unlock()
	state := g.runs[runID]
	if state == nil {
		return RunBudgetSnapshot{}
	}
	return RunBudgetSnapshot{
		UsedPages:    state.usedPages,
		ReservedPage: state.reservedPage,
		UsedBytes:    state.usedBytes,
		ReservedByte: state.reservedByte,
	}
}

type runBudgetReservation struct {
	owner   *RunBudgetGate
	id      uint64
	runID   string
	allowed int64
	done    bool
}

func (r *runBudgetReservation) AllowedBytes() int64 { return r.allowed }

func (r *runBudgetReservation) Commit(actualBytes int64) error {
	if actualBytes < 0 || actualBytes > r.allowed {
		return fmt.Errorf("%w: actual bytes exceed reservation", ErrBudgetExhausted)
	}
	r.owner.mu.Lock()
	defer r.owner.mu.Unlock()
	if r.done {
		return ErrBudgetExhausted
	}
	state := r.owner.runs[r.runID]
	if state == nil || r.owner.reservations[r.id] != r {
		return ErrBudgetExhausted
	}
	state.reservedPage--
	state.reservedByte -= r.allowed
	state.usedPages++
	state.usedBytes += actualBytes
	delete(r.owner.reservations, r.id)
	r.done = true
	return nil
}

func (r *runBudgetReservation) Release() {
	r.owner.mu.Lock()
	defer r.owner.mu.Unlock()
	if r.done {
		return
	}
	state := r.owner.runs[r.runID]
	if state != nil && r.owner.reservations[r.id] == r {
		state.reservedPage--
		state.reservedByte -= r.allowed
		delete(r.owner.reservations, r.id)
	}
	r.done = true
}
