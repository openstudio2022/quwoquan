package application

import "time"

type Identity struct {
	UserID         string
	ConversationID string
}

type Item struct {
	UserID              string
	ConversationID      string
	Type                string
	Title               string
	AvatarURL           string
	GroupAvatarVersion  int64
	LastMessageID       string
	LastMessagePreview  string
	LastMessageType     string
	LastMessageTime     time.Time
	LastSeq             int64
	ReadSeq             int64
	InboxProjectedSeq   int64
	UnreadCount         int
	MentionUnreadCount  int
	Muted               bool
	Pinned              bool
	CircleID            string
	ConversationUpdated time.Time
	StateUpdated        time.Time
	LastReadAt          time.Time
}

type Page struct {
	Items      []Item
	NextCursor string
}

type Event struct {
	ID             string
	Type           string
	ConversationID string
	ActorID        string
	Payload        map[string]any
	Checkpoint     string
}
