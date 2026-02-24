package recommendation

import (
	"context"

	experiments "quwoquan_service/runtime/experiments"
)

const (
	ExpRecWeights = "rec_scoring_weights"
)

// WeightPresets defines named weight configurations for AB testing.
var WeightPresets = map[string]ScoringWeights{
	"control": DefaultWeights(),
	"engagement_heavy": {
		TagRelevance:    2.0,
		AuthorAffinity:  1.0,
		Popularity:      4.0,
		Freshness:       1.0,
		SocialPrior:     0.5,
		ExploreBoost:    0.3,
		NegativePenalty: 5.0,
		DwellBonus:      1.5,
	},
	"freshness_heavy": {
		TagRelevance:    2.5,
		AuthorAffinity:  1.5,
		Popularity:      1.5,
		Freshness:       4.0,
		SocialPrior:     1.0,
		ExploreBoost:    0.8,
		NegativePenalty: 5.0,
		DwellBonus:      0.5,
	},
	"explore_heavy": {
		TagRelevance:    2.0,
		AuthorAffinity:  1.0,
		Popularity:      1.5,
		Freshness:       1.5,
		SocialPrior:     1.0,
		ExploreBoost:    2.0,
		NegativePenalty: 5.0,
		DwellBonus:      0.5,
	},
}

// ResolveWeights determines scoring weights for a user via AB experiment assignment.
func ResolveWeights(ctx context.Context, resolver experiments.Resolver, userID string) ScoringWeights {
	if resolver == nil {
		return DefaultWeights()
	}

	assignment, err := resolver.Resolve(ctx, ExpRecWeights, userID)
	if err != nil {
		return DefaultWeights()
	}

	if preset, ok := WeightPresets[assignment.Bucket]; ok {
		return preset
	}
	return DefaultWeights()
}

// RegisterRecWeightsExperiment registers the recommendation weights AB experiment.
func RegisterRecWeightsExperiment(resolver *experiments.HashResolver) {
	resolver.Register(&experiments.Experiment{
		ID: ExpRecWeights,
		Buckets: []experiments.BucketDef{
			{Name: "control", WeightPct: 60},
			{Name: "engagement_heavy", WeightPct: 15},
			{Name: "freshness_heavy", WeightPct: 15},
			{Name: "explore_heavy", WeightPct: 10},
		},
		PolicyVersion: "v1",
		Enabled:       true,
	})
}
