package runtimegovernance

import (
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
