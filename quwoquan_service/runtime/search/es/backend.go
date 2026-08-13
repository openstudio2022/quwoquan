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

type replicaPreferenceKey struct{}

// WithReplicaPreference pins the request to a deterministic shard replica
// (ES ?preference=). Replicas legitimately differ in segment-merge state, so
// identical queries can score marginally differently across copies; session
// stickiness removes that visible jitter without the extra round trip of
// dfs_query_then_fetch. The value must already be a non-PII digest.
func WithReplicaPreference(ctx context.Context, preference string) context.Context {
	if preference == "" {
		return ctx
	}
	return context.WithValue(ctx, replicaPreferenceKey{}, preference)
}

// ReplicaPreferenceFromContext returns the pinned replica preference, if any.
func ReplicaPreferenceFromContext(ctx context.Context) string {
	preference, _ := ctx.Value(replicaPreferenceKey{}).(string)
	return preference
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
// the Searcher. Candidates come back ServerRanked (function_score pushdown);
// the shared pipeline keeps only filtering, the permission gate and rank
// explanation (defense in depth, no second score).
func (b *Backend) Recall(ctx context.Context, plan rtsearch.RetrievePlan) ([]rtsearch.RecallCandidate, error) {
	body := b.builder.Build(plan)
	if plan.ReplicaPreference != "" {
		ctx = WithReplicaPreference(ctx, plan.ReplicaPreference)
	}
	return b.searcher.Search(ctx, b.index, body)
}
