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

	// Level-mapped features (0-5 scale, derived from raw counts)
	LikeLevel     int `json:"likeLevel"`
	FavoriteLevel int `json:"favoriteLevel"`
	ShareLevel    int `json:"shareLevel"`
	EventLevel    int `json:"eventLevel"`

	// Four-dimension tag affinities (Phase 2.1)
	TopicAffinities    map[string]float64 `json:"topicAffinities,omitempty"`
	AudienceAffinities map[string]float64 `json:"audienceAffinities,omitempty"`
	FormatAffinities   map[string]float64 `json:"formatAffinities,omitempty"`
	EntityAffinities   map[string]float64 `json:"entityAffinities,omitempty"`

	// Entity instance affinities (specific entities like places/brands)
	EntityInstanceAffinities map[string]float64 `json:"entityInstanceAffinities,omitempty"`

	// Content type engagement (ENER: Exposure-Normalized Engagement Rate)
	TypeENER         map[string]float64 `json:"typeENER,omitempty"`
	TypeConfidence   map[string]float64 `json:"typeConfidence,omitempty"`
	TypeExploreBonus map[string]float64 `json:"typeExploreBonus,omitempty"`

	// Depth engagement profile
	AvgEngagementDepth float64     `json:"avgEngagementDepth"`
	DepthDistribution  map[int]int `json:"depthDistribution,omitempty"`

	// Source distribution
	SourceDistribution map[string]int `json:"sourceDistribution,omitempty"`

	// Social features
	CircleTagAffinities map[string]float64 `json:"circleTagAffinities,omitempty"`
	SocialInterestScore float64            `json:"socialInterestScore"`
}

// MapCountToLevel maps a raw count to a 0-5 level using fixed thresholds.
// Thresholds: 0→0, 1-4→1, 5-19→2, 20-99→3, 100-499→4, 500+→5
func MapCountToLevel(count int) int {
	switch {
	case count <= 0:
		return 0
	case count < 5:
		return 1
	case count < 20:
		return 2
	case count < 100:
		return 3
	case count < 500:
		return 4
	default:
		return 5
	}
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
