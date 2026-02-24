package recommendation

import (
	"context"
	"sync"
	"time"
)

// SessionCache provides an L1 in-process cache over any SessionReader.
// Includes singleflight deduplication: concurrent requests for the same
// session key share a single Redis round-trip.
type SessionCache struct {
	inner   SessionReader
	mu      sync.RWMutex
	cache   map[string]*cachedEntry
	ttl     time.Duration
	maxSize int

	// singleflight: deduplicate concurrent reads to the same session
	sfMu    sync.Mutex
	inflight map[string]*sfCall
}

type cachedEntry struct {
	state     *SessionState
	fetchedAt time.Time
}

type sfCall struct {
	wg    sync.WaitGroup
	state *SessionState
	err   error
}

func NewSessionCache(inner SessionReader, ttl time.Duration, maxSize int) *SessionCache {
	if ttl <= 0 {
		ttl = 2 * time.Second
	}
	if maxSize <= 0 {
		maxSize = 10000
	}
	sc := &SessionCache{
		inner:    inner,
		cache:    make(map[string]*cachedEntry, 256),
		ttl:      ttl,
		maxSize:  maxSize,
		inflight: make(map[string]*sfCall),
	}
	go sc.evictLoop()
	return sc
}

// GetSessionState checks L1 cache first, then deduplicates concurrent misses.
func (sc *SessionCache) GetSessionState(ctx context.Context, userID, sessionID string) (*SessionState, error) {
	key := userID + ":" + sessionID

	// L1 cache hit
	sc.mu.RLock()
	if entry, ok := sc.cache[key]; ok && time.Since(entry.fetchedAt) < sc.ttl {
		sc.mu.RUnlock()
		return entry.state, nil
	}
	sc.mu.RUnlock()

	// Singleflight: if another goroutine is already fetching this key, wait for it
	sc.sfMu.Lock()
	if call, ok := sc.inflight[key]; ok {
		sc.sfMu.Unlock()
		call.wg.Wait()
		return call.state, call.err
	}

	call := &sfCall{}
	call.wg.Add(1)
	sc.inflight[key] = call
	sc.sfMu.Unlock()

	// Fetch from inner reader
	call.state, call.err = sc.inner.GetSessionState(ctx, userID, sessionID)
	call.wg.Done()

	// Remove from inflight
	sc.sfMu.Lock()
	delete(sc.inflight, key)
	sc.sfMu.Unlock()

	// Store in L1 cache on success
	if call.err == nil {
		sc.mu.Lock()
		if len(sc.cache) >= sc.maxSize {
			sc.evictOldest()
		}
		sc.cache[key] = &cachedEntry{state: call.state, fetchedAt: time.Now()}
		sc.mu.Unlock()
	}

	return call.state, call.err
}

// Invalidate removes a session from the cache (call after processing signals).
func (sc *SessionCache) Invalidate(userID, sessionID string) {
	key := userID + ":" + sessionID
	sc.mu.Lock()
	delete(sc.cache, key)
	sc.mu.Unlock()
}

func (sc *SessionCache) evictOldest() {
	now := time.Now()
	evicted := 0
	target := sc.maxSize / 4
	for k, v := range sc.cache {
		if evicted >= target || now.Sub(v.fetchedAt) > sc.ttl {
			delete(sc.cache, k)
			evicted++
		}
		if evicted >= target {
			break
		}
	}
}

func (sc *SessionCache) evictLoop() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for range ticker.C {
		sc.mu.Lock()
		now := time.Now()
		for k, v := range sc.cache {
			if now.Sub(v.fetchedAt) > sc.ttl*2 {
				delete(sc.cache, k)
			}
		}
		sc.mu.Unlock()
	}
}
