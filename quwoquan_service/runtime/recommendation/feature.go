package recommendation

import (
	"context"
	"strings"
)

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
	// in lockstep with services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/feature_registry.yaml content_feed.user_features.
	SharedFolloweesCount      int     `json:"sharedFolloweesCount"`
	SharedCircleCount         int     `json:"sharedCircleCount"`
	CoCommentedCount          int     `json:"coCommentedCount"`
	CoVisitedEntityCount      int     `json:"coVisitedEntityCount"`
	FolloweeInObjectActive    int     `json:"followeeInObjectActive"`
	FolloweeViewingActive     int     `json:"followeeViewingActive"`
	AffinityIntersectionScore float64 `json:"affinityIntersectionScore"`
	IntersectionSourceRefTop  string  `json:"intersectionSourceRefTop,omitempty"`

	// IntersectionEdges 是「viewer ↔ 具体对象」的物化交集边，键为对象 ID
	// （人 / 地点 / 圈子 / 内容），值为交集图物化器真算的边权与新鲜度。
	//
	// 这是排序里唯一的「真实交集强度」来源。候选投影上的
	// intersectionFactStrength 是内容侧的交集承载力（该 post 自身挂了多少
	// entity/tag 提示），与 viewer 无关，不能当作 viewer 与该内容的交集强度使用；
	// 它继续作为离线训练特征回流，不参与在线事实通道融合。
	IntersectionEdges map[string]IntersectionEdgeFeature `json:"intersectionEdges,omitempty"`

	// Population segments (rule-based, from segments.yaml), computed by the
	// content-service InterestProfileAggregator and $set into rm_recommend_feature.
	// Priority-sorted; drive policy segment targeting (preset override / weight deltas)
	// and experiment eligibility without recomputation in the engine.
	Segments []string `json:"segments,omitempty"`

	// Embedding (Phase 5+, populated by dual-tower inference)
	UserEmbedding []float64 `json:"userEmbedding,omitempty"`
}

// IntersectionEdgeFeature 是 viewer 与单个对象之间的一条物化交集边。
// 真相源是 content-service 的 rm_viewer_object_intersection 快照：Weight 取
// 交集图物化器的 edgeWeight（关系强度 × 证据频率 × 新鲜度衰减），Freshness 取
// 同一条边的新鲜度衰减，Kind 取注册表 kind。三者都在异步物化时算好，
// 在线读路径只做点查与匹配，不重算图谱（R-IX01 读路径零同步打分）。
type IntersectionEdgeFeature struct {
	Weight    float64 `json:"weight"`
	Freshness float64 `json:"freshness"`
	Kind      string  `json:"kind,omitempty"`
}

// StrongestIntersectionEdge 返回 viewer 与该候选之间最强的物化交集边。
//
// 命中口径只有两处，因为对象级交集只能通过这两处与一条内容相连：
// 候选作者（人对象交集，如共同关注 / 同行）与候选 entityRefs
// （地点/实体对象交集，如都去过某地）。命不中即返回 false，调用方
// 必须按「无交集」处理，禁止回退到内容侧的交集承载力冒充 viewer 强度。
func (v *UserFeatureVector) StrongestIntersectionEdge(c ContentCandidate) (IntersectionEdgeFeature, bool) {
	return v.StrongestIntersectionEdgeFor(c.AuthorID, c.EntityRefs)
}

// StrongestIntersectionEdgeFor 是同一匹配口径的对象级入口，供在线评分与训练
// 特征快照共用，避免两侧各写一遍命中规则形成训练/在线偏斜。
func (v *UserFeatureVector) StrongestIntersectionEdgeFor(
	authorID string,
	entityRefs []string,
) (IntersectionEdgeFeature, bool) {
	if v == nil || len(v.IntersectionEdges) == 0 {
		return IntersectionEdgeFeature{}, false
	}
	best := IntersectionEdgeFeature{}
	found := false
	consider := func(objectID string) {
		objectID = strings.TrimSpace(objectID)
		if objectID == "" {
			return
		}
		edge, ok := v.IntersectionEdges[objectID]
		if !ok || edge.Weight <= 0 {
			return
		}
		if !found || edge.Weight > best.Weight {
			best = edge
			found = true
		}
	}
	consider(authorID)
	for _, ref := range entityRefs {
		consider(ref)
	}
	return best, found
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
