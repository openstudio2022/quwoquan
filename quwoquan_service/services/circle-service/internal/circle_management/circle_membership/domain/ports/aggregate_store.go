package ports

import (
	"context"
	"encoding/json"
	"time"

	circlemodel "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
	membershipmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/model"
)

type CommitRequest struct {
	Change           membershipmodel.ChangeSet
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

type CommitReceipt struct {
	MembershipID string
	Version      int64
	State        membershipmodel.CircleMembershipState
	Role         membershipmodel.CircleMemberRole
	Replayed     bool
}

type AggregateStore interface {
	Load(context.Context, string) (membershipmodel.CircleMembership, bool, error)
	LoadByIdentity(context.Context, string, string) (membershipmodel.CircleMembership, bool, error)
	Commit(context.Context, CommitRequest) (CommitReceipt, error)
}

type CirclePolicySlice struct {
	CircleID       string
	OwnerPersonaID string
	State          string
	JoinPolicy     string
}

type CirclePolicyReader interface {
	ReadCirclePolicy(context.Context, string) (CirclePolicySlice, bool, error)
}

type MembershipSlice struct {
	Items  []membershipmodel.CircleMembership
	Cursor string
}

type MembershipReader interface {
	ReadCircleMembership(context.Context, string, string) (membershipmodel.CircleMembership, bool, error)
	ListCircleMemberships(context.Context, string, int, string) (MembershipSlice, error)
	// ListPendingCircleMemberships 返回待审批（state=pending）成员申请队列，
	// 仅供 owner/admin 审批面消费。
	ListPendingCircleMemberships(context.Context, string, int, string) (MembershipSlice, error)
}

// CircleSummary is a named read projection; it is not the Circle aggregate
// and cannot be passed to a Circle command or Store.
type CircleSummary struct {
	ID                       string                               `json:"circleId"`
	Name                     string                               `json:"name"`
	Description              string                               `json:"description"`
	CoverURL                 string                               `json:"coverUrl"`
	IconURL                  string                               `json:"iconUrl"`
	OwnerPersonaID           string                               `json:"ownerPersonaId"`
	OwnerDisplayNameSnapshot string                               `json:"ownerDisplayNameSnapshot"`
	Category                 string                               `json:"category"`
	SubCategory              string                               `json:"subCategory"`
	Tags                     []string                             `json:"tags"`
	MemberCount              int64                                `json:"memberCount"`
	PostCount                int64                                `json:"postCount"`
	WeeklyActiveCount        int64                                `json:"weeklyActiveCount"`
	Status                   circlemodel.CircleStatus             `json:"status"`
	Visibility               circlemodel.CircleVisibility         `json:"visibility"`
	JoinPolicy               circlemodel.CircleJoinPolicy         `json:"joinPolicy"`
	Kind                     circlemodel.CircleKind               `json:"kind"`
	DisplaySubjectType       circlemodel.CircleDisplaySubjectType `json:"displaySubjectType"`
	FollowEnabled            bool                                 `json:"followEnabled"`
	DefaultPublicGroupID     string                               `json:"defaultPublicGroupId"`
	LinkedHomepageID         string                               `json:"linkedHomepageId"`
	LinkedHomepageType       circlemodel.HomepageType             `json:"linkedHomepageType"`
	LinkedHomepageTitle      string                               `json:"linkedHomepageTitle"`
	CreatedAt                time.Time                            `json:"createdAt"`
	UpdatedAt                time.Time                            `json:"updatedAt"`
}

type PersonaCircleQuery struct {
	PersonaID       string
	ViewerPersonaID string
	Query           string
	Limit           int
	Cursor          string
}

type PersonaCircleSlice struct {
	Items  []CircleSummary
	Cursor string
}

type PersonaCircleReader interface {
	ListPersonaCircles(context.Context, PersonaCircleQuery) (PersonaCircleSlice, error)
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
