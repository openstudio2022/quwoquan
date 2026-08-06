// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-005
package streaming

import (
	"context"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

// scaledStreamBudget keeps the three bounds in the same order as a real
// contract (handshake < idle < max_duration) while staying fast enough for a
// local_contract test. The production values come from the generated
// descriptor; only the magnitudes are scaled here.
func scaledStreamBudget() rtauth.OperationStreamBudget {
	return rtauth.OperationStreamBudget{
		HandshakeMilliseconds:   40,
		IdleMilliseconds:        120,
		MaxDurationMilliseconds: 2000,
	}
}

func awaitBudgetLimit(
	t *testing.T,
	guard *BudgetGuard,
	within time.Duration,
) BudgetLimit {
	t.Helper()
	select {
	case <-guard.Done():
		return guard.Limit()
	case <-time.After(within):
		t.Fatalf("stream budget never closed the connection within %s", within)
		return BudgetLimitNone
	}
}

// A connection that is admitted but never produces its first byte must be
// closed by the handshake bound, not by the connection lifetime.
func TestStreamBudgetClosesConnectionThatNeverFlushesFirstByte(t *testing.T) {
	t.Parallel()

	guard := NewBudgetGuard(context.Background(), scaledStreamBudget())
	defer guard.Stop()

	started := time.Now()
	if limit := awaitBudgetLimit(t, guard, time.Second); limit != BudgetLimitHandshake {
		t.Fatalf("limit=%q want %q", limit, BudgetLimitHandshake)
	}
	if elapsed := time.Since(started); elapsed >= 120*time.Millisecond {
		t.Fatalf("handshake bound waited %s, i.e. the idle bound fired instead", elapsed)
	}
}

// Once the stream is live, a producer that stops making progress must be closed
// by the idle bound well before the connection lifetime expires.
func TestStreamBudgetClosesLiveConnectionWithoutProgress(t *testing.T) {
	t.Parallel()

	guard := NewBudgetGuard(context.Background(), scaledStreamBudget())
	defer guard.Stop()
	guard.HandshakeCompleted()

	started := time.Now()
	if limit := awaitBudgetLimit(t, guard, time.Second); limit != BudgetLimitIdle {
		t.Fatalf("limit=%q want %q", limit, BudgetLimitIdle)
	}
	elapsed := time.Since(started)
	if elapsed < 100*time.Millisecond {
		t.Fatalf("idle bound fired after %s, i.e. the handshake bound leaked past first byte", elapsed)
	}
	if elapsed >= 2*time.Second {
		t.Fatalf("idle bound waited %s, i.e. the connection lifetime fired instead", elapsed)
	}
}

// This is the bound that is easiest to get wrong: a healthy long-running
// producer must never be mistaken for a stalled one. Payload frames arriving
// faster than the idle bound keep restarting it, so the connection survives
// many idle windows and is finally closed by its declared lifetime.
func TestStreamBudgetKeepsHealthyLongConnectionAliveUntilLifetime(t *testing.T) {
	t.Parallel()

	budget := scaledStreamBudget()
	guard := NewBudgetGuard(context.Background(), budget)
	defer guard.Stop()
	guard.HandshakeCompleted()

	frames := 0
	ticker := time.NewTicker(budget.Idle() / 3)
	defer ticker.Stop()
	started := time.Now()
	for open := true; open; {
		select {
		case <-guard.Done():
			open = false
		case <-ticker.C:
			guard.FrameEmitted()
			frames++
		}
	}
	elapsed := time.Since(started)
	if limit := guard.Limit(); limit != BudgetLimitMaxDuration {
		t.Fatalf(
			"limit=%q want %q after %d frames in %s: a progressing stream was treated as idle",
			limit,
			BudgetLimitMaxDuration,
			frames,
			elapsed,
		)
	}
	// Surviving several idle windows is the actual discrimination being proven.
	if elapsed < 4*budget.Idle() {
		t.Fatalf("progressing stream only survived %s (idle bound %s)", elapsed, budget.Idle())
	}
	if frames < 4 {
		t.Fatalf("frames=%d is too few to prove the idle bound restarted", frames)
	}
}

// Keep-alive traffic must not count as progress. A stalled producer still emits
// heartbeats, so a guard that accepted them could never fire the idle bound.
func TestStreamBudgetIgnoresKeepAliveTrafficForIdleProgress(t *testing.T) {
	t.Parallel()

	budget := scaledStreamBudget()
	guard := NewBudgetGuard(context.Background(), budget)
	defer guard.Stop()
	guard.HandshakeCompleted()

	// A heartbeat is written straight to the wire and is deliberately not
	// reported to the guard; nothing here may restart the idle bound.
	heartbeats := 0
	ticker := time.NewTicker(budget.Idle() / 3)
	defer ticker.Stop()
	for open := true; open; {
		select {
		case <-guard.Done():
			open = false
		case <-ticker.C:
			heartbeats++
		}
	}
	if limit := guard.Limit(); limit != BudgetLimitIdle {
		t.Fatalf(
			"limit=%q want %q after %d heartbeats: keep-alive traffic was mistaken for progress",
			limit,
			BudgetLimitIdle,
			heartbeats,
		)
	}
}

// A healthy stream still has a ceiling: the client resumes from its last event
// rather than holding one connection forever.
func TestStreamBudgetClosesHealthyConnectionAtDeclaredLifetime(t *testing.T) {
	t.Parallel()

	budget := rtauth.OperationStreamBudget{
		HandshakeMilliseconds:   40,
		IdleMilliseconds:        400,
		MaxDurationMilliseconds: 150,
	}
	guard := NewBudgetGuard(context.Background(), budget)
	defer guard.Stop()
	guard.HandshakeCompleted()
	guard.FrameEmitted()

	if limit := awaitBudgetLimit(t, guard, time.Second); limit != BudgetLimitMaxDuration {
		t.Fatalf("limit=%q want %q", limit, BudgetLimitMaxDuration)
	}
}

// A client that disconnects, or an upstream deadline, is not a budget
// violation. Reporting it as one would attribute a normal close to the
// contract.
func TestStreamBudgetReportsNoLimitWhenParentEnds(t *testing.T) {
	t.Parallel()

	parent, cancel := context.WithCancel(context.Background())
	guard := NewBudgetGuard(parent, scaledStreamBudget())
	defer guard.Stop()
	guard.HandshakeCompleted()
	guard.FrameEmitted()
	cancel()

	select {
	case <-guard.Done():
	case <-time.After(time.Second):
		t.Fatal("guard ignored parent cancellation")
	}
	if limit := guard.Limit(); limit != BudgetLimitNone {
		t.Fatalf("limit=%q want no declared bound", limit)
	}
}

// A budget with a missing bound must fail at wiring time. Silently treating a
// zero as "unbounded" is how the permanent hang comes back.
func TestStreamBudgetRejectsIncompleteBudget(t *testing.T) {
	t.Parallel()

	for name, budget := range map[string]rtauth.OperationStreamBudget{
		"missing handshake":    {IdleMilliseconds: 10, MaxDurationMilliseconds: 20},
		"missing idle":         {HandshakeMilliseconds: 10, MaxDurationMilliseconds: 20},
		"missing max duration": {HandshakeMilliseconds: 10, IdleMilliseconds: 20},
	} {
		t.Run(name, func(t *testing.T) {
			defer func() {
				if recover() == nil {
					t.Fatal("incomplete stream budget must fail closed")
				}
			}()
			NewBudgetGuard(context.Background(), budget)
		})
	}
}
