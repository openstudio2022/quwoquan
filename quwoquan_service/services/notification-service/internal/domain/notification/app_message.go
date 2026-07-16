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

// AppMessage is the Notification aggregate persisted by notification-service.
// Transport metadata, operation IDs and page attribution do not belong here.
type AppMessage struct {
	MessageID      string                `bson:"_id" json:"messageId"`
	IdempotencyKey string                `bson:"idempotencyKey,omitempty" json:"-"`
	UserID         string                `bson:"userId" json:"userId"`
	MessageType    string                `bson:"messageType" json:"messageType"`
	Source         string                `bson:"source" json:"source"`
	SourceID       string                `bson:"sourceId" json:"sourceId"`
	Destination    AppMessageDestination `bson:"destination" json:"destination"`
	Title          string                `bson:"title" json:"title"`
	Summary        string                `bson:"summary" json:"summary"`
	Target         AppMessageTarget      `bson:"target" json:"target"`
	Provenance     AppMessageProvenance  `bson:"provenance" json:"-"`
	Read           bool                  `bson:"read" json:"read"`
	CreatedAt      time.Time             `bson:"createdAt" json:"createdAt"`
	DeliveredAt    *time.Time            `bson:"deliveredAt,omitempty" json:"deliveredAt,omitempty"`
	AckedAt        *time.Time            `bson:"ackedAt,omitempty" json:"ackedAt,omitempty"`
	ReadAt         *time.Time            `bson:"readAt,omitempty" json:"readAt,omitempty"`
}

type AppMessageInboxSlice struct {
	Items      []AppMessage `json:"items"`
	NextCursor string       `json:"nextCursor,omitempty"`
}

type AppMessageUnreadCountSlice struct {
	UnreadCount int64 `json:"unreadCount"`
}
