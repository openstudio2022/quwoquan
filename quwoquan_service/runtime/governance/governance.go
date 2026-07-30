package runtimegovernance

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"sync/atomic"
	"time"
)

// ResiliencePolicy defines runtime-governance baseline controls.
type ResiliencePolicy struct {
	TimeoutMs             int
	RetryMaxAttempts      int
	RetryBackoffMs        int
	CircuitBreakerEnabled bool
	DegradeEnabled        bool
}

// PolicyProvider resolves governance policy from runtime config.
type PolicyProvider interface {
	Policy(ctx context.Context, key string) (ResiliencePolicy, error)
}

// StaticPolicyProvider returns the same policy for all keys.
type StaticPolicyProvider struct {
	Value ResiliencePolicy
}

func (p StaticPolicyProvider) Policy(_ context.Context, _ string) (ResiliencePolicy, error) {
	return p.Value, nil
}

// CircuitBreaker implements a simple three-state circuit breaker.
type CircuitBreaker struct {
	mu            sync.Mutex
	state         CircuitState
	failureCount  int
	threshold     int
	resetTimeout  time.Duration
	lastFailureAt time.Time
	logger        *slog.Logger
}

type CircuitState int

const (
	StateClosed CircuitState = iota
	StateOpen
	StateHalfOpen
)

func (s CircuitState) String() string {
	switch s {
	case StateClosed:
		return "closed"
	case StateOpen:
		return "open"
	case StateHalfOpen:
		return "half-open"
	default:
		return "unknown"
	}
}

func NewCircuitBreaker(threshold int, resetTimeout time.Duration, logger *slog.Logger) *CircuitBreaker {
	return &CircuitBreaker{
		state:        StateClosed,
		threshold:    threshold,
		resetTimeout: resetTimeout,
		logger:       logger,
	}
}

// Allow checks if the request should proceed.
func (cb *CircuitBreaker) Allow() bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	switch cb.state {
	case StateClosed:
		return true
	case StateOpen:
		if time.Since(cb.lastFailureAt) > cb.resetTimeout {
			cb.state = StateHalfOpen
			cb.logger.Info("circuit breaker: open -> half-open")
			return true
		}
		return false
	case StateHalfOpen:
		return true
	default:
		return true
	}
}

// RecordSuccess records a successful call.
func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if cb.state == StateHalfOpen {
		cb.state = StateClosed
		cb.failureCount = 0
		cb.logger.Info("circuit breaker: half-open -> closed")
	}
}

// RecordFailure records a failed call.
func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	cb.failureCount++
	cb.lastFailureAt = time.Now()

	if cb.failureCount >= cb.threshold {
		cb.state = StateOpen
		cb.logger.Warn("circuit breaker: closed -> open",
			slog.Int("failures", cb.failureCount),
			slog.Int("threshold", cb.threshold))
	}
}

// InflightLimiter bounds the number of concurrently in-flight operations. It is
// an owner resource backpressure primitive, not a business arrival quota. Under
// a slow downstream (e.g. ES), in-flight requests can pile up and exhaust
// goroutines / connection pools / search thread pools even when api-edge arrival
// quota is healthy. It is non-blocking by design so the owner sheds load instead
// of queueing unboundedly.
type InflightLimiter struct {
	sem chan struct{}
	max int
	cur int64
}

// NewInflightLimiter builds a limiter allowing at most max concurrent holders.
// A non-positive max is clamped to 1 (never an unbounded/zero-capacity limiter).
func NewInflightLimiter(max int) *InflightLimiter {
	if max <= 0 {
		max = 1
	}
	return &InflightLimiter{sem: make(chan struct{}, max), max: max}
}

// Acquire reserves a slot without blocking. It returns false when the limiter is
// already at capacity so the caller can shed load immediately.
func (l *InflightLimiter) Acquire() bool {
	select {
	case l.sem <- struct{}{}:
		atomic.AddInt64(&l.cur, 1)
		return true
	default:
		return false
	}
}

// Release frees a slot previously taken by a successful Acquire. It is safe to
// call only after Acquire returned true (each Release pairs one Acquire).
func (l *InflightLimiter) Release() {
	select {
	case <-l.sem:
		atomic.AddInt64(&l.cur, -1)
	default:
	}
}

// Inflight reports the current number of held slots (observability gauge source).
func (l *InflightLimiter) Inflight() int { return int(atomic.LoadInt64(&l.cur)) }

// Max reports the configured concurrency ceiling.
func (l *InflightLimiter) Max() int { return l.max }

// Retry executes fn with retry logic based on policy.
func Retry(ctx context.Context, policy ResiliencePolicy, fn func(ctx context.Context) error) error {
	var lastErr error
	for attempt := 0; attempt <= policy.RetryMaxAttempts; attempt++ {
		if attempt > 0 && policy.RetryBackoffMs > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(time.Duration(policy.RetryBackoffMs*attempt) * time.Millisecond):
			}
		}

		timeoutCtx := ctx
		if policy.TimeoutMs > 0 {
			var cancel context.CancelFunc
			timeoutCtx, cancel = context.WithTimeout(ctx, time.Duration(policy.TimeoutMs)*time.Millisecond)
			defer cancel()
		}

		lastErr = fn(timeoutCtx)
		if lastErr == nil {
			return nil
		}
	}
	return fmt.Errorf("after %d retries: %w", policy.RetryMaxAttempts, lastErr)
}
