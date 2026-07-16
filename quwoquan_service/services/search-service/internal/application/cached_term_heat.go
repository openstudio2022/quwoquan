package application

import (
	"context"
	"sync"
	"time"

	"quwoquan_service/services/search-service/internal/application/queryheat"
)

// CachedTermHeat wraps a TermHeatProvider with a short-TTL, size-bounded
// in-memory cache keyed by the normalized query. Related-terms lookups hit Mongo
// on every search; under concurrency the same hot queries repeat constantly, so
// a few-second cache collapses that fan-out into one Mongo read per hot key per
// TTL window. It is best-effort and read-through: a cache miss falls through to
// the underlying provider, and errors are never cached (so a transient Mongo
// failure is not pinned for the whole TTL).
type CachedTermHeat struct {
	inner    TermHeatProvider
	ttl      time.Duration
	maxKeys  int
	now      func() time.Time
	observer RelatedTermsCacheObserver

	mu      sync.Mutex
	entries map[string]cachedHeatEntry
}

type cachedHeatEntry struct {
	heats     []queryheat.TermHeat
	expiresAt time.Time
}

// NewCachedTermHeat 包装热词读取端口；observer 可为空。
func NewCachedTermHeat(inner TermHeatProvider, ttl time.Duration, maxKeys int, observer RelatedTermsCacheObserver) *CachedTermHeat {
	if inner == nil {
		return nil
	}
	if ttl <= 0 {
		ttl = 2 * time.Second
	}
	if maxKeys <= 0 {
		maxKeys = 1024
	}
	return &CachedTermHeat{
		inner:    inner,
		ttl:      ttl,
		maxKeys:  maxKeys,
		now:      time.Now,
		observer: observer,
		entries:  make(map[string]cachedHeatEntry, maxKeys),
	}
}

// RelatedTerms serves from cache when fresh, else reads through and caches the
// result (including a legitimately empty result, to offload Mongo for no-heat
// queries). The limit is part of the contract but heat rows are capped by the
// provider; we key on query only and trim defensively to limit.
func (c *CachedTermHeat) RelatedTerms(ctx context.Context, normalizedQuery string, limit int) ([]queryheat.TermHeat, error) {
	now := c.now()

	c.mu.Lock()
	if e, ok := c.entries[normalizedQuery]; ok && now.Before(e.expiresAt) {
		c.mu.Unlock()
		c.observeCache(true)
		return trimHeats(e.heats, limit), nil
	}
	c.mu.Unlock()

	c.observeCache(false)
	heats, err := c.inner.RelatedTerms(ctx, normalizedQuery, limit)
	if err != nil {
		return nil, err
	}

	c.mu.Lock()
	c.evictIfNeededLocked(now)
	c.entries[normalizedQuery] = cachedHeatEntry{heats: heats, expiresAt: now.Add(c.ttl)}
	c.mu.Unlock()
	return heats, nil
}

func (c *CachedTermHeat) observeCache(hit bool) {
	if c.observer != nil {
		c.observer.ObserveRelatedTermsCache(hit)
	}
}

// evictIfNeededLocked keeps the map bounded: it first drops expired keys, then,
// if still at capacity, evicts the entry expiring soonest. Caller holds c.mu.
func (c *CachedTermHeat) evictIfNeededLocked(now time.Time) {
	if len(c.entries) < c.maxKeys {
		return
	}
	for k, e := range c.entries {
		if !now.Before(e.expiresAt) {
			delete(c.entries, k)
		}
	}
	if len(c.entries) < c.maxKeys {
		return
	}
	var oldestKey string
	var oldest time.Time
	for k, e := range c.entries {
		if oldestKey == "" || e.expiresAt.Before(oldest) {
			oldestKey, oldest = k, e.expiresAt
		}
	}
	if oldestKey != "" {
		delete(c.entries, oldestKey)
	}
}

func trimHeats(heats []queryheat.TermHeat, limit int) []queryheat.TermHeat {
	if limit > 0 && len(heats) > limit {
		return heats[:limit]
	}
	return heats
}
