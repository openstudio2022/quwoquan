package runtimegovernance

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"testing"
	"time"
)

func logger() *slog.Logger {
	return slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelWarn}))
}

func TestCircuitBreaker_ClosedAllows(t *testing.T) {
	cb := NewCircuitBreaker(3, time.Second, logger())
	if !cb.Allow() {
		t.Error("closed circuit should allow")
	}
}

func TestCircuitBreaker_OpensAfterThreshold(t *testing.T) {
	cb := NewCircuitBreaker(3, time.Second, logger())
	cb.RecordFailure()
	cb.RecordFailure()
	cb.RecordFailure()

	if cb.Allow() {
		t.Error("circuit should be open after 3 failures")
	}
}

func TestCircuitBreaker_HalfOpenAfterTimeout(t *testing.T) {
	cb := NewCircuitBreaker(2, 50*time.Millisecond, logger())
	cb.RecordFailure()
	cb.RecordFailure()

	if cb.Allow() {
		t.Error("should be open immediately after failures")
	}

	time.Sleep(60 * time.Millisecond)

	if !cb.Allow() {
		t.Error("should be half-open after reset timeout")
	}
}

func TestCircuitBreaker_ClosesOnSuccess(t *testing.T) {
	cb := NewCircuitBreaker(1, 50*time.Millisecond, logger())
	cb.RecordFailure()

	time.Sleep(60 * time.Millisecond)
	cb.Allow() // triggers half-open
	cb.RecordSuccess()

	if !cb.Allow() {
		t.Error("should be closed after success in half-open")
	}
}

func TestRateLimiter_AllowsWithinLimit(t *testing.T) {
	rl := NewRateLimiter(5)
	for i := 0; i < 5; i++ {
		if !rl.Allow() {
			t.Errorf("should allow request %d within limit", i)
		}
	}
}

func TestRateLimiter_DeniesOverLimit(t *testing.T) {
	rl := NewRateLimiter(2)
	rl.Allow()
	rl.Allow()
	if rl.Allow() {
		t.Error("should deny third request with limit=2")
	}
}

func TestRateLimiter_RefillsOverTime(t *testing.T) {
	rl := NewRateLimiter(1)
	rl.Allow()
	if rl.Allow() {
		t.Error("should deny immediately")
	}
	time.Sleep(1100 * time.Millisecond)
	if !rl.Allow() {
		t.Error("should allow after refill")
	}
}

func TestRetry_SucceedsFirstTry(t *testing.T) {
	called := 0
	err := Retry(context.Background(), ResiliencePolicy{RetryMaxAttempts: 3}, func(_ context.Context) error {
		called++
		return nil
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if called != 1 {
		t.Errorf("expected 1 call, got %d", called)
	}
}

func TestRetry_SucceedsOnRetry(t *testing.T) {
	called := 0
	err := Retry(context.Background(), ResiliencePolicy{RetryMaxAttempts: 3, RetryBackoffMs: 10}, func(_ context.Context) error {
		called++
		if called < 3 {
			return errors.New("transient")
		}
		return nil
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if called != 3 {
		t.Errorf("expected 3 calls, got %d", called)
	}
}

func TestRetry_ExhaustsAttempts(t *testing.T) {
	called := 0
	err := Retry(context.Background(), ResiliencePolicy{RetryMaxAttempts: 2, RetryBackoffMs: 10}, func(_ context.Context) error {
		called++
		return errors.New("persistent")
	})
	if err == nil {
		t.Fatal("expected error after retries exhausted")
	}
	if called != 3 { // initial + 2 retries
		t.Errorf("expected 3 calls, got %d", called)
	}
}

func TestRetry_RespectsContextCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := Retry(ctx, ResiliencePolicy{RetryMaxAttempts: 5, RetryBackoffMs: 100}, func(ctx context.Context) error {
		return errors.New("fail")
	})
	if err == nil {
		t.Fatal("expected error from cancelled context")
	}
}

func TestStaticPolicyProvider(t *testing.T) {
	p := StaticPolicyProvider{Value: ResiliencePolicy{TimeoutMs: 500, RetryMaxAttempts: 2}}
	policy, err := p.Policy(context.Background(), "any_key")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if policy.TimeoutMs != 500 {
		t.Errorf("timeout: got %d, want 500", policy.TimeoutMs)
	}
}
