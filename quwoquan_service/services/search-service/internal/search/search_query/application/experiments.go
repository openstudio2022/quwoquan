package application

import (
	"context"
	"errors"
	"fmt"

	runtimeexperiments "quwoquan_service/runtime/experiments"
)

// SearchRankingExperimentID is the stable AB experiment id for search ranking.
// control = base CrossTypeRanker order; term_heat = search-term heat re-rank on.
const SearchRankingExperimentID = "search_ranking"

const (
	// BucketControl leaves the base ranking untouched (no search-term heat boost).
	BucketControl = "control"
	// BucketTermHeat applies the search-term heat boost so user search terms
	// participate in ranking; AB attribution compares it against control.
	BucketTermHeat = "term_heat"
)

// ExperimentBucket is one AB arm with its rollout weight.
type ExperimentBucket struct {
	Name      string
	WeightPct int
}

// ExperimentConfig is the complete search-ranking assignment policy supplied by
// service-owned runtime config. Runtime identity is derived from this content.
type ExperimentConfig struct {
	Enabled bool
	Buckets []ExperimentBucket
}

// Experiments deterministically buckets a subject into the search ranking AB,
// reusing the canonical FNV hash resolver (single hashing impl across services).
type Experiments struct {
	resolver *runtimeexperiments.HashResolver
}

// NewExperiments rejects missing or malformed policy; no implicit buckets or
// manual version identity exist on the runtime path.
func NewExperiments(cfg ExperimentConfig) (*Experiments, error) {
	buckets := make([]runtimeexperiments.BucketDef, 0, len(cfg.Buckets))
	for _, bucket := range cfg.Buckets {
		buckets = append(buckets, runtimeexperiments.BucketDef{
			Name:      bucket.Name,
			WeightPct: bucket.WeightPct,
		})
	}
	resolver := runtimeexperiments.NewHashResolver()
	if err := resolver.Register(&runtimeexperiments.Experiment{
		ID:      SearchRankingExperimentID,
		Buckets: buckets,
		Enabled: cfg.Enabled,
	}); err != nil {
		return nil, fmt.Errorf("search ranking experiment policy: %w", err)
	}
	return &Experiments{resolver: resolver}, nil
}

// Assign returns the deterministic bucket for one stable subject identity.
// Missing identity, resolver state, or enabled policy fails closed.
func (e *Experiments) Assign(ctx context.Context, subjectKey string) (string, error) {
	if e == nil || e.resolver == nil {
		return "", errors.New("search ranking experiment resolver is unavailable")
	}
	assignment, err := e.resolver.Resolve(ctx, SearchRankingExperimentID, subjectKey)
	if err != nil {
		return "", fmt.Errorf("assign search ranking experiment: %w", err)
	}
	if assignment.Bucket == "" {
		return "", errors.New("search ranking experiment returned an empty bucket")
	}
	return assignment.Bucket, nil
}
