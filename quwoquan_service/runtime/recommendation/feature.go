package recommendation

import "context"

// UserFeatureVector holds precomputed user-level features for model scoring.
// Populated from the feature store (rm_recommend_feature projection) and
// augmented with derived metrics.
type UserFeatureVector struct {
	TagAffinities    map[string]float64 `json:"tagAffinities,omitempty"`
	AuthorAffinities map[string]float64 `json:"authorAffinities,omitempty"`
	TotalLikes       int                `json:"totalLikes"`
	TotalFavorites   int                `json:"totalFavorites"`
	TotalShares      int                `json:"totalShares"`
	TotalEvents      int                `json:"totalEvents"`
	EngagementRate   float64            `json:"engagementRate"`
}

// FeatureProvider supplies user-level features for scoring.
// Implemented by infrastructure/recommendation.FeatureStore (MongoDB) or
// NullFeatureProvider (when no feature store is configured).
type FeatureProvider interface {
	GetFeatures(ctx context.Context, userID string) (*UserFeatureVector, error)
}

// NullFeatureProvider returns nil features.
// Used when no feature store is configured; scoring falls back to session-only signals.
type NullFeatureProvider struct{}

func (*NullFeatureProvider) GetFeatures(_ context.Context, _ string) (*UserFeatureVector, error) {
	return nil, nil
}
