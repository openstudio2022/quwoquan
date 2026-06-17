package application

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/services/search-service/internal/application/queryheat"
)

type countingTermHeat struct {
	calls atomic.Int64
	terms []queryheat.TermHeat
	err   error
}

func (c *countingTermHeat) RelatedTerms(_ context.Context, _ string, _ int) ([]queryheat.TermHeat, error) {
	c.calls.Add(1)
	return c.terms, c.err
}

func TestCachedTermHeatServesHitWithinTTL(t *testing.T) {
	inner := &countingTermHeat{terms: []queryheat.TermHeat{{NormalizedTerm: "火锅", Relevance: 9}}}
	now := time.Unix(0, 0)
	c := NewCachedTermHeat(inner, time.Second, 16)
	c.now = func() time.Time { return now }

	for i := 0; i < 5; i++ {
		got, err := c.RelatedTerms(context.Background(), "成都", 8)
		if err != nil {
			t.Fatalf("unexpected err: %v", err)
		}
		if len(got) != 1 || got[0].NormalizedTerm != "火锅" {
			t.Fatalf("unexpected heats: %+v", got)
		}
	}
	if inner.calls.Load() != 1 {
		t.Fatalf("inner calls=%d, want 1 (4 served from cache)", inner.calls.Load())
	}
}

func TestCachedTermHeatRefetchesAfterTTL(t *testing.T) {
	inner := &countingTermHeat{terms: []queryheat.TermHeat{{NormalizedTerm: "火锅", Relevance: 9}}}
	now := time.Unix(0, 0)
	c := NewCachedTermHeat(inner, time.Second, 16)
	c.now = func() time.Time { return now }

	if _, err := c.RelatedTerms(context.Background(), "成都", 8); err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	now = now.Add(1100 * time.Millisecond) // past TTL
	if _, err := c.RelatedTerms(context.Background(), "成都", 8); err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if inner.calls.Load() != 2 {
		t.Fatalf("inner calls=%d, want 2 (cache expired)", inner.calls.Load())
	}
}

// Errors must pass through and must NOT be cached, so a transient Mongo failure
// is not pinned for the whole TTL window.
func TestCachedTermHeatDoesNotCacheErrors(t *testing.T) {
	inner := &countingTermHeat{err: errors.New("mongo down")}
	c := NewCachedTermHeat(inner, time.Second, 16)

	if _, err := c.RelatedTerms(context.Background(), "成都", 8); err == nil {
		t.Fatalf("expected error to pass through")
	}
	if _, err := c.RelatedTerms(context.Background(), "成都", 8); err == nil {
		t.Fatalf("expected error to pass through on second call")
	}
	if inner.calls.Load() != 2 {
		t.Fatalf("inner calls=%d, want 2 (errors not cached)", inner.calls.Load())
	}
}

func TestCachedTermHeatBoundsKeys(t *testing.T) {
	inner := &countingTermHeat{terms: []queryheat.TermHeat{{NormalizedTerm: "x", Relevance: 1}}}
	now := time.Unix(0, 0)
	c := NewCachedTermHeat(inner, time.Hour, 4)
	c.now = func() time.Time { return now }

	for i := 0; i < 50; i++ {
		key := string(rune('a' + (i % 50)))
		if _, err := c.RelatedTerms(context.Background(), key+string(rune('0'+i)), 8); err != nil {
			t.Fatalf("unexpected err: %v", err)
		}
	}
	c.mu.Lock()
	n := len(c.entries)
	c.mu.Unlock()
	if n > 4 {
		t.Fatalf("cache size=%d exceeded maxKeys=4", n)
	}
}

func TestNewCachedTermHeatNilInner(t *testing.T) {
	if c := NewCachedTermHeat(nil, time.Second, 16); c != nil {
		t.Fatalf("expected nil wrapper for nil inner, got %v", c)
	}
}
