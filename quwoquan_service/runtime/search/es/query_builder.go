// Package es implements the Elasticsearch RecallBackend for runtime/search.
//
// It is capability-complete but default-off: the launch backend is
// search.NativeStoreBackend. ESBackend is selected only when ES is deployed and
// SEARCH_BACKEND=es (or ES_ENDPOINT is injected). QueryBuilder is unit-tested by
// asserting the produced DSL, without requiring a real ES cluster.
package es

import (
	"strconv"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
)

// DefaultIndex is the unified object index name.
const DefaultIndex = "quwoquan_objects"

// QueryBuilder assembles a single ES request that covers recall + filter +
// (P2) hybrid kNN in one round trip.
type QueryBuilder struct {
	// TextFields are the weighted full-text fields for the terms multi_match.
	TextFields []string
}

// NewQueryBuilder returns a builder with the default field weights.
func NewQueryBuilder() *QueryBuilder {
	return &QueryBuilder{
		TextFields: []string{"title^3", "summary^2", "body", "tags^2.2", "entities^2"},
	}
}

// Build converts a RetrievePlan into an ES search body.
func (b *QueryBuilder) Build(plan rtsearch.RetrievePlan) map[string]any {
	must := []map[string]any{}
	filter := []map[string]any{}
	should := []map[string]any{}

	// terms -> multi_match (main text match).
	if len(plan.Terms) > 0 {
		must = append(must, map[string]any{
			"multi_match": map[string]any{
				"query":  strings.Join(plan.Terms, " "),
				"fields": b.TextFields,
				"type":   "best_fields",
			},
		})
	}

	// targets -> term filter on the AI target field.
	if len(plan.Targets) > 0 {
		targets := make([]string, 0, len(plan.Targets))
		for _, t := range plan.Targets {
			targets = append(targets, string(t))
		}
		filter = append(filter, map[string]any{"terms": map[string]any{"target": targets}})
	}

	// filters.tags -> hard term filter (boost handled in should).
	if len(plan.Tags) > 0 {
		filter = append(filter, map[string]any{"terms": map[string]any{"tags": plan.Tags}})
		should = append(should, map[string]any{"terms": map[string]any{"tags": plan.Tags, "boost": 2.0}})
	}

	// filters.timeRange -> range filter on updatedAt.
	if plan.TimeRange != nil {
		rng := map[string]any{}
		if !plan.TimeRange.From.IsZero() {
			rng["gte"] = plan.TimeRange.From.UTC().Format("2006-01-02T15:04:05Z07:00")
		}
		if !plan.TimeRange.To.IsZero() {
			rng["lte"] = plan.TimeRange.To.UTC().Format("2006-01-02T15:04:05Z07:00")
		}
		if len(rng) > 0 {
			filter = append(filter, map[string]any{"range": map[string]any{"updatedAt": rng}})
		}
	}

	// filters.near -> geo_distance hard filter (附近). Scopes recall to candidates
	// within RadiusKm of the pin. Proximity WEIGHTING is intentionally left to the
	// shared CrossTypeRanker (rankAndMerge) so native and ES share one proximity
	// scoring truth source (R24: no second ranking chain); this stays pure recall.
	if plan.Near.Active() {
		filter = append(filter, map[string]any{
			"geo_distance": map[string]any{
				"distance": strconv.FormatFloat(plan.Near.RadiusKm, 'f', -1, 64) + "km",
				"geo":      map[string]any{"lat": plan.Near.Lat, "lon": plan.Near.Lng},
			},
		})
	}

	// Permission gate is pushed down as a filter (visibility is implicit).
	if !plan.Viewer.IncludePrivate {
		filter = append(filter, map[string]any{"terms": map[string]any{"visibility": []string{"public"}}})
	}

	// ids -> objectId direct hit OR related anchor fields.
	anchorClauses := []map[string]any{}
	if len(plan.IDs) > 0 {
		anchorClauses = append(anchorClauses,
			map[string]any{"terms": map[string]any{"objectId": plan.IDs, "boost": 5.0}},
			map[string]any{"terms": map[string]any{"authorId": plan.IDs, "boost": 3.0}},
			map[string]any{"terms": map[string]any{"groupId": plan.IDs, "boost": 3.0}},
			map[string]any{"terms": map[string]any{"entityId": plan.IDs, "boost": 3.0}},
		)
	}
	// names -> related-name anchors (author/group/entity) resolved by ES analyzers.
	if len(plan.Names) > 0 {
		query := strings.Join(plan.Names, " ")
		anchorClauses = append(anchorClauses,
			map[string]any{"match": map[string]any{"authorName": map[string]any{"query": query, "boost": 2.5}}},
			map[string]any{"match": map[string]any{"groupName": map[string]any{"query": query, "boost": 2.5}}},
			map[string]any{"match": map[string]any{"entityName": map[string]any{"query": query, "boost": 2.5}}},
		)
	}

	boolQuery := map[string]any{}
	// When there is no text match, anchors become required (minimum_should_match).
	if len(anchorClauses) > 0 {
		should = append(should, anchorClauses...)
		if len(must) == 0 {
			boolQuery["minimum_should_match"] = 1
		}
	}
	if len(must) > 0 {
		boolQuery["must"] = must
	}
	if len(filter) > 0 {
		boolQuery["filter"] = filter
	}
	if len(should) > 0 {
		boolQuery["should"] = should
	}

	body := map[string]any{
		"size":  plan.Limit,
		"from":  plan.Offset,
		"query": map[string]any{"bool": boolQuery},
		// Stable sort tie-break: _score primary, then objectId (keyword) so the
		// top-`size` cutoff is deterministic across replicas, segment merges and
		// refreshes. Without this, equal-_score docs at the size boundary are
		// selected in a non-deterministic internal order, so the candidate set
		// (and thus the final re-ranked TopN) can jump between identical queries.
		"sort": []map[string]any{
			{"_score": map[string]any{"order": "desc"}},
			{"objectId": map[string]any{"order": "asc"}},
		},
		// Cost guard: commercial recall only needs the top-`size` window, never an
		// exact hit total, so skip exact total counting on every high-QPS query.
		"track_total_hits": false,
	}
	return body
}

// BuildHybrid layers a dense_vector kNN clause on top of the lexical query and
// fuses with RRF. queryVector is the embedded query (P2/RAG). When the vector is
// empty this is identical to Build.
func (b *QueryBuilder) BuildHybrid(plan rtsearch.RetrievePlan, queryVector []float64, k int) map[string]any {
	body := b.Build(plan)
	if len(queryVector) == 0 {
		return body
	}
	if k <= 0 {
		k = plan.Limit
	}
	// RRF rank governs ordering for the hybrid path; ES rejects a top-level sort
	// alongside rank, so drop the lexical tie-break sort here (determinism for the
	// hybrid path is a P2 concern handled by RRF + stable rank inputs).
	delete(body, "sort")
	body["knn"] = map[string]any{
		"field":          "embedding",
		"query_vector":   queryVector,
		"k":              k,
		"num_candidates": k * 5,
	}
	body["rank"] = map[string]any{"rrf": map[string]any{}}
	return body
}
