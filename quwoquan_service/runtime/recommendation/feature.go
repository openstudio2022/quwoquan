package recommendation

import "context"

// UserFeatureVector holds precomputed user-level features for model scoring.
// Populated from the feature store (rm_recommend_feature projection) and
// augmented with derived metrics.
type UserFeatureVector struct {
	TagAffinities    map[string]float64 `json:"tagAffinities,omitempty"`
	AuthorAffinities map[string]float64 `json:"authorAffinities,omitempty"`
	TotalLikes       int                `json:"totalLikes"`
	TotalShares      int                `json:"totalShares"`
	TotalEvents      int                `json:"totalEvents"`
	EngagementRate   float64            `json:"engagementRate"`

	// Level-mapped features (0-5 scale, derived from raw counts)
	LikeLevel  int `json:"likeLevel"`
	ShareLevel int `json:"shareLevel"`
	EventLevel int `json:"eventLevel"`

	// Four-dimension tag affinities (Phase 2.1)
	TopicAffinities    map[string]float64 `json:"topicAffinities,omitempty"`
	AudienceAffinities map[string]float64 `json:"audienceAffinities,omitempty"`
	FormatAffinities   map[string]float64 `json:"formatAffinities,omitempty"`
	EntityAffinities   map[string]float64 `json:"entityAffinities,omitempty"`

	// Entity instance affinities (specific entities like places/brands)
	EntityInstanceAffinities map[string]float64 `json:"entityInstanceAffinities,omitempty"`

	// Content type engagement (ENER: Exposure-Normalized Engagement Rate)
	TypeENER map[string]float64 `json:"typeENER,omitempty"`

	// Depth engagement profile (keys: "L0".."L4")
	AvgEngagementDepth float64        `json:"avgEngagementDepth"`
	DepthDistribution  map[string]int `json:"depthDistribution,omitempty"`

	// Recent search intent features (24h freshness-gated by FeatureStore).
	SearchTermAffinities      map[string]float64 `json:"searchTermAffinities,omitempty"`
	SearchTopObjectAffinities map[string]float64 `json:"searchTopObjectAffinities,omitempty"`
	SearchTermHeat            float64            `json:"searchTermHeat,omitempty"`

	// Social features
	CircleTagAffinities map[string]float64 `json:"circleTagAffinities,omitempty"`
	SocialInterestScore float64            `json:"socialInterestScore"`

	// Intersection features (fact channel + affinity probability channel),
	// aligned with IntersectionReason (§5.4 kind registry). Fact signals must
	// outrank the affinity channel in ranking fusion; AffinityIntersectionScore
	// is advisory only and never overrides a confirmed fact intersection.
	// Sourced from rm_recommend_feature.socialFeatures.intersection.* and kept
	// in lockstep with services/rec-model-service/scripts/feature_registry.yaml content_feed.user_features.
	SharedFolloweesCount      int     `json:"sharedFolloweesCount"`
	SharedCircleCount         int     `json:"sharedCircleCount"`
	CoCommentedCount          int     `json:"coCommentedCount"`
	CoVisitedEntityCount      int     `json:"coVisitedEntityCount"`
	FolloweeInObjectActive    int     `json:"followeeInObjectActive"`
	FolloweeViewingActive     int     `json:"followeeViewingActive"`
	AffinityIntersectionScore float64 `json:"affinityIntersectionScore"`
	IntersectionSourceRefTop  string  `json:"intersectionSourceRefTop,omitempty"`

	// Population segments (rule-based, from segments.yaml), computed by the
	// content-service InterestProfileAggregator and $set into rm_recommend_feature.
	// Priority-sorted; drive policy segment targeting (preset override / weight deltas)
	// and experiment eligibility without recomputation in the engine.
	Segments []string `json:"segments,omitempty"`

	// Embedding (Phase 5+, populated by dual-tower inference)
	UserEmbedding []float64 `json:"userEmbedding,omitempty"`
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
