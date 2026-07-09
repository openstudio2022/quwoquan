package ports

import (
	"context"
	"time"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
)

// PostRepository defines the post storage operations consumed by application use cases.
type PostRepository interface {
	Create(ctx context.Context, post *postmodel.Post) error
	Update(ctx context.Context, id string, post *postmodel.Post) bool
	FindByID(ctx context.Context, id string) (*postmodel.Post, bool)
	ListAll(ctx context.Context) []postmodel.Post
	ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post
	ListByAuthor(ctx context.Context, authorID string, limit int, cursor string) []postmodel.Post
	AdjustCommentCount(ctx context.Context, postID string, delta int64) (int64, bool, error)
	SetCommentCount(ctx context.Context, postID string, count int64) (bool, error)
}

// ReportRepository defines the report persistence port consumed by report use cases.
type ReportRepository interface {
	Create(ctx context.Context, report *reportmodel.Report) error
	FindByID(ctx context.Context, id string) (*reportmodel.Report, bool, error)
	Update(ctx context.Context, report *reportmodel.Report) error
	List(ctx context.Context, limit int) ([]*reportmodel.Report, error)
}

// Projector receives domain events for in-process read-model projection.
type Projector interface {
	Project(ctx context.Context, event ProjectorEvent) error
}

type ProjectorEvent struct {
	Type          string         `json:"type"`
	AggregateType string         `json:"aggregateType"`
	AggregateID   string         `json:"aggregateId"`
	Payload       map[string]any `json:"payload"`
	OccurredAt    time.Time      `json:"occurredAt"`
}

// BehaviorEventStore persists raw behavior events for offline analytics.
type BehaviorEventStore interface {
	InsertBatch(ctx context.Context, events []RawBehaviorEvent) error
	ListUserFootprint(ctx context.Context, userID string, actions []string, before time.Time, limit int) ([]RawBehaviorEvent, error)
}

// RawBehaviorEvent is the persistent form of a user behavior event.
type RawBehaviorEvent struct {
	ClientEventID          string    `bson:"clientEventId,omitempty"`
	State                  string    `bson:"state,omitempty"`
	UserID                 string    `bson:"userId"`
	DeviceActorID          string    `bson:"deviceActorId,omitempty"`
	SessionID              string    `bson:"sessionId"`
	ContentID              string    `bson:"contentId"`
	Action                 string    `bson:"action"`
	Tags                   []string  `bson:"tagRefs,omitempty"`
	Duration               float64   `bson:"duration,omitempty"`
	AuthorID               string    `bson:"authorId,omitempty"`
	ReferralSource         string    `bson:"referralSource,omitempty"`
	EngagementDepth        int       `bson:"engagementDepth,omitempty"`
	ConsumedRatio          float64   `bson:"consumedRatio,omitempty"`
	TotalUnits             int       `bson:"totalUnits,omitempty"`
	EntityRefs             []string  `bson:"entityRefs,omitempty"`
	FeedRequestID          string    `bson:"feedRequestId,omitempty"`
	Position               int       `bson:"position,omitempty"`
	CommentLength          int       `bson:"commentLength,omitempty"`
	ChannelID              string    `bson:"channelId,omitempty"`
	RankingVersion         string    `bson:"rankingVersion,omitempty"`
	ReasonVersion          string    `bson:"reasonVersion,omitempty"`
	RecallPath             string    `bson:"recallPath,omitempty"`
	ContentVertical        string    `bson:"contentVertical,omitempty"`
	SupplySource           string    `bson:"supplySource,omitempty"`
	IntersectionDimension  string    `bson:"intersectionDimension,omitempty"`
	IntersectionTagRefs    []string  `bson:"intersectionTagRefs,omitempty"`
	IntersectionID         string    `bson:"intersectionId,omitempty"`
	IntersectionClass      string    `bson:"intersectionClass,omitempty"`
	IntersectionSourceRef  string    `bson:"intersectionSourceRef,omitempty"`
	IntersectionEvidenceID string    `bson:"intersectionEvidenceId,omitempty"`
	OccurredAt             string    `bson:"occurredAt"`
	CreatedAt              time.Time `bson:"createdAt"`
}

// WishlistEventStore persists explicit want-to-go / wishlist intent facts.
// This is the stable source consumed by coWishlistedEntity intersection facts.
type WishlistEventStore interface {
	UpsertWishlistEvent(ctx context.Context, event WishlistEvent) error
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

const (
	DailyMetricDimensionAction       = "action"
	DailyMetricDimensionContent      = "content"
	DailyMetricDimensionAuthor       = "author"
	DailyMetricDimensionIntersection = "intersection"
)

var DailyMetricDimensions = []string{
	DailyMetricDimensionAction,
	DailyMetricDimensionContent,
	DailyMetricDimensionAuthor,
	DailyMetricDimensionIntersection,
}

type DailyMetricsStore interface {
	IncrementMetric(ctx context.Context, date, dimension, dimensionKey, action string, dwellMs int64, depth int) error
}

type DailyMetric struct {
	Date                  string    `bson:"date"`
	Dimension             string    `bson:"dimension"`
	DimensionKey          string    `bson:"dimensionKey"`
	Impressions           int64     `bson:"impressions"`
	Clicks                int64     `bson:"clicks"`
	Dwells                int64     `bson:"dwells"`
	Likes                 int64     `bson:"likes"`
	Shares                int64     `bson:"shares"`
	Comments              int64     `bson:"comments"`
	Dislikes              int64     `bson:"dislikes"`
	Reports               int64     `bson:"reports"`
	FollowConversions     int64     `bson:"followConversions"`
	JoinCircleConversions int64     `bson:"joinCircleConversions"`
	AddContactConversions int64     `bson:"addContactConversions"`
	TotalDwellMs          int64     `bson:"totalDwellMs"`
	AvgDepth              float64   `bson:"avgDepth"`
	UniqueUsers           int64     `bson:"uniqueUsers"`
	CreatedAt             time.Time `bson:"createdAt"`
}

type AuthorImpactEvent struct {
	AuthorID              string
	Action                string
	HelpType              string
	IntersectionDimension string
	IntersectionTagRefs   []string
	Source                string
	OccurredAt            time.Time
}

type AuthorImpactStore interface {
	Record(ctx context.Context, event AuthorImpactEvent) error
	GetSummary(ctx context.Context, authorID string, limit int64) (AuthorImpactSummary, error)
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
	RepresentativeActor   *ImpactRepresentativeActor `json:"representativeActor,omitempty" bson:"-"`
	ActionHints           []ImpactActionHint         `json:"actionHints" bson:"-"`
	IconKey               string                     `json:"iconKey" bson:"-"`
	CountObjectKind       string                     `json:"countObjectKind,omitempty" bson:"-"`
	CountTarget           *ImpactTarget              `json:"countTarget,omitempty" bson:"-"`
	UpdatedAt             time.Time                  `json:"updatedAt" bson:"updatedAt"`
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

type AuthorImpactEvidenceRecord struct {
	AuthorID              string
	ImpactID              string
	SourceEventID         string
	ActorID               string
	ContentID             string
	ContentType           string
	HelpType              string
	Action                string
	IntersectionDimension string
	TagRef                string
	Source                string
	OccurredAt            time.Time
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

type AuthorImpactEvidenceStore interface {
	Record(ctx context.Context, rec AuthorImpactEvidenceRecord) error
	CountByImpact(ctx context.Context, authorID, impactID string) (int64, error)
	ListPageWithTotal(ctx context.Context, authorID, impactID, cursor string, limit int64) ([]AuthorImpactEvidenceRaw, string, bool, int64, error)
}

type WatermarkStore interface {
	LoadWatermarks(ctx context.Context, userID string) (map[string]int64, error)
	SaveWatermarks(ctx context.Context, userID string, dims map[string]int64) error
}
