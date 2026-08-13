package ports

import (
	"context"
	"time"

	behaviormodel "quwoquan_service/services/content-service/internal/content/content_behavior_fact/domain/model"
	behaviorports "quwoquan_service/services/content-service/internal/content/content_behavior_fact/domain/ports"
	intersectionports "quwoquan_service/services/content-service/internal/content/intersection_visit_state/domain/ports"
)

// Compatibility within the source tree is a Go type identity alias, not a
// second wire or persistence model. ContentBehaviorFact remains the owner.
type BehaviorEventStore = behaviorports.FactStore
type RawBehaviorEvent = behaviormodel.Fact

// WishlistEventStore persists explicit want-to-go / wishlist intent facts.
// This is the stable source consumed by coWishlistedEntity intersection facts.
type WishlistEventStore interface {
	UpsertWishlistEvent(ctx context.Context, event WishlistEvent) error
}

// WishlistStateReader 提供当前用户对 canonical object 的私有意图状态。
// 查询只读 entity_wishlist_events，不加载 Post 聚合。
type WishlistStateReader interface {
	IsWishlisted(
		ctx context.Context,
		userID string,
		objectID string,
		objectKind string,
	) (bool, error)
}

type WishlistEvent struct {
	UserID         string
	EntityID       string
	ObjectType     string
	DisplayName    string
	Status         string
	SourceSurface  string
	ReferralSource string
	FeedRequestID  string
	SessionID      string
	ClientEventID  string
	CreatedAt      time.Time
	UpdatedAt      time.Time
}

type AuthorImpactSummary struct {
	AuthorID string             `json:"authorId" bson:"authorId"`
	Total    int64              `json:"total" bson:"total"`
	Items    []AuthorImpactItem `json:"items" bson:"items"`
}

type AuthorImpactItem struct {
	ImpactID              string                     `json:"impactId" bson:"-"`
	HelpType              string                     `json:"helpType" bson:"helpType"`
	Action                string                     `json:"action" bson:"action"`
	IntersectionDimension string                     `json:"intersectionDimension" bson:"intersectionDimension"`
	TagRef                string                     `json:"tagRef" bson:"tagRef"`
	Source                string                     `json:"source" bson:"source"`
	Count                 int64                      `json:"count" bson:"count"`
	PrimaryText           string                     `json:"primaryText" bson:"-"`
	SubtitleText          string                     `json:"subtitleText" bson:"-"`
	PrimarySpans          []map[string]any           `json:"primarySpans" bson:"-"`
	SampleVisuals         []map[string]any           `json:"sampleVisuals" bson:"-"`
	RepresentativeActor   *ImpactRepresentativeActor `json:"representativeActor,omitempty" bson:"-"`
	ActionHints           []ImpactActionHint         `json:"actionHints" bson:"-"`
	IconKey               string                     `json:"iconKey" bson:"-"`
	EvidenceSnapshotID    string                     `json:"evidenceSnapshotId" bson:"-"`
	CountObjectKind       string                     `json:"countObjectKind" bson:"-"`
	CountTarget           *ImpactTarget              `json:"countTarget,omitempty" bson:"-"`
	PropagationPath       map[string]any             `json:"propagationPath,omitempty" bson:"-"`
	FreshAt               string                     `json:"freshAt" bson:"-"`
	TimeBucket            string                     `json:"timeBucket" bson:"-"`
	LifecycleState        string                     `json:"lifecycleState" bson:"-"`
	PreviousStrength      float64                    `json:"previousStrength" bson:"-"`
	StrengthDelta         float64                    `json:"strengthDelta" bson:"-"`
	UpdatedAt             time.Time                  `json:"-" bson:"updatedAt"`
	// RepresentativeContentID is an internal hydration hint, never sent alone.
	RepresentativeContentID string `json:"-" bson:"-"`
}

type ImpactRepresentativeActor struct {
	ActorID       string        `json:"actorId"`
	DisplayName   string        `json:"displayName"`
	AvatarURL     string        `json:"avatarUrl"`
	RelationLabel string        `json:"relationLabel"`
	PrivacyState  string        `json:"privacyState"`
	Target        *ImpactTarget `json:"target,omitempty"`
	EvidenceRank  int           `json:"evidenceRank"`
}

type ImpactActionHint struct {
	ActionKey string        `json:"actionKey"`
	Label     string        `json:"label"`
	Target    *ImpactTarget `json:"target,omitempty"`
	IsPrimary bool          `json:"isPrimary"`
	Priority  int           `json:"priority"`
}

type ImpactTarget struct {
	ObjectID   string `json:"objectId"`
	ObjectKind string `json:"objectKind"`
	RouteID    string `json:"routeId"`
}

type AuthorImpactEvidenceRaw struct {
	EvidenceID            string
	ImpactID              string
	ContentID             string
	ContentType           string
	HelpType              string
	Action                string
	IntersectionDimension string
	OccurredAt            time.Time
}

// AuthorImpactProjectionReader is the only cross-context read port for the
// Recommendation-owned author-impact projection. Content uses it solely to
// decorate the summary and hydrate current Post visibility.
type AuthorImpactProjectionReader interface {
	GetSummary(ctx context.Context, authorID string, limit int64) (AuthorImpactSummary, error)
	ListPageWithTotal(ctx context.Context, authorID, impactID, cursor string, limit int64) ([]AuthorImpactEvidenceRaw, string, bool, int64, error)
}

// GatheringSocialProofSummary 是四锚点两级诚实社会证明计数的只读投影。
// Content 只做 App 代理透传，不落计数副本、不本地推断。
type GatheringSocialProofSummary struct {
	AnchorKind       string
	ObjectID         string
	PublishedCount   int64
	FormedCount      int64
	ExperiencedCount int64
}

// GatheringSocialProofProjectionReader is the only cross-context read port
// for the Recommendation-owned gathering social proof aggregation.
type GatheringSocialProofProjectionReader interface {
	GetGatheringSocialProof(
		ctx context.Context,
		anchorKind string,
		objectID string,
	) (GatheringSocialProofSummary, error)
}

type WatermarkStore = intersectionports.Store

// ProjectorEvent 是读模型投影器消费的规范化生命周期事件。
type ProjectorEvent struct {
	ID            string
	Type          string
	AggregateType string
	AggregateID   string
	Payload       map[string]any
	OccurredAt    time.Time
}

// Projector 将聚合生命周期事件应用到派生读模型。
type Projector interface {
	Project(ctx context.Context, event ProjectorEvent) error
}
