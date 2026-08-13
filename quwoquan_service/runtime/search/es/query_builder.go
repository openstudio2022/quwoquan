// Package es implements the Elasticsearch RecallBackend for runtime/search.
//
// It is the single search-service production recall backend. NativeStoreBackend
// remains available to domain-local retrieval code and deterministic tests, but
// is never selected as an outage fallback for the unified search API.
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
	// PhraseFields receive an exact-phrase boost so 精确短语命中 outranks
	// bag-of-words matches with the same terms.
	PhraseFields []string
	// PinyinFields are the .py sub-fields (short name/title fields only) that
	// let latin-input queries recall Chinese objects.
	PinyinFields []string
	// FuzzyMaxTerms bounds the fuzzy clause: fuzziness is the most expensive
	// text clause, so it only fires for short queries (<= this many terms).
	// 0 disables fuzziness entirely.
	FuzzyMaxTerms int
}

// NewQueryBuilder returns a builder with the default field weights.
func NewQueryBuilder() *QueryBuilder {
	return &QueryBuilder{
		TextFields:    []string{"title^3", "summary^2", "body", "tags^2.2", "entities^2"},
		PhraseFields:  []string{"title^3", "summary^1.5"},
		PinyinFields:  []string{"title.py^1.2", "authorName.py", "groupName.py", "entityName.py", "placeName.py"},
		FuzzyMaxTerms: 2,
	}
}

// Build converts a RetrievePlan into an ES search body.
func (b *QueryBuilder) Build(plan rtsearch.RetrievePlan) map[string]any {
	must := []map[string]any{}
	filter := []map[string]any{}
	should := []map[string]any{}

	// terms -> composed text recall: at least one of best_fields / exact phrase /
	// pinyin / (bounded) fuzzy must match. Phrase outranks bag-of-words; pinyin
	// covers latin input; fuzziness only fires on short queries (CPU guard).
	if len(plan.Terms) > 0 {
		query := strings.Join(plan.Terms, " ")
		textShould := []map[string]any{
			{
				"multi_match": map[string]any{
					"query":  query,
					"fields": b.TextFields,
					"type":   "best_fields",
				},
			},
			{
				"multi_match": map[string]any{
					"query":  query,
					"fields": b.PhraseFields,
					"type":   "phrase",
					"boost":  2.0,
				},
			},
		}
		if len(b.PinyinFields) > 0 {
			textShould = append(textShould, map[string]any{
				"multi_match": map[string]any{
					"query":  query,
					"fields": b.PinyinFields,
					"type":   "best_fields",
					"boost":  0.8,
				},
			})
		}
		if b.FuzzyMaxTerms > 0 && len(plan.Terms) <= b.FuzzyMaxTerms {
			textShould = append(textShould, map[string]any{
				"multi_match": map[string]any{
					"query":         query,
					"fields":        b.TextFields,
					"type":          "best_fields",
					"fuzziness":     "AUTO",
					"prefix_length": 1,
					"boost":         0.3,
				},
			})
		}
		must = append(must, map[string]any{
			"bool": map[string]any{
				"should":               textShould,
				"minimum_should_match": 1,
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

	// Query-time boost injection (term_heat AB arm): matching a hot related term
	// lifts the engine score directly, so the AB treatment participates in the
	// single engine ranking instead of a post-recall re-rank.
	for _, boost := range plan.BoostTerms {
		should = append(should, map[string]any{
			"multi_match": map[string]any{
				"query":  boost.Term,
				"fields": []string{"title^1.5", "summary", "tags^1.2"},
				"boost":  boost.Weight,
			},
		})
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
		// Recall a stable prefix. The Search owner applies the cursor-decoded
		// offset only after the single canonical cross-type sort; exposing ES
		// from/search_after would create a second pagination truth. Pagination
		// depth is bounded by the owner cursor (MaxCursorOffset), so this window
		// stays small.
		"size":  plan.Offset + plan.Limit,
		"from":  0,
		"query": buildFunctionScore(plan, boolQuery),
		// Stable total order aligned field-by-field with rtsearch.LessHitStable
		// (Score desc -> Title asc -> Target asc -> ObjectID asc) so the ES
		// top-`size` cutoff and the application page slice share one ranking
		// truth across replicas, segment merges and refreshes.
		"sort": []map[string]any{
			{"_score": map[string]any{"order": "desc"}},
			{"title.kw": map[string]any{"order": "asc", "missing": "_last", "unmapped_type": "keyword"}},
			{"target": map[string]any{"order": "asc"}},
			{"objectId": map[string]any{"order": "asc"}},
		},
		// Cost guard: commercial recall only needs the top-`size` window, never an
		// exact hit total, so skip exact total counting on every high-QPS query.
		"track_total_hits": false,
	}
	if plan.PITID != "" {
		// Pagination snapshot: the PIT pins segments and shard copies, so every
		// follow-up page reads the exact index state the pagination started on.
		// Each page renews the lease; abandoning the pagination lets it expire.
		body["pit"] = map[string]any{"id": plan.PITID, "keep_alive": PITKeepAlive}
	}
	if len(plan.Terms) > 0 {
		// Server-side highlighter selects the best matching fragment as a plain
		// snippet (no markup — the App highlights via matchedTerms). unified
		// highlighter needs no term_vectors, so the index carries no extra cost.
		body["highlight"] = map[string]any{
			"type":                "unified",
			"fragment_size":       100,
			"number_of_fragments": 1,
			"pre_tags":            []any{""},
			"post_tags":           []any{""},
			"fields": map[string]any{
				"title":   map[string]any{},
				"summary": map[string]any{},
				"body":    map[string]any{},
			},
		}
	}
	return body
}

// buildFunctionScore pushes the static CrossTypeRanker factors (freshness,
// quality/popularity, geo proximity) down into ES so the engine's sort order is
// the final commercial order (single ranking truth; the application layer only
// explains it via rankReasons and never re-ranks server-ranked candidates).
// score_mode/boost_mode `sum` mirrors the additive composition the shared
// ranker uses for native candidates.
func buildFunctionScore(plan rtsearch.RetrievePlan, boolQuery map[string]any) map[string]any {
	functions := []map[string]any{
		{
			// freshnessScore analogue: newer content decays over ~30 days.
			"gauss": map[string]any{
				"updatedAt": map[string]any{
					"origin": "now",
					"scale":  "30d",
					"offset": "1d",
					"decay":  0.5,
				},
			},
			"weight": 1.2,
		},
		{
			// popularityScore analogue: quality is the projected popularity signal.
			"field_value_factor": map[string]any{
				"field":    "quality",
				"factor":   1.0,
				"modifier": "sqrt",
				"missing":  0,
			},
			"weight": 0.5,
		},
	}
	if plan.Near.Active() {
		functions = append(functions, map[string]any{
			// geo proximity analogue: closer to the pin ranks higher inside the
			// hard geo_distance filter window.
			"gauss": map[string]any{
				"geo": map[string]any{
					"origin": map[string]any{"lat": plan.Near.Lat, "lon": plan.Near.Lng},
					"scale":  strconv.FormatFloat(maxFloat(plan.Near.RadiusKm/2, 0.1), 'f', -1, 64) + "km",
					"decay":  0.5,
				},
			},
			"weight": 1.5,
		})
	}
	return map[string]any{
		"function_score": map[string]any{
			"query":      map[string]any{"bool": boolQuery},
			"functions":  functions,
			"score_mode": "sum",
			"boost_mode": "sum",
		},
	}
}

func maxFloat(a, b float64) float64 {
	if a > b {
		return a
	}
	return b
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
