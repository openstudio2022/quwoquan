package assistant

import "time"

type AppMessageTarget struct {
	TargetType string `json:"targetType"`
	TargetID   string `json:"targetId"`
}

type AppMessageDestination struct {
	Type string `json:"type"`
	ID   string `json:"id"`
}

type AppMessage struct {
	MessageID   string                `json:"messageId"`
	UserID      string                `json:"userId"`
	MessageType string                `json:"messageType"`
	Source      string                `json:"source"`
	SourceID    string                `json:"sourceId"`
	Destination AppMessageDestination `json:"destination"`
	Title       string                `json:"title"`
	Summary     string                `json:"summary"`
	Target      AppMessageTarget      `json:"target"`
	Read        bool                  `json:"read"`
	CreatedAt   time.Time             `json:"createdAt"`
	DeliveredAt *time.Time            `json:"deliveredAt,omitempty"`
	AckedAt     *time.Time            `json:"ackedAt,omitempty"`
	ReadAt      *time.Time            `json:"readAt,omitempty"`
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
}

type AppMessageListView struct {
	Items []AppMessage `json:"items"`
}

type AppMessageUnreadCountView struct {
	UnreadCount int `json:"unreadCount"`
}
