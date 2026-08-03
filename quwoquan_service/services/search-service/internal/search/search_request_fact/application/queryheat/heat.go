// Package queryheat is the pure, storage-agnostic search-term heat/relevance
// algorithm: query-log mining over normalized terms with recency decay and CTR
// weighting, plus query→clicked-object relevance. It has no I/O so it is fully
// unit-testable; infrastructure feeds it raw records and persists the result.
//
// Industry-standard query-log mining shape:
//   - 归一化 + 去重：terms are normalized (lowercase/trim/collapse) before counting.
//   - 时间衰减：each occurrence is weighted by an exponential half-life so a term
//     that is hot today outranks one that was hot last month at equal raw counts.
//   - CTR 加权：impressions/clicks attributed to the term lift relevance, so a
//     term that reliably produces clicked results ranks above a noisy one.
//   - query→object 相关性：the most-clicked object ids per term are retained so the
//     ranking layer can favor objects that historically satisfy the term.
package queryheat

import (
	"math"
	"sort"
	"strings"
	"time"
)

// QueryRecord is one logged search request (write source: search_queries).
type QueryRecord struct {
	NormalizedTerm string
	CreatedAt      time.Time
	ResultCount    int
}

// FeedbackRecord is one logged interaction already joined to its query term
// (write source: SearchFeedbackFact.HeatReader joined with SearchRequestFact on
// searchRequestId; no sibling collection access).
// EventType uses the metadata vocabulary: impression|click|dwell|zero_result|…
type FeedbackRecord struct {
	NormalizedTerm string
	EventType      string
	ObjectID       string
	CreatedAt      time.Time
}

// TermHeat is the derived heat/relevance signal for one normalized search term.
// It is the single search-term truth consumed by both the search ranking layer
// (relatedTerms + heat boost) and the recommendation feature pipeline.
type TermHeat struct {
	NormalizedTerm string    `bson:"normalizedTerm" json:"normalizedTerm"`
	Frequency      int       `bson:"frequency" json:"frequency"`
	DecayedHeat    float64   `bson:"decayedHeat" json:"decayedHeat"`
	Impressions    int       `bson:"impressions" json:"impressions"`
	Clicks         int       `bson:"clicks" json:"clicks"`
	CTR            float64   `bson:"ctr" json:"ctr"`
	Relevance      float64   `bson:"relevance" json:"relevance"`
	LastSeen       time.Time `bson:"lastSeen" json:"lastSeen"`
	TopObjectIDs   []string  `bson:"topObjectIds,omitempty" json:"topObjectIds,omitempty"`
}

// Config tunes the mining. Zero values fall back to sane defaults so callers
// can pass an empty Config. Now is injectable for deterministic tests.
type Config struct {
	HalfLifeHours     float64 // recency half-life; older occurrences decay
	CTRBoost          float64 // how strongly CTR lifts relevance
	TopObjectsPerTerm int     // query→object relevance fan-out cap
	Now               func() time.Time
}

func (c Config) withDefaults() Config {
	if c.HalfLifeHours <= 0 {
		c.HalfLifeHours = 72 // 3 天半衰期：平衡近期热度与稳定性
	}
	if c.CTRBoost <= 0 {
		c.CTRBoost = 2.0
	}
	if c.TopObjectsPerTerm <= 0 {
		c.TopObjectsPerTerm = 5
	}
	if c.Now == nil {
		c.Now = time.Now
	}
	return c
}

// Compute mines the term heat/relevance table from raw query + feedback logs.
// Output is sorted by Relevance desc then term asc for stable, top-k friendly
// consumption.
func Compute(queries []QueryRecord, feedback []FeedbackRecord, cfg Config) []TermHeat {
	cfg = cfg.withDefaults()
	now := cfg.Now().UTC()
	halfLife := cfg.HalfLifeHours

	type agg struct {
		frequency   int
		decayedHeat float64
		impressions int
		clicks      int
		lastSeen    time.Time
		objectHits  map[string]int
	}
	table := map[string]*agg{}
	get := func(term string) *agg {
		a, ok := table[term]
		if !ok {
			a = &agg{objectHits: map[string]int{}}
			table[term] = a
		}
		return a
	}

	for _, q := range queries {
		term := strings.TrimSpace(q.NormalizedTerm)
		if term == "" {
			continue
		}
		a := get(term)
		a.frequency++
		a.decayedHeat += decayWeight(now, q.CreatedAt, halfLife)
		if q.CreatedAt.After(a.lastSeen) {
			a.lastSeen = q.CreatedAt
		}
	}

	for _, f := range feedback {
		term := strings.TrimSpace(f.NormalizedTerm)
		if term == "" {
			continue
		}
		a := get(term)
		switch strings.ToLower(strings.TrimSpace(f.EventType)) {
		case "impression":
			a.impressions++
		case "click":
			a.clicks++
			if id := strings.TrimSpace(f.ObjectID); id != "" {
				a.objectHits[id]++
			}
		}
		if f.CreatedAt.After(a.lastSeen) {
			a.lastSeen = f.CreatedAt
		}
	}

	out := make([]TermHeat, 0, len(table))
	for term, a := range table {
		ctr := 0.0
		if a.impressions > 0 {
			ctr = float64(a.clicks) / float64(a.impressions)
		}
		relevance := a.decayedHeat * (1 + cfg.CTRBoost*ctr)
		out = append(out, TermHeat{
			NormalizedTerm: term,
			Frequency:      a.frequency,
			DecayedHeat:    round4(a.decayedHeat),
			Impressions:    a.impressions,
			Clicks:         a.clicks,
			CTR:            round4(ctr),
			Relevance:      round4(relevance),
			LastSeen:       a.lastSeen,
			TopObjectIDs:   topObjects(a.objectHits, cfg.TopObjectsPerTerm),
		})
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Relevance == out[j].Relevance {
			return out[i].NormalizedTerm < out[j].NormalizedTerm
		}
		return out[i].Relevance > out[j].Relevance
	})
	return out
}

// RelatedTerms returns up to limit terms most relevant to query, ordered by
// relevance desc. Candidates are terms that share a token/substring with the
// query (so "成都" surfaces "成都 美食") or, when none match, the globally hottest
// terms (so a cold/empty query still gets useful suggestions). The query term
// itself is excluded.
func RelatedTerms(query string, heats []TermHeat, limit int) []TermHeat {
	q := NormalizeForMatch(query)
	if limit <= 0 {
		limit = 8
	}
	qTokens := strings.Fields(q)

	related := make([]TermHeat, 0, limit)
	fallback := make([]TermHeat, 0, limit)
	for _, h := range heats {
		term := NormalizeForMatch(h.NormalizedTerm)
		if term == "" || term == q {
			continue
		}
		if q != "" && termsOverlap(q, qTokens, term) {
			related = append(related, h)
		} else {
			fallback = append(fallback, h)
		}
	}
	// heats is already relevance-sorted, so the slices preserve that order.
	if len(related) >= limit || q == "" {
		if q == "" {
			return capTerms(fallback, limit)
		}
		return capTerms(related, limit)
	}
	combined := append(related, fallback...)
	return capTerms(combined, limit)
}

// HeatByTerm indexes a heat table by normalized term for O(1) ranking lookups.
func HeatByTerm(heats []TermHeat) map[string]TermHeat {
	idx := make(map[string]TermHeat, len(heats))
	for _, h := range heats {
		idx[h.NormalizedTerm] = h
	}
	return idx
}

func termsOverlap(q string, qTokens []string, term string) bool {
	if strings.Contains(term, q) || strings.Contains(q, term) {
		return true
	}
	for _, tok := range qTokens {
		if tok != "" && strings.Contains(term, tok) {
			return true
		}
	}
	return false
}

func capTerms(items []TermHeat, limit int) []TermHeat {
	if len(items) > limit {
		return items[:limit]
	}
	return items
}

func decayWeight(now, at time.Time, halfLifeHours float64) float64 {
	if at.IsZero() {
		return 1
	}
	ageHours := now.Sub(at.UTC()).Hours()
	if ageHours <= 0 {
		return 1
	}
	return math.Exp(-math.Ln2 * ageHours / halfLifeHours)
}

func topObjects(hits map[string]int, limit int) []string {
	if len(hits) == 0 {
		return nil
	}
	type kv struct {
		id    string
		count int
	}
	pairs := make([]kv, 0, len(hits))
	for id, c := range hits {
		pairs = append(pairs, kv{id, c})
	}
	sort.SliceStable(pairs, func(i, j int) bool {
		if pairs[i].count == pairs[j].count {
			return pairs[i].id < pairs[j].id
		}
		return pairs[i].count > pairs[j].count
	})
	if len(pairs) > limit {
		pairs = pairs[:limit]
	}
	out := make([]string, 0, len(pairs))
	for _, p := range pairs {
		out = append(out, p.id)
	}
	return out
}

// NormalizeForMatch lowercases, trims and collapses whitespace. It is a local,
// match-only normalizer; the canonical query normalization lives in
// runtime/search and is applied before a term ever reaches this package. The
// ranking layer reuses it so term↔hit matching shares one normalization.
func NormalizeForMatch(raw string) string {
	return strings.Join(strings.Fields(strings.ToLower(strings.TrimSpace(raw))), " ")
}

func round4(v float64) float64 {
	return math.Round(v*10000) / 10000
}
