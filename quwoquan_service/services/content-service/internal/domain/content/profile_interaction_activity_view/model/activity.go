package model

import (
	"strings"
	"time"
)

const (
	DirectionReceived = "received"
	DirectionSent     = "sent"

	TypeLike    = "like"
	TypeComment = "comment"
	TypeShare   = "share"
)

// Activity is one durable row in ProfileInteractionActivityView. The composite
// identity is OwnerPersonaID + Direction + ActivityID.
type Activity struct {
	OwnerPersonaID         string     `json:"-" bson:"ownerPersonaId"`
	ActivityID             string     `json:"activityId" bson:"activityId"`
	ActivityType           string     `json:"activityType" bson:"activityType"`
	Direction              string     `json:"direction" bson:"direction"`
	SourceType             string     `json:"-" bson:"sourceType"`
	SourceEventID          string     `json:"-" bson:"sourceEventId"`
	SourceVersion          int64      `json:"-" bson:"sourceVersion"`
	ViewerReactionVersion  int64      `json:"-" bson:"viewerReactionVersion"`
	TargetVersion          int64      `json:"-" bson:"targetVersion"`
	Active                 bool       `json:"-" bson:"active"`
	CommentKind            string     `json:"commentKind" bson:"commentKind"`
	CommentID              string     `json:"commentId,omitempty" bson:"commentId,omitempty"`
	ParentCommentID        string     `json:"parentCommentId,omitempty" bson:"parentCommentId,omitempty"`
	ViewerReaction         string     `json:"viewerReaction" bson:"viewerReaction"`
	ActorSubAccountID      string     `json:"actorSubAccountId" bson:"actorSubAccountId"`
	ActorDisplayName       string     `json:"actorDisplayName" bson:"actorDisplayName"`
	ActorAvatarURL         string     `json:"actorAvatarUrl,omitempty" bson:"actorAvatarUrl,omitempty"`
	ActorAvatarVersion     int64      `json:"actorAvatarVersion" bson:"actorAvatarVersion"`
	CounterpartSubAccountID string    `json:"counterpartSubAccountId,omitempty" bson:"counterpartSubAccountId,omitempty"`
	CounterpartDisplayName string     `json:"counterpartDisplayName,omitempty" bson:"counterpartDisplayName,omitempty"`
	CounterpartAvatarURL   string     `json:"counterpartAvatarUrl,omitempty" bson:"counterpartAvatarUrl,omitempty"`
	TargetSubAccountID     string     `json:"targetSubAccountId" bson:"targetSubAccountId"`
	TargetContentID        string     `json:"targetContentId" bson:"targetContentId"`
	TargetContentType      string     `json:"targetContentType" bson:"targetContentType"`
	TargetContentSummary   string     `json:"targetContentSummary,omitempty" bson:"targetContentSummary,omitempty"`
	TargetKind             string     `json:"targetKind" bson:"targetKind"`
	TargetAvailability     string     `json:"targetAvailability" bson:"targetAvailability"`
	TargetReplyCount       int64      `json:"targetReplyCount" bson:"targetReplyCount"`
	DisplaySubAccountID    string     `json:"displaySubAccountId" bson:"displaySubAccountId"`
	DisplayName            string     `json:"displayName" bson:"displayName"`
	DisplayAvatarURL       string     `json:"displayAvatarUrl,omitempty" bson:"displayAvatarUrl,omitempty"`
	DisplayAvatarVersion   int64      `json:"displayAvatarVersion" bson:"displayAvatarVersion"`
	DisplayUserRouteID     string     `json:"displayUserRouteId,omitempty" bson:"displayUserRouteId,omitempty"`
	PrimaryText            string     `json:"primaryText" bson:"primaryText"`
	ContextText            string     `json:"contextText,omitempty" bson:"contextText,omitempty"`
	PreviewMediaKind       string     `json:"previewMediaKind" bson:"previewMediaKind"`
	PreviewImageURL        string     `json:"previewImageUrl,omitempty" bson:"previewImageUrl,omitempty"`
	PreviewText            string     `json:"previewText,omitempty" bson:"previewText,omitempty"`
	PreviewUnavailable     bool       `json:"previewUnavailable" bson:"previewUnavailable"`
	PreviewObjectID        string     `json:"previewObjectId,omitempty" bson:"previewObjectId,omitempty"`
	PreviewRouteID         string     `json:"previewRouteId,omitempty" bson:"previewRouteId,omitempty"`
	OutboundShareEventID   string     `json:"outboundShareEventId,omitempty" bson:"outboundShareEventId,omitempty"`
	ShareText              string     `json:"shareText,omitempty" bson:"shareText,omitempty"`
	ImpactPrimaryText      string     `json:"impactPrimaryText,omitempty" bson:"impactPrimaryText,omitempty"`
	ImpactDeepLink         string     `json:"impactDeepLink,omitempty" bson:"impactDeepLink,omitempty"`
	FilterKeys             []string   `json:"filterKeys" bson:"filterKeys"`
	CreatedAt              time.Time  `json:"createdAt" bson:"createdAt"`
	OccurredAt             time.Time  `json:"occurredAt" bson:"occurredAt"`
	SeenAt                 *time.Time `json:"seenAt,omitempty" bson:"seenAt,omitempty"`
	ReadAt                 *time.Time `json:"readAt,omitempty" bson:"readAt,omitempty"`
}

func (a Activity) Valid() bool {
	return strings.TrimSpace(a.OwnerPersonaID) != "" &&
		strings.TrimSpace(a.ActivityID) != "" &&
		(a.Direction == DirectionReceived || a.Direction == DirectionSent) &&
		(a.ActivityType == TypeLike || a.ActivityType == TypeComment || a.ActivityType == TypeShare) &&
		strings.TrimSpace(a.SourceEventID) != "" &&
		a.SourceVersion > 0 &&
		strings.TrimSpace(a.ActorSubAccountID) != "" &&
		strings.TrimSpace(a.TargetSubAccountID) != "" &&
		strings.TrimSpace(a.TargetContentID) != "" &&
		!a.OccurredAt.IsZero()
}
