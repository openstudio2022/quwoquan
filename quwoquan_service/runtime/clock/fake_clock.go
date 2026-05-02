package clock

import (
	"sync"
	"time"
)

type FixedClock struct {
	now time.Time
}

func NewFixed(t time.Time) FixedClock {
	return FixedClock{now: t.UTC()}
}

func (c FixedClock) Now() time.Time {
	return c.now
}

type FakeClock struct {
	mu  sync.RWMutex
	now time.Time
}

func NewFake(t time.Time) *FakeClock {
	return &FakeClock{now: t.UTC()}
}

func NewFakeClock(t time.Time) *FakeClock {
	return NewFake(t)
}

func (c *FakeClock) Now() time.Time {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.now
}

func (c *FakeClock) Set(t time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = t.UTC()
}

func (c *FakeClock) Advance(d time.Duration) time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = c.now.Add(d).UTC()
	return c.now
}
