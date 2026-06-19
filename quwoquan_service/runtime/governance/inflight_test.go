package runtimegovernance

import (
	"sync"
	"testing"
)

func TestInflightLimiterShedsAtCapacity(t *testing.T) {
	l := NewInflightLimiter(2)

	if !l.Acquire() || !l.Acquire() {
		t.Fatalf("expected first two Acquire to succeed")
	}
	if l.Inflight() != 2 {
		t.Fatalf("Inflight()=%d, want 2", l.Inflight())
	}
	if l.Acquire() {
		t.Fatalf("expected third Acquire to be shed (false) at capacity")
	}

	l.Release()
	if l.Inflight() != 1 {
		t.Fatalf("Inflight()=%d after release, want 1", l.Inflight())
	}
	if !l.Acquire() {
		t.Fatalf("expected Acquire to succeed after a Release freed a slot")
	}
}

func TestInflightLimiterClampsNonPositiveMax(t *testing.T) {
	l := NewInflightLimiter(0)
	if l.Max() != 1 {
		t.Fatalf("Max()=%d, want clamp to 1", l.Max())
	}
	if !l.Acquire() {
		t.Fatalf("expected one slot available on clamped limiter")
	}
	if l.Acquire() {
		t.Fatalf("expected second Acquire shed on clamped (max=1) limiter")
	}
}

// TestInflightLimiterConcurrentNeverExceedsMax hammers the limiter from many
// goroutines and asserts the held count never crosses the ceiling — the core
// backpressure invariant.
func TestInflightLimiterConcurrentNeverExceedsMax(t *testing.T) {
	const max = 8
	l := NewInflightLimiter(max)

	var wg sync.WaitGroup
	for i := 0; i < 200; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if l.Acquire() {
				if got := l.Inflight(); got > max {
					t.Errorf("Inflight()=%d exceeded max=%d", got, max)
				}
				l.Release()
			}
		}()
	}
	wg.Wait()

	if l.Inflight() != 0 {
		t.Fatalf("Inflight()=%d after all released, want 0", l.Inflight())
	}
}
