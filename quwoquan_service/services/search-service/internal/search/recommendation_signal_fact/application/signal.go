package application

import (
	"context"

	signaldomain "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/domain"
)

// Signal mirrors the SearchRecommendationSignalPublished contract. Query and
// click are intentionally disjoint so an exposure can never become affinity.
type Signal = signaldomain.Fact

// Publisher appends a replay-safe signal to the object-owned durable stream.
type Publisher interface {
	PublishSearchSignal(ctx context.Context, signal Signal) error
}
