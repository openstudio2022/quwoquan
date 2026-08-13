package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sort"
	"strings"
	"sync"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

// OwnerSearchCache collapses the Zipf head of the result-page traffic into one
// engine round trip per hot key per TTL window:
//
//   - Only first-page (no cursor) result-mode owner queries are cached —
//     paginated requests are bound to their continuation semantics.
//   - The key binds the normalized query, the full filter scope, the
//     experiment bucket (BoostTerms change the engine order) and the policy /
//     candidate identity. The cloud result path serves public objects only, so
//     the viewer identity deliberately stays out of the key (per-user keys
//     would push the hit rate toward zero).
//   - TTL must stay at or below the index-freshness promise
//     (search_slo.yaml indexing.index_freshness_seconds_max = 30s).
//   - Concurrent misses on one key are collapsed into a single engine call
//     (singleflight): under spike traffic the expiry of one hot query must not
//     stampede the engine.
//
// Errors are never cached, and degraded responses (non-empty DegradeSignals)
// are not cached either, so a transient engine failure is not pinned for a
// whole TTL window.
type OwnerSearchCache struct {
	ttl     time.Duration
	maxKeys int
	now     func() time.Time

	mu       sync.Mutex
	entries  map[string]ownerSearchCacheEntry
	inFlight map[string]*ownerSearchCall
}

type ownerSearchCacheEntry struct {
	response  OwnerSearchResponse
	expiresAt time.Time
}

type ownerSearchCall struct {
	done     chan struct{}
	response OwnerSearchResponse
	err      error
}

// NewOwnerSearchCache builds the first-page result cache. TTL defaults to 10s
// and is clamped to the 30s freshness promise.
func NewOwnerSearchCache(ttl time.Duration, maxKeys int) *OwnerSearchCache {
	if ttl <= 0 {
		ttl = 10 * time.Second
	}
	if ttl > 30*time.Second {
		ttl = 30 * time.Second
	}
	if maxKeys <= 0 {
		maxKeys = 512
	}
	return &OwnerSearchCache{
		ttl:      ttl,
		maxKeys:  maxKeys,
		now:      time.Now,
		entries:  make(map[string]ownerSearchCacheEntry, maxKeys),
		inFlight: map[string]*ownerSearchCall{},
	}
}

// Cacheable reports whether this input may be served from / stored into the
// cache: first page, result mode, no per-request ids.
func (c *OwnerSearchCache) Cacheable(in QueryInput) bool {
	if c == nil {
		return false
	}
	return strings.TrimSpace(in.Cursor) == "" &&
		normalizedSearchMode(in.Mode) == "result" &&
		len(in.IDs) == 0
}

// Execute serves a cached first page or collapses concurrent misses into one
// call of next.
func (c *OwnerSearchCache) Execute(
	ctx context.Context,
	in QueryInput,
	identity QueryExecutionIdentity,
	bucket string,
	next func(context.Context) (OwnerSearchResponse, error),
) (OwnerSearchResponse, error) {
	if !c.Cacheable(in) {
		return next(ctx)
	}
	key := ownerSearchCacheKey(in, identity, bucket)
	now := c.now()

	c.mu.Lock()
	if entry, ok := c.entries[key]; ok && now.Before(entry.expiresAt) {
		c.mu.Unlock()
		return entry.response, nil
	}
	if call, ok := c.inFlight[key]; ok {
		c.mu.Unlock()
		select {
		case <-call.done:
			return call.response, call.err
		case <-ctx.Done():
			return OwnerSearchResponse{}, ctx.Err()
		}
	}
	call := &ownerSearchCall{done: make(chan struct{})}
	c.inFlight[key] = call
	c.mu.Unlock()

	response, err := next(ctx)
	call.response, call.err = response, err
	close(call.done)

	c.mu.Lock()
	delete(c.inFlight, key)
	if err == nil && len(response.DegradeSignals) == 0 {
		if len(c.entries) >= c.maxKeys {
			c.evictSoonestLocked()
		}
		c.entries[key] = ownerSearchCacheEntry{
			response:  response,
			expiresAt: c.now().Add(c.ttl),
		}
	}
	c.mu.Unlock()
	return response, err
}

func (c *OwnerSearchCache) evictSoonestLocked() {
	var soonestKey string
	var soonest time.Time
	for key, entry := range c.entries {
		if soonestKey == "" || entry.expiresAt.Before(soonest) {
			soonestKey = key
			soonest = entry.expiresAt
		}
	}
	if soonestKey != "" {
		delete(c.entries, soonestKey)
	}
}

func ownerSearchCacheKey(in QueryInput, identity QueryExecutionIdentity, bucket string) string {
	normalizedQuery := rtsearch.Analyze(in.Query, nil).Normalized
	objectTypes := normalizedSorted(in.ObjectTypes)
	contentTypes := normalizedSorted(in.ContentTypes)
	tags := normalizedSorted(in.Tags)
	boosts := make([]string, 0, len(in.BoostTerms))
	for _, boost := range in.BoostTerms {
		boosts = append(boosts, boost.Term)
	}
	sort.Strings(boosts)
	payload, _ := json.Marshal(struct {
		Query        string   `json:"query"`
		ObjectTypes  []string `json:"objectTypes"`
		ContentTypes []string `json:"contentTypes"`
		Tags         []string `json:"tags"`
		TimeRange    any      `json:"timeRange,omitempty"`
		Near         any      `json:"near,omitempty"`
		Limit        int      `json:"limit"`
		Bucket       string   `json:"bucket"`
		Boosts       []string `json:"boosts"`
		Candidate    string   `json:"candidate"`
		Policy       string   `json:"policy"`
	}{
		Query: normalizedQuery, ObjectTypes: objectTypes, ContentTypes: contentTypes,
		Tags: tags, TimeRange: in.TimeRange, Near: in.Near, Limit: in.Limit,
		Bucket: bucket, Boosts: boosts,
		Candidate: identity.CandidateDigest, Policy: identity.PolicyDigest,
	})
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:])
}
