package persistence

import (
	"context"
	cryptorand "crypto/rand"
	"encoding/binary"
	"sync"
	"time"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const (
	DefaultActiveSupplyCacheTTL    = 2 * time.Second
	DefaultActiveSupplyCacheJitter = 500 * time.Millisecond
)

type activeSupplyCacheKey struct {
	environment    string
	releaseID      string
	manifestDigest string
}

type activeSupplySnapshotCall struct {
	done     chan struct{}
	snapshot postports.ActiveSupplySnapshot
	err      error
}

// activeSupplySnapshotCache coalesces the expensive projection readback counts
// after the caller has read the current release identity. Only Ready snapshots
// are cached; failures and incomplete readbacks invalidate the selected key.
// A release/digest change switches currentKey before loading, so a late result
// from the previous release can never repopulate the cache.
type activeSupplySnapshotCache struct {
	mu         sync.Mutex
	now        func() time.Time
	ttl        time.Duration
	jitter     time.Duration
	randomSeed uint64

	currentKey activeSupplyCacheKey
	snapshot   postports.ActiveSupplySnapshot
	expiresAt  time.Time
	inflight   map[activeSupplyCacheKey]*activeSupplySnapshotCall
}

func newActiveSupplySnapshotCache(
	ttl time.Duration,
	jitter time.Duration,
) *activeSupplySnapshotCache {
	if ttl <= 0 {
		ttl = DefaultActiveSupplyCacheTTL
	}
	if jitter < 0 {
		jitter = 0
	}
	var seedBytes [8]byte
	if _, err := cryptorand.Read(seedBytes[:]); err != nil {
		binary.LittleEndian.PutUint64(seedBytes[:], uint64(time.Now().UnixNano()))
	}
	return &activeSupplySnapshotCache{
		now:        func() time.Time { return time.Now().UTC() },
		ttl:        ttl,
		jitter:     jitter,
		randomSeed: binary.LittleEndian.Uint64(seedBytes[:]),
		inflight:   make(map[activeSupplyCacheKey]*activeSupplySnapshotCall),
	}
}

func (cache *activeSupplySnapshotCache) Invalidate() {
	if cache == nil {
		return
	}
	cache.mu.Lock()
	cache.currentKey = activeSupplyCacheKey{}
	cache.snapshot = postports.ActiveSupplySnapshot{}
	cache.expiresAt = time.Time{}
	cache.mu.Unlock()
}

func (cache *activeSupplySnapshotCache) Load(
	ctx context.Context,
	key activeSupplyCacheKey,
	read func(context.Context) (postports.ActiveSupplySnapshot, error),
) (postports.ActiveSupplySnapshot, error) {
	if cache == nil {
		return read(ctx)
	}
	now := cache.now()
	cache.mu.Lock()
	if cache.currentKey != key {
		cache.currentKey = key
		cache.snapshot = postports.ActiveSupplySnapshot{}
		cache.expiresAt = time.Time{}
	}
	if cache.snapshot.Ready() && now.Before(cache.expiresAt) {
		snapshot := cache.snapshot
		cache.mu.Unlock()
		return snapshot, nil
	}
	if call := cache.inflight[key]; call != nil {
		cache.mu.Unlock()
		select {
		case <-ctx.Done():
			return postports.ActiveSupplySnapshot{}, ctx.Err()
		case <-call.done:
			return call.snapshot, call.err
		}
	}
	call := &activeSupplySnapshotCall{done: make(chan struct{})}
	cache.inflight[key] = call
	cache.mu.Unlock()

	snapshot, err := read(ctx)
	cache.mu.Lock()
	delete(cache.inflight, key)
	call.snapshot = snapshot
	call.err = err
	if err == nil && snapshot.Ready() && cache.currentKey == key {
		cache.snapshot = snapshot
		cache.expiresAt = cache.now().Add(cache.ttl + cache.nextJitterLocked())
	} else if cache.currentKey == key {
		cache.snapshot = postports.ActiveSupplySnapshot{}
		cache.expiresAt = time.Time{}
	}
	close(call.done)
	cache.mu.Unlock()
	return snapshot, err
}

func (cache *activeSupplySnapshotCache) nextJitterLocked() time.Duration {
	if cache.jitter <= 0 {
		return 0
	}
	// xorshift64 keeps jitter local to this cache and avoids the package-global
	// pseudo-random lock on the request hot path.
	seed := cache.randomSeed
	seed ^= seed << 13
	seed ^= seed >> 7
	seed ^= seed << 17
	cache.randomSeed = seed
	return time.Duration(seed % uint64(cache.jitter+1))
}
