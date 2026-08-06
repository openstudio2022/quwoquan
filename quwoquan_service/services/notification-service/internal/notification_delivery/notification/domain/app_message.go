package notification

import "time"

type AppMessageDestination struct {
	Type string `bson:"type" json:"type"`
	ID   string `bson:"id" json:"id"`
}

type AppMessageRouteQuery struct {
	Dimension string `bson:"dimension,omitempty" json:"dimension,omitempty"`
}

type AppMessageTarget struct {
	TargetType string               `bson:"targetType" json:"targetType"`
	TargetID   string               `bson:"targetId" json:"targetId"`
	RouteID    string               `bson:"routeId,omitempty" json:"routeId,omitempty"`
	RoutePath  string               `bson:"routePath,omitempty" json:"routePath,omitempty"`
	Query      AppMessageRouteQuery `bson:"query" json:"query"`
}

type AppMessageProvenance struct {
	Personalized    bool     `bson:"personalized"`
	InterestTags    []string `bson:"interestTags,omitempty"`
	MatchedSegments []string `bson:"matchedSegments,omitempty"`
	LifecycleStage  string   `bson:"lifecycleStage,omitempty"`
}

type AppMessageGatheringInvitationSchedule struct {
	Timezone  string     `bson:"timezone" json:"timezone"`
	StartAt   *time.Time `bson:"startAt,omitempty" json:"startAt,omitempty"`
	EndAt     *time.Time `bson:"endAt,omitempty" json:"endAt,omitempty"`
	DateLabel string     `bson:"dateLabel,omitempty" json:"dateLabel,omitempty"`
}

type AppMessageGatheringInvitationPlace struct {
	Mode              string `bson:"mode" json:"mode"`
	CoarsePlaceLabel  string `bson:"coarsePlaceLabel,omitempty" json:"coarsePlaceLabel,omitempty"`
	ExactMeetingPoint string `bson:"exactMeetingPoint,omitempty" json:"exactMeetingPoint,omitempty"`
}

type AppMessageGatheringInvitationActionIntent struct {
	Action                       string `bson:"action" json:"action"`
	ExpectedGatheringVersion     int64  `bson:"expectedGatheringVersion" json:"expectedGatheringVersion"`
	ExpectedParticipationVersion int64  `bson:"expectedParticipationVersion" json:"expectedParticipationVersion"`
}

type AppMessageGatheringInvitation struct {
	GatheringID          string                                      `bson:"gatheringId" json:"gatheringId"`
	InviterPersonaID     string                                      `bson:"inviterPersonaId" json:"inviterPersonaId"`
	RecipientPersonaID   string                                      `bson:"recipientPersonaId" json:"recipientPersonaId"`
	PurposeSummary       string                                      `bson:"purposeSummary" json:"purposeSummary"`
	Schedule             AppMessageGatheringInvitationSchedule       `bson:"schedule" json:"schedule"`
	Place                AppMessageGatheringInvitationPlace          `bson:"place" json:"place"`
	ParticipationVersion int64                                       `bson:"participationVersion" json:"participationVersion"`
	Status               string                                      `bson:"status" json:"status"`
	ActionIntents        []AppMessageGatheringInvitationActionIntent `bson:"actionIntents" json:"actionIntents"`
	ExpiresAt            *time.Time                                  `bson:"expiresAt,omitempty" json:"expiresAt,omitempty"`
}

// AppMessage is the Notification aggregate persisted by notification-service.
// Transport metadata, operation IDs and page attribution do not belong here.
type AppMessage struct {
	MessageID           string                         `bson:"_id" json:"messageId"`
	IdempotencyKey      string                         `bson:"idempotencyKey,omitempty" json:"-"`
	UserID              string                         `bson:"userId" json:"userId"`
	MessageType         string                         `bson:"messageType" json:"messageType"`
	Source              string                         `bson:"source" json:"source"`
	SourceID            string                         `bson:"sourceId" json:"sourceId"`
	Destination         AppMessageDestination          `bson:"destination" json:"destination"`
	Title               string                         `bson:"title" json:"title"`
	Summary             string                         `bson:"summary" json:"summary"`
	Target              AppMessageTarget               `bson:"target" json:"target"`
	GatheringInvitation *AppMessageGatheringInvitation `bson:"gatheringInvitation,omitempty" json:"gatheringInvitation,omitempty"`
	Provenance          AppMessageProvenance           `bson:"provenance" json:"-"`
	Read                bool                           `bson:"read" json:"read"`
	CreatedAt           time.Time                      `bson:"createdAt" json:"createdAt"`
	DeliveredAt         *time.Time                     `bson:"deliveredAt,omitempty" json:"deliveredAt,omitempty"`
	AckedAt             *time.Time                     `bson:"ackedAt,omitempty" json:"ackedAt,omitempty"`
	ReadAt              *time.Time                     `bson:"readAt,omitempty" json:"readAt,omitempty"`
}

type AppMessageInboxSlice struct {
	Items      []AppMessage `json:"items"`
	NextCursor string       `json:"nextCursor,omitempty"`
}

type AppMessageUnreadCountSlice struct {
	UnreadCount int64 `json:"unreadCount"`
}
