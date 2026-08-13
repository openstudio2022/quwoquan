package application

import (
	"context"
	"errors"
	"log/slog"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application/queryheat"
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

// RankedPreparation is the AB-aware pre-query decision: the assigned bucket,
// the related-term envelope and the query-time BoostTerms the term_heat arm
// injects into the engine query. Ranking itself stays single-sourced in the
// recall engine (function_score + boost injection); nothing re-ranks after
// recall.
type RankedPreparation struct {
	ExperimentBucket string
	RelatedTerms     []string
	TopObjectIDs     []string
	BoostTerms       []rtsearch.BoostTerm
}

// TermHeatApplied reports whether the term_heat treatment actually injected
// boosts for this query (observability: search_retrieve_term_heat_applied_total).
func (p RankedPreparation) TermHeatApplied() bool {
	return p.ExperimentBucket == BucketTermHeat && len(p.BoostTerms) > 0
}

// RankingDecorator owns the AB-aware pre-query decision: it assigns the
// experiment bucket, fetches related terms and converts search-term heat into
// query-time BoostTerms under the term_heat arm. It is the single place
// search-term signals enter the search ranking decision — as query input, not
// as a post-recall re-rank (the engine order is the only ranking truth).
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

func (d *RankingDecorator) PolicyDigest() string {
	if d == nil || d.experiments == nil {
		return ""
	}
	return d.experiments.PolicyDigest()
}

// Prepare assigns the bucket, fetches related terms (best-effort) and, for the
// term_heat arm, converts the heat rows into bounded query-time BoostTerms.
// The caller injects them into the retrieve request before recall, so the
// engine's order is the final commercial order — Prepare never re-ranks.
func (d *RankingDecorator) Prepare(ctx context.Context, normalizedQuery, subjectKey string) (RankedPreparation, error) {
	if d == nil || d.experiments == nil {
		return RankedPreparation{}, errors.New("search ranking experiment policy is unavailable")
	}
	bucket, err := d.experiments.Assign(ctx, subjectKey)
	if err != nil {
		// Request path degrades to control when ExperimentPolicy is missing or
		// assignment transport is unhealthy (e.g. Redis DNS thrash).
		d.logger.WarnContext(ctx, "search experiment assignment degraded to control",
			slog.String("subjectKey", subjectKey), slog.String("err", err.Error()))
		bucket = BucketControl
	}
	out := RankedPreparation{ExperimentBucket: bucket}

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

	if bucket != BucketTermHeat || len(heats) == 0 {
		return out, nil
	}
	out.BoostTerms = d.boostTermsFor(heats)
	return out, nil
}

// boostTermsFor normalizes heat relevance against the hottest related term so
// every lift stays bounded by d.boost, regardless of absolute magnitudes.
func (d *RankingDecorator) boostTermsFor(heats []queryheat.TermHeat) []rtsearch.BoostTerm {
	maxRelevance := 0.0
	for _, h := range heats {
		if h.Relevance > maxRelevance {
			maxRelevance = h.Relevance
		}
	}
	if maxRelevance <= 0 {
		return nil
	}
	boosts := make([]rtsearch.BoostTerm, 0, len(heats))
	for _, h := range heats {
		term := strings.TrimSpace(h.NormalizedTerm)
		if term == "" || h.Relevance <= 0 {
			continue
		}
		boosts = append(boosts, rtsearch.BoostTerm{
			Term:   term,
			Weight: d.boost * (h.Relevance / maxRelevance),
		})
	}
	return boosts
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
