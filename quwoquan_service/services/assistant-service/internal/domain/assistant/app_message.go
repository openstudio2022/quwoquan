package assistant

import "time"

type AppMessageTarget struct {
	TargetType string `bson:"targetType" json:"targetType"`
	TargetID   string `bson:"targetId" json:"targetId"`
}

type AppMessageDestination struct {
	Type string `bson:"type" json:"type"`
	ID   string `bson:"id" json:"id"`
}

type AppMessage struct {
	MessageID   string                `bson:"_id" json:"messageId"`
	UserID      string                `bson:"userId" json:"userId"`
	MessageType string                `bson:"messageType" json:"messageType"`
	Source      string                `bson:"source" json:"source"`
	SourceID    string                `bson:"sourceId" json:"sourceId"`
	Destination AppMessageDestination `bson:"destination" json:"destination"`
	Title       string                `bson:"title" json:"title"`
	Summary     string                `bson:"summary" json:"summary"`
	Target      AppMessageTarget      `bson:"target" json:"target"`
	Read        bool                  `bson:"read" json:"read"`
	// 主动消费证据：标记该消息是否由用户兴趣画像(interestProfile)派生个性化而来，
	// 并持久化派生出的标签/人群/生命周期，供审计与飞轮闭环数据面校验。
	Personalized    bool       `bson:"personalized" json:"personalized"`
	InterestTags    []string   `bson:"interestTags,omitempty" json:"interestTags,omitempty"`
	MatchedSegments []string   `bson:"matchedSegments,omitempty" json:"matchedSegments,omitempty"`
	LifecycleStage  string     `bson:"lifecycleStage,omitempty" json:"lifecycleStage,omitempty"`
	CreatedAt       time.Time  `bson:"createdAt" json:"createdAt"`
	DeliveredAt     *time.Time `bson:"deliveredAt,omitempty" json:"deliveredAt,omitempty"`
	AckedAt         *time.Time `bson:"ackedAt,omitempty" json:"ackedAt,omitempty"`
	ReadAt          *time.Time `bson:"readAt,omitempty" json:"readAt,omitempty"`
}

type CreateAppMessageInput struct {
	UserID      string                `json:"userId"`
	MessageType string                `json:"messageType"`
	Source      string                `json:"source"`
	SourceID    string                `json:"sourceId"`
	Destination AppMessageDestination `json:"destination"`
	Title       string                `json:"title"`
	Summary     string                `json:"summary"`
	Target      AppMessageTarget      `json:"target"`
	// 主动消费个性化归因，由主动编排从画像派生结果透传而来。
	Personalized    bool     `json:"personalized"`
	InterestTags    []string `json:"interestTags,omitempty"`
	MatchedSegments []string `json:"matchedSegments,omitempty"`
	LifecycleStage  string   `json:"lifecycleStage,omitempty"`
}

type AppMessageListView struct {
	Items []AppMessage `json:"items"`
}

type AppMessageUnreadCountView struct {
	UnreadCount int `json:"unreadCount"`
}
