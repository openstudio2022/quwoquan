package streaming

import (
	"context"
	"net/http"
	"sync"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

// BudgetLimit names which declared stream bound closed a connection. It is the
// only distinction the transport can make about *why* a stream ended early, so
// error mapping, logs and metrics all key off it.
type BudgetLimit string

const (
	// BudgetLimitNone means no declared bound fired; the stream ended for its
	// own reason (terminal state, client disconnect, upstream cancellation).
	BudgetLimitNone BudgetLimit = ""
	// BudgetLimitHandshake means the connection was admitted but never
	// produced its first byte.
	BudgetLimitHandshake BudgetLimit = "handshake"
	// BudgetLimitIdle means the connection was open but the producer stopped
	// making progress. Keep-alive traffic does not count as progress.
	BudgetLimitIdle BudgetLimit = "idle"
	// BudgetLimitMaxDuration means the connection reached its declared
	// lifetime while still healthy. The client resumes from its last event.
	BudgetLimitMaxDuration BudgetLimit = "max_duration"
)

type budgetSignal int

const (
	budgetSignalHandshakeCompleted budgetSignal = iota
	budgetSignalFrameEmitted
)

// BudgetGuard enforces one operation's declared reliability.stream_budget on
// one live connection.
//
// The three bounds are enforced as two clocks. MaxDuration runs from admission
// and never restarts. The second clock is the handshake bound until the first
// byte is flushed and the idle bound afterwards, restarting on every payload
// frame. Keep-alive comments deliberately do not restart it: a stalled producer
// still emits heartbeats, so letting heartbeats count as progress would make
// the idle bound unable to fire at all — which is the exact failure this guard
// exists to catch.
type BudgetGuard struct {
	budget  rtauth.OperationStreamBudget
	ctx     context.Context
	cancel  context.CancelFunc
	signals chan budgetSignal
	mu      sync.Mutex
	limit   BudgetLimit
}

// NewBudgetGuard starts the clocks for one connection. The returned guard's
// context must be the context every read on the streaming path uses, otherwise
// a store call that hangs past the handshake bound keeps the connection alive
// regardless of the contract.
func NewBudgetGuard(
	parent context.Context,
	budget rtauth.OperationStreamBudget,
) *BudgetGuard {
	if budget.HandshakeMilliseconds <= 0 ||
		budget.IdleMilliseconds <= 0 ||
		budget.MaxDurationMilliseconds <= 0 {
		panic("stream budget must declare positive handshake, idle and max duration")
	}
	ctx, cancel := context.WithCancel(parent)
	guard := &BudgetGuard{
		budget:  budget,
		ctx:     ctx,
		cancel:  cancel,
		signals: make(chan budgetSignal, 16),
	}
	go guard.run()
	return guard
}

// Context is cancelled as soon as any declared bound fires, the caller stops
// the guard, or the parent request is cancelled.
func (guard *BudgetGuard) Context() context.Context {
	return guard.ctx
}

// Done mirrors Context().Done() for use directly in a stream select.
func (guard *BudgetGuard) Done() <-chan struct{} {
	return guard.ctx.Done()
}

// HandshakeCompleted records that the first byte of the stream reached the
// client. The handshake bound stops here and the idle bound takes over.
func (guard *BudgetGuard) HandshakeCompleted() {
	guard.signal(budgetSignalHandshakeCompleted)
}

// FrameEmitted records one payload frame, restarting the idle bound. Callers
// must not report keep-alive comments here.
func (guard *BudgetGuard) FrameEmitted() {
	guard.signal(budgetSignalFrameEmitted)
}

// Limit reports which declared bound closed the connection, or
// BudgetLimitNone when the stream ended for its own reason.
func (guard *BudgetGuard) Limit() BudgetLimit {
	guard.mu.Lock()
	defer guard.mu.Unlock()
	return guard.limit
}

// Stop releases the clocks. It is safe to call more than once.
func (guard *BudgetGuard) Stop() {
	guard.cancel()
}

func (guard *BudgetGuard) signal(value budgetSignal) {
	select {
	case guard.signals <- value:
	default:
	}
}

func (guard *BudgetGuard) run() {
	lifetime := time.NewTimer(guard.budget.MaxDuration())
	defer lifetime.Stop()
	progress := time.NewTimer(guard.budget.Handshake())
	defer progress.Stop()
	handshakeCompleted := false
	for {
		select {
		case <-guard.ctx.Done():
			return
		case <-lifetime.C:
			guard.trip(BudgetLimitMaxDuration)
			return
		case <-progress.C:
			if handshakeCompleted {
				guard.trip(BudgetLimitIdle)
			} else {
				guard.trip(BudgetLimitHandshake)
			}
			return
		case <-guard.signals:
			handshakeCompleted = true
			restartTimer(progress, guard.budget.Idle())
		}
	}
}

func (guard *BudgetGuard) trip(limit BudgetLimit) {
	guard.mu.Lock()
	if guard.limit == BudgetLimitNone {
		guard.limit = limit
	}
	guard.mu.Unlock()
	guard.cancel()
}

func restartTimer(timer *time.Timer, duration time.Duration) {
	if !timer.Stop() {
		select {
		case <-timer.C:
		default:
		}
	}
	timer.Reset(duration)
}

// ReleaseTransportWriteDeadline hands the connection's time budget over to the
// operation contract.
//
// http.Server.WriteTimeout is applied once per connection and is never
// refreshed per flush, so any stream that outlives it is cut by the transport
// rather than by its declared stream budget — the same "hand-written value
// wins over the contract" shape that a literal WriteTimeout produces. Clearing
// the deadline is only safe because BudgetGuard then owns all three bounds.
func ReleaseTransportWriteDeadline(w http.ResponseWriter) error {
	return http.NewResponseController(w).SetWriteDeadline(time.Time{})
}
