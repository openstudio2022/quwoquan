package clock

import (
	"testing"
	"time"
)

func TestFixedClock(t *testing.T) {
	now := time.Date(2026, 4, 29, 2, 0, 0, 0, time.FixedZone("CST", 8*3600))
	c := NewFixed(now)
	if got := c.Now(); !got.Equal(now.UTC()) {
		t.Fatalf("Now() = %s, want %s", got, now.UTC())
	}
}

func TestFakeClockAdvanceAndSet(t *testing.T) {
	start := time.Date(2026, 4, 29, 2, 0, 0, 0, time.UTC)
	c := NewFake(start)
	if got := c.Advance(90 * time.Second); !got.Equal(start.Add(90 * time.Second)) {
		t.Fatalf("Advance() = %s", got)
	}
	next := start.Add(3 * time.Hour)
	c.Set(next)
	if got := c.Now(); !got.Equal(next) {
		t.Fatalf("Now() = %s, want %s", got, next)
	}
}

func TestSinceUntilUseClock(t *testing.T) {
	now := time.Date(2026, 4, 29, 2, 0, 0, 0, time.UTC)
	c := NewFixed(now)
	if got := Since(c, now.Add(-time.Minute)); got != time.Minute {
		t.Fatalf("Since() = %s", got)
	}
	if got := Until(c, now.Add(2*time.Minute)); got != 2*time.Minute {
		t.Fatalf("Until() = %s", got)
	}
}
