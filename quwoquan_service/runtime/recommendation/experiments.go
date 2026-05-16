package recommendation

import (
	"context"

	experiments "quwoquan_service/runtime/experiments"
)

const (
	ExpRecWeights      = "rec_scoring_weights"
	ExpModelVsRule     = "rec_model_vs_rule"
	ExpModelVersion    = "rec_model_version"
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
		EntityAffinity:  1.0,
		TopicMatch:      1.2,
		AudienceMatch:   1.0,
		FormatMatch:     0.8,
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
		EntityAffinity:  1.2,
		TopicMatch:      0.8,
		AudienceMatch:   0.6,
		FormatMatch:     0.4,
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
		EntityAffinity:  1.0,
		TopicMatch:      0.6,
		AudienceMatch:   0.5,
		FormatMatch:     0.4,
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

// RegisterModelVsRuleExperiment registers the model-vs-rule scoring AB experiment.
func RegisterModelVsRuleExperiment(resolver *experiments.HashResolver) {
	resolver.Register(&experiments.Experiment{
		ID: ExpModelVsRule,
		Buckets: []experiments.BucketDef{
			{Name: "rule", WeightPct: 80},
			{Name: "model", WeightPct: 20},
		},
		PolicyVersion: "v1",
		Enabled:       true,
	})
}

// ResolveModelBucket determines whether a user should use rule or model scoring.
func ResolveModelBucket(ctx context.Context, resolver experiments.Resolver, userID string) string {
	if resolver == nil {
		return "rule"
	}
	assignment, err := resolver.Resolve(ctx, ExpModelVsRule, userID)
	if err != nil {
		return "rule"
	}
	return assignment.Bucket
}

// RegisterModelVersionExperiment registers the champion-vs-challenger model version AB experiment.
func RegisterModelVersionExperiment(resolver *experiments.HashResolver) {
	resolver.Register(&experiments.Experiment{
		ID: ExpModelVersion,
		Buckets: []experiments.BucketDef{
			{Name: "champion", WeightPct: 90},
			{Name: "challenger", WeightPct: 10},
		},
		PolicyVersion: "v1",
		Enabled:       true,
	})
}

// ResolveModelVersion determines which model version (champion/challenger) to use.
// Returns "champion" (production) or "challenger" (canary).
func ResolveModelVersion(ctx context.Context, resolver experiments.Resolver, userID string) string {
	if resolver == nil {
		return "champion"
	}
	assignment, err := resolver.Resolve(ctx, ExpModelVersion, userID)
	if err != nil {
		return "champion"
	}
	return assignment.Bucket
}
