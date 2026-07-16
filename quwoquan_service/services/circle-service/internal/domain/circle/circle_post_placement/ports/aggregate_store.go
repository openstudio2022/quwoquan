package ports

import (
	"context"
	"encoding/json"
	"time"

	placementmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/model"
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

type AggregateStore interface {
	Load(context.Context, string) (placementmodel.CirclePostPlacement, bool, error)
	Commit(context.Context, CommitRequest) (CommitReceipt, error)
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

// PostLifecycleEvent is the typed cross-context fact consumed by Circle. It
// intentionally contains only the fields required to maintain PostOwnerView.
type PostLifecycleEvent struct {
	EventID        string
	EventType      string
	PostID         string
	PostVersion    int64
	OwnerPersonaID string
	State          string
	OccurredAt     time.Time
}

type PostLifecycleProjection interface {
	ApplyPostLifecycle(context.Context, PostLifecycleEvent) error
}

type PostLifecycleFailureStore interface {
	RecordPostLifecycleFailure(context.Context, string, string, error) (int64, error)
	ClearPostLifecycleFailure(context.Context, string) error
}
