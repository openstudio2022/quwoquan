package es

import (
	"context"

	rtsearch "quwoquan_service/runtime/search"
)

// Searcher abstracts the ES transport so the backend is testable without a real
// cluster (a fake Searcher returns canned candidates; the production Searcher is
// an HTTP client built from the injected ES_ENDPOINT secret).
type Searcher interface {
	Search(ctx context.Context, index string, body map[string]any) ([]rtsearch.RecallCandidate, error)
}

// Backend implements rtsearch.RecallBackend over Elasticsearch.
type Backend struct {
	searcher Searcher
	builder  *QueryBuilder
	index    string
}

// NewBackend constructs the ES backend. index defaults to DefaultIndex.
func NewBackend(searcher Searcher, index string) *Backend {
	if index == "" {
		index = DefaultIndex
	}
	return &Backend{
		searcher: searcher,
		builder:  NewQueryBuilder(),
		index:    index,
	}
}

// Name implements rtsearch.RecallBackend.
func (b *Backend) Name() string { return "elasticsearch" }

// Recall implements rtsearch.RecallBackend by building the DSL and delegating to
// the Searcher. The shared CrossTypeRanker still applies final normalization,
// boosts and the permission gate (defense in depth).
func (b *Backend) Recall(ctx context.Context, plan rtsearch.RetrievePlan) ([]rtsearch.RecallCandidate, error) {
	body := b.builder.Build(plan)
	return b.searcher.Search(ctx, b.index, body)
}
