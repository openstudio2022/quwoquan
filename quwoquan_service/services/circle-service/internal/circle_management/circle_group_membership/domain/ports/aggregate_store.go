package ports

import (
	"context"
	"encoding/json"
	"time"

	model "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/domain/model"
)

type CommitRequest struct {
	Change           model.ChangeSet
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

type CommitReceipt struct {
	MembershipID string
	Version      int64
	Role         model.CircleGroupMembershipRole
	State        model.CircleGroupMembershipState
	Replayed     bool
}

type AggregateStore interface {
	Load(context.Context, string) (model.CircleGroupMembership, bool, error)
	LoadByIdentity(context.Context, string, string) (model.CircleGroupMembership, bool, error)
	Commit(context.Context, CommitRequest) (CommitReceipt, error)
}

type GroupPolicySlice struct {
	GroupID            string
	CircleID           string
	JoinPolicy         string
	Status             string
	CreatedByPersonaID string
	ConversationID     string
}

type GroupPolicyReader interface {
	ReadGroupPolicy(context.Context, string, string) (GroupPolicySlice, bool, error)
}

type CircleMembershipPolicyReader interface {
	IsActiveCircleMember(context.Context, string, string) (bool, error)
}

type MembershipPage struct {
	Items  []model.CircleGroupMembership
	Cursor string
}

type MembershipReader interface {
	ReadGroupMembership(context.Context, string, string) (model.CircleGroupMembership, bool, error)
	ListGroupMemberships(context.Context, string, string, int, string) (MembershipPage, error)
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
