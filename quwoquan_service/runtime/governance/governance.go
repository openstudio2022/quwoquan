package runtimegovernance

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"
)

// ResiliencePolicy defines runtime-governance baseline controls.
type ResiliencePolicy struct {
	TimeoutMs             int
	RetryMaxAttempts      int
	RetryBackoffMs        int
	CircuitBreakerEnabled bool
	RateLimitPerSecond    int
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
	StateClosed   CircuitState = iota
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

// RateLimiter implements a simple token-bucket rate limiter.
type RateLimiter struct {
	mu       sync.Mutex
	tokens   int
	capacity int
	rate     int
	lastFill time.Time
}

func NewRateLimiter(ratePerSecond int) *RateLimiter {
	return &RateLimiter{
		tokens:   ratePerSecond,
		capacity: ratePerSecond,
		rate:     ratePerSecond,
		lastFill: time.Now(),
	}
}

// Allow returns true if the request is within rate limit.
func (rl *RateLimiter) Allow() bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	rl.refill()
	if rl.tokens > 0 {
		rl.tokens--
		return true
	}
	return false
}

func (rl *RateLimiter) refill() {
	now := time.Now()
	elapsed := now.Sub(rl.lastFill)
	newTokens := int(elapsed.Seconds()) * rl.rate
	if newTokens > 0 {
		rl.tokens += newTokens
		if rl.tokens > rl.capacity {
			rl.tokens = rl.capacity
		}
		rl.lastFill = now
	}
}

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
