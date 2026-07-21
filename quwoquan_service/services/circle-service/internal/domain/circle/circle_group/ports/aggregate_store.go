package ports

import (
	"context"
	"encoding/json"
	"time"

	groupmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_group/model"
)

type CommitRequest struct {
	Change           groupmodel.ChangeSet
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

type CommitReceipt struct {
	GroupID  string
	Version  int64
	Status   groupmodel.CircleGroupStatus
	Replayed bool
}

// NoopReceipt 持久化"目标状态已满足"的命名意图回执：
// 不递增 aggregate version、不产生 outbox 事件，相同 key 重放原始结果。
type NoopReceipt struct {
	GroupID          string
	Version          int64
	Status           groupmodel.CircleGroupStatus
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

type AggregateStore interface {
	Load(context.Context, string) (groupmodel.CircleGroup, bool, error)
	Commit(context.Context, CommitRequest) (CommitReceipt, error)
	RecordNoopReceipt(context.Context, NoopReceipt) (CommitReceipt, error)
}

// ConversationBindingWriter is the internal durable-event write port for the
// one-to-one CircleGroup.conversationId binding. No HTTP command receives this
// capability.
type ConversationBindingWriter interface {
	BindConversation(
		ctx context.Context,
		eventID string,
		circleID string,
		groupID string,
		conversationID string,
	) error
}

type CirclePolicySlice struct {
	CircleID string
	State    string
}

type CircleMembershipPolicySlice struct {
	PersonaID string
	Role      string
	State     string
}

type GroupMembershipPolicySlice struct {
	PersonaID string
	Role      string
	State     string
}

type PolicyReader interface {
	ReadCirclePolicy(context.Context, string) (CirclePolicySlice, bool, error)
	ReadCircleMembership(context.Context, string, string) (CircleMembershipPolicySlice, bool, error)
	ReadGroupMembership(context.Context, string, string) (GroupMembershipPolicySlice, bool, error)
	ReadParent(context.Context, string, string) (groupmodel.CircleGroup, bool, error)
	ParentChainContains(context.Context, string, string, string) (bool, error)
}

type GroupReadSlice struct {
	Group       groupmodel.CircleGroup
	MemberCount int64
}

type GroupPageSlice struct {
	Items  []GroupReadSlice
	Cursor string
}

type ListQuery struct {
	CircleID      string
	GroupType     string
	Visibility    string
	ParentGroupID string
	NodeType      string
	Cursor        string
	Limit         int
}

type SearchQuery struct {
	CircleID   string
	Query      string
	Visibility string
	GroupType  string
	Cursor     string
	Limit      int
}

type GroupReader interface {
	ReadGroup(context.Context, string, string) (GroupReadSlice, bool, error)
	ListGroups(context.Context, ListQuery) (GroupPageSlice, error)
	SearchGroups(context.Context, SearchQuery) (GroupPageSlice, error)
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
