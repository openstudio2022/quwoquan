package application

import (
	"context"
	"time"
)

// Signal mirrors the SearchRecommendationSignalPublished contract. Query and
// click are intentionally disjoint so an exposure can never become affinity.
type Signal struct {
	SignalID         string
	SignalType       string
	SearchRequestID  string
	SessionID        string
	UserID           string
	NormalizedQuery  string
	RelatedTerms     []string
	EngagedObjectIDs []string
	RankingVersion   string
	ExperimentBucket string
	ResultCount      int
	CreatedAt        time.Time
}

// Publisher appends a replay-safe signal to the object-owned durable stream.
type Publisher interface {
	PublishSearchSignal(ctx context.Context, signal Signal) error
}
