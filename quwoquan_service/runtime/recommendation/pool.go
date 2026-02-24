package recommendation

import "sync"

// Pools for high-frequency intermediate slices in the recommendation pipeline.
// These reduce GC pressure under high concurrency by reusing heap allocations
// across GetFeed requests instead of allocating fresh slices every call.

const defaultPoolCap = 256

var candidatePool = sync.Pool{
	New: func() any {
		s := make([]ContentCandidate, 0, defaultPoolCap)
		return &s
	},
}

var scoredPool = sync.Pool{
	New: func() any {
		s := make([]ScoredCandidate, 0, defaultPoolCap)
		return &s
	},
}

var feedItemPool = sync.Pool{
	New: func() any {
		s := make([]FeedItem, 0, 32)
		return &s
	},
}

// acquireCandidates returns a pooled []ContentCandidate slice (length 0).
func acquireCandidates() *[]ContentCandidate {
	p := candidatePool.Get().(*[]ContentCandidate)
	*p = (*p)[:0]
	return p
}

// releaseCandidates returns a candidate slice to the pool.
// The caller must not reference the slice after release.
func releaseCandidates(p *[]ContentCandidate) {
	if p == nil {
		return
	}
	if cap(*p) > 4096 {
		return
	}
	*p = (*p)[:0]
	candidatePool.Put(p)
}

// acquireScored returns a pooled []ScoredCandidate slice (length 0).
func acquireScored() *[]ScoredCandidate {
	p := scoredPool.Get().(*[]ScoredCandidate)
	*p = (*p)[:0]
	return p
}

// releaseScored returns a scored slice to the pool.
func releaseScored(p *[]ScoredCandidate) {
	if p == nil {
		return
	}
	if cap(*p) > 4096 {
		return
	}
	*p = (*p)[:0]
	scoredPool.Put(p)
}

// acquireFeedItems returns a pooled []FeedItem slice (length 0).
func acquireFeedItems() *[]FeedItem {
	p := feedItemPool.Get().(*[]FeedItem)
	*p = (*p)[:0]
	return p
}

// releaseFeedItems returns a feed item slice to the pool.
func releaseFeedItems(p *[]FeedItem) {
	if p == nil {
		return
	}
	if cap(*p) > 4096 {
		return
	}
	*p = (*p)[:0]
	feedItemPool.Put(p)
}
