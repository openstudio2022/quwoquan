package post

import (
	"context"
	"time"
)

// ShareInteractionOccurrence 是一次不可变转发事实。列表方向由查询主体决定：
// targetSubAccountId=主体表示 received，actorSubAccountId=主体表示 initiated。
type ShareInteractionOccurrence struct {
	InteractionID           string    `json:"interactionId" bson:"interactionId"`
	ActorSubAccountID       string    `json:"actorSubAccountId" bson:"actorSubAccountId"`
	ActorDisplayName        string    `json:"actorDisplayName" bson:"actorDisplayName"`
	ActorAvatarURL          string    `json:"actorAvatarUrl" bson:"actorAvatarUrl"`
	CounterpartSubAccountID string    `json:"counterpartSubAccountId" bson:"counterpartSubAccountId"`
	CounterpartDisplayName  string    `json:"counterpartDisplayName" bson:"counterpartDisplayName"`
	CounterpartAvatarURL    string    `json:"counterpartAvatarUrl" bson:"counterpartAvatarUrl"`
	TargetSubAccountID      string    `json:"targetSubAccountId" bson:"targetSubAccountId"`
	TargetContentID         string    `json:"targetContentId" bson:"targetContentId"`
	TargetContentType       string    `json:"targetContentType" bson:"targetContentType"`
	TargetContentSummary    string    `json:"targetContentSummary" bson:"targetContentSummary"`
	TargetKind              string    `json:"targetKind" bson:"targetKind"`
	TargetAvailability      string    `json:"targetAvailability" bson:"targetAvailability"`
	TargetReplyCount        int64     `json:"targetReplyCount" bson:"targetReplyCount"`
	PreviewMediaKind        string    `json:"previewMediaKind" bson:"previewMediaKind"`
	PreviewImageURL         string    `json:"previewImageUrl" bson:"previewImageUrl"`
	PreviewText             string    `json:"previewText" bson:"previewText"`
	OutboundShareEventID    string    `json:"outboundShareEventId" bson:"outboundShareEventId"`
	ShareText               string    `json:"shareText" bson:"shareText"`
	ImpactPrimaryText       string    `json:"impactPrimaryText" bson:"impactPrimaryText"`
	ImpactDeepLink          string    `json:"impactDeepLink" bson:"impactDeepLink"`
	OccurredAt              time.Time `json:"occurredAt" bson:"occurredAt"`
	SeenAt                  time.Time `json:"seenAt,omitempty" bson:"seenAt,omitempty"`
	ReadAt                  time.Time `json:"readAt,omitempty" bson:"readAt,omitempty"`
}

type ShareInteractionQuery struct {
	SubAccountID string
	Direction    string
	CursorTime   time.Time
	CursorID     string
	Limit        int
}

// ShareInteractionStore 是转发互动唯一持久化读模型接口。
type ShareInteractionStore interface {
	Save(context.Context, ShareInteractionOccurrence) error
	List(context.Context, ShareInteractionQuery) ([]ShareInteractionOccurrence, bool, error)
	MarkState(context.Context, string, string, string, time.Time) error
}
