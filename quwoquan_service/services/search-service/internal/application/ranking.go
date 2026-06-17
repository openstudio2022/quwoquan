package application

import (
	"context"
	"log/slog"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/application/queryheat"
)

// RelatedTermsLimit caps the relatedTerms envelope + the heat boost fan-out.
const RelatedTermsLimit = 8

// DefaultTermHeatBoost is the max score lift a single fully-hot related term
// adds under the term_heat AB arm. It is comparable to a strong tag/term hit so
// search-term heat meaningfully reorders without drowning text relevance.
const DefaultTermHeatBoost = 1.5

// TermHeatProvider supplies the derived search-term heat for ranking + suggest.
// Implemented in infrastructure (reads the rm_search_term_heat read model). It
// is best-effort: a nil provider or an error degrades to base ranking, never a
// failed search.
type TermHeatProvider interface {
	// RelatedTerms returns up to limit heat rows most relevant to normalizedQuery,
	// ordered by relevance desc. The query term itself is excluded.
	RelatedTerms(ctx context.Context, normalizedQuery string, limit int) ([]queryheat.TermHeat, error)
}

// RankedResult is the enriched, AB-aware ranking output the HTTP layer renders.
// Hits carry the (possibly re-ranked) order with RankPosition/RankReasons; the
// envelope fields back the commercial search contract.
type RankedResult struct {
	Hits             []rtsearch.RetrieveHit
	RelatedTerms     []string
	TopObjectIDs     []string
	ExperimentBucket string
	RankingVersion   string
}

// RankingDecorator turns a base RetrieveResponse into a commercial, AB-aware
// result: it assigns the experiment bucket, attaches relatedTerms, and — under
// the term_heat arm — folds search-term heat into the score so user search
// terms genuinely participate in ranking. It is the single place search-term
// signals enter the search ranking decision.
type RankingDecorator struct {
	termHeat    TermHeatProvider
	experiments *Experiments
	boost       float64
	logger      *slog.Logger
}

// NewRankingDecorator wires the decorator. termHeat may be nil (relatedTerms
// empty + no heat boost). A non-positive boost falls back to DefaultTermHeatBoost.
func NewRankingDecorator(termHeat TermHeatProvider, experiments *Experiments, boost float64, logger *slog.Logger) *RankingDecorator {
	if boost <= 0 {
		boost = DefaultTermHeatBoost
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &RankingDecorator{termHeat: termHeat, experiments: experiments, boost: boost, logger: logger}
}

// Decorate assigns the bucket, fetches related terms (best-effort) and, for the
// term_heat arm, re-ranks hits by blending the base score with the search-term
// heat boost. RankPosition is renumbered after any re-rank so the published
// position always matches the returned order.
func (d *RankingDecorator) Decorate(ctx context.Context, resp rtsearch.RetrieveResponse, normalizedQuery, subjectKey string) RankedResult {
	bucket := d.experiments.Assign(ctx, subjectKey)
	out := RankedResult{
		Hits:             resp.Hits,
		ExperimentBucket: bucket,
		RankingVersion:   RankingVersion,
	}

	var heats []queryheat.TermHeat
	if d.termHeat != nil {
		fetched, err := d.termHeat.RelatedTerms(ctx, normalizedQuery, RelatedTermsLimit)
		if err != nil {
			// Best-effort: degrade to base ranking, never fail the search.
			d.logger.WarnContext(ctx, "search related-terms lookup failed (best-effort, base ranking served)",
				slog.String("query", normalizedQuery), slog.String("err", err.Error()))
		} else {
			heats = fetched
		}
	}
	out.RelatedTerms = termNames(heats)
	out.TopObjectIDs = topObjectIDs(heats)

	if bucket != BucketTermHeat || len(heats) == 0 || len(resp.Hits) == 0 {
		return out
	}
	out.Hits = d.applyTermHeatBoost(resp.Hits, heats)
	return out
}

// applyTermHeatBoost lifts each hit by the heat of related terms it matches,
// re-sorts, appends a transparent "search.term_heat" reason, and renumbers
// RankPosition. The boost is normalized against the hottest related term so it
// stays bounded by d.boost regardless of absolute relevance magnitudes.
func (d *RankingDecorator) applyTermHeatBoost(hits []rtsearch.RetrieveHit, heats []queryheat.TermHeat) []rtsearch.RetrieveHit {
	maxRelevance := 0.0
	for _, h := range heats {
		if h.Relevance > maxRelevance {
			maxRelevance = h.Relevance
		}
	}
	if maxRelevance <= 0 {
		return hits
	}

	boosted := make([]rtsearch.RetrieveHit, len(hits))
	copy(boosted, hits)
	for i := range boosted {
		hay := hitHaystack(boosted[i])
		matched := 0.0
		var matchedTerms []string
		for _, h := range heats {
			term := queryheat.NormalizeForMatch(h.NormalizedTerm)
			if term == "" || !strings.Contains(hay, term) {
				continue
			}
			if h.Relevance > matched {
				matched = h.Relevance
			}
			matchedTerms = append(matchedTerms, h.NormalizedTerm)
		}
		if matched <= 0 {
			continue
		}
		lift := d.boost * (matched / maxRelevance)
		boosted[i].Score += lift
		boosted[i].RankReasons = append(boosted[i].RankReasons, rtsearch.Reason{
			Code:   "search.term_heat",
			Label:  "热搜词加权：" + strings.Join(matchedTerms, "、"),
			Weight: lift,
		})
	}

	// Reuse the single repeatable total order (Score desc -> Title asc ->
	// Target asc -> ObjectID asc) so the term_heat re-rank produces the same
	// deterministic page as the base recall merge — no second sort truth.
	rtsearch.SortHitsStable(boosted)
	for i := range boosted {
		boosted[i].RankPosition = i + 1
	}
	return boosted
}

func hitHaystack(hit rtsearch.RetrieveHit) string {
	parts := make([]string, 0, 4+len(hit.MatchedTerms)+len(hit.MatchedTags))
	parts = append(parts, hit.Title, hit.Snippet)
	parts = append(parts, hit.MatchedTerms...)
	parts = append(parts, hit.MatchedTags...)
	return queryheat.NormalizeForMatch(strings.Join(parts, " "))
}

func termNames(heats []queryheat.TermHeat) []string {
	if len(heats) == 0 {
		return nil
	}
	out := make([]string, 0, len(heats))
	for _, h := range heats {
		if t := strings.TrimSpace(h.NormalizedTerm); t != "" {
			out = append(out, t)
		}
	}
	return out
}

func topObjectIDs(heats []queryheat.TermHeat) []string {
	if len(heats) == 0 {
		return nil
	}
	seen := map[string]struct{}{}
	out := make([]string, 0, len(heats))
	for _, h := range heats {
		for _, id := range h.TopObjectIDs {
			id = strings.TrimSpace(id)
			if id == "" {
				continue
			}
			if _, ok := seen[id]; ok {
				continue
			}
			seen[id] = struct{}{}
			out = append(out, id)
		}
	}
	return out
}
