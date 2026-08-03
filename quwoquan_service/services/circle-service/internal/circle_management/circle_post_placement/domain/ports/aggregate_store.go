package ports

import (
	"context"
	"encoding/json"
	"time"

	placementmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/model"
)

type CommitRequest struct {
	Change           placementmodel.ChangeSet
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

type CommitReceipt struct {
	PlacementID string
	Version     int64
	State       placementmodel.CirclePostPlacementState
	Replayed    bool
}

// NoopReceipt 持久化"目标状态已满足"的命名意图回执：
// 不递增 aggregate version、不产生 outbox 事件，相同 key 重放原始结果。
type NoopReceipt struct {
	PlacementID      string
	Version          int64
	State            placementmodel.CirclePostPlacementState
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

type AggregateStore interface {
	Load(context.Context, string) (placementmodel.CirclePostPlacement, bool, error)
	Commit(context.Context, CommitRequest) (CommitReceipt, error)
	RecordNoopReceipt(context.Context, NoopReceipt) (CommitReceipt, error)
}

type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          json.RawMessage
	OccurredAt       time.Time
	Checkpoint       string
}

type OutboxReader interface {
	ReadAfter(context.Context, string, int) ([]OutboxEvent, error)
}

type ProjectionCheckpointStore interface {
	LoadCheckpoint(context.Context, string) (string, error)
	SaveCheckpoint(context.Context, string, string) error
}

type OutboxPublisher interface {
	Publish(context.Context, OutboxEvent) error
}

type CirclePolicySlice struct {
	CircleID       string
	OwnerPersonaID string
	State          string
}

type CirclePolicyReader interface {
	ReadCirclePolicy(context.Context, string) (CirclePolicySlice, bool, error)
}

type GroupPolicySlice struct {
	GroupID  string
	CircleID string
	State    string
}

type GroupPolicyReader interface {
	ReadGroupPolicy(context.Context, string) (GroupPolicySlice, bool, error)
}

type PostOwnerSlice struct {
	PostID         string
	OwnerPersonaID string
	State          string
}

// PostOwnerReader is the named read boundary over the Content projection. The
// placement aggregate never loads or imports the Post aggregate.
type PostOwnerReader interface {
	ReadPostOwner(context.Context, string) (PostOwnerSlice, bool, error)
}

type MembershipRoleSlice struct {
	CircleID  string
	PersonaID string
	Role      string
	State     string
}

type MembershipRoleReader interface {
	ReadMembershipRole(context.Context, string, string) (MembershipRoleSlice, bool, error)
}

type PolicyReaders struct {
	Circles     CirclePolicyReader
	Groups      GroupPolicyReader
	Posts       PostOwnerReader
	Memberships MembershipRoleReader
}

// PostLifecycleEvent is the typed cross-context fact consumed by Circle. The
// optional feed snapshot is present only for lifecycle events that can keep a
// public CircleFeedItem projection alive; removal/redaction facts carry only
// identity, version and owner state.
type PostLifecycleEvent struct {
	EventID        string
	EventType      string
	PostID         string
	PostVersion    int64
	OwnerPersonaID string
	State          string
	Visibility     string
	Moderation     string
	FeedItem       *PostFeedItemSnapshot
	OccurredAt     time.Time
}

// PostFeedItemSnapshot is the Content-owned public Post slice copied into the
// Circle boundary by the typed lifecycle stream. It is a projection payload,
// never a second Post aggregate or an authority for Content mutations.
type PostFeedItemSnapshot struct {
	ContentType        string
	ContentIdentity    string
	AssistantUsePolicy string
	AuthorDisplayName  string
	AuthorAvatarURL    string
	Title              string
	Body               string
	Summary            string
	CoverURL           string
	MediaURLs          []string
	VideoURL           string
	ThumbnailURL       string
	Width              int64
	Height             int64
	DurationMs         int64
	LikeCount          int64
	CommentCount       int64
	ShareCount         int64
	ContentVertical    string
	CreatedAt          time.Time
	UpdatedAt          time.Time
	PublishedAt        time.Time
}

type PostLifecycleProjection interface {
	ApplyPostLifecycle(context.Context, PostLifecycleEvent) error
}

type PostLifecycleFailureStore interface {
	RecordPostLifecycleFailure(context.Context, string, string, error) (int64, error)
	ClearPostLifecycleFailure(context.Context, string) error
}
