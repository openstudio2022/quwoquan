package model

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

var (
	ErrNotFound      = errors.New("conversation user state not found")
	ErrInvalidCursor = errors.New("invalid conversation user state cursor")
)

// State is the private per-persona state aggregate for one Conversation.
type State struct {
	ID                 string    `json:"id" bson:"_id"`
	UserId             string    `json:"userId" bson:"userId"`
	ConversationId     string    `json:"conversationId" bson:"conversationId"`
	ReadSeq            int64     `json:"readSeq" bson:"readSeq"`
	InboxProjectedSeq  int64     `json:"-" bson:"inboxProjectedSeq"`
	UnreadCount        int       `json:"unreadCount" bson:"unreadCount"`
	MentionUnreadCount int       `json:"mentionUnreadCount" bson:"mentionUnreadCount"`
	Muted              bool      `json:"muted" bson:"muted"`
	Pinned             bool      `json:"pinned" bson:"pinned"`
	LastReadAt         time.Time `json:"lastReadAt" bson:"lastReadAt"`
	UpdatedAt          time.Time `json:"updatedAt" bson:"updatedAt"`
}

func (state State) ValidateIdentity() error {
	if strings.TrimSpace(state.ID) == "" || strings.TrimSpace(state.UserId) == "" ||
		strings.TrimSpace(state.ConversationId) == "" {
		return errors.New("conversation user state identity is required")
	}
	if state.ReadSeq < 0 || state.InboxProjectedSeq < 0 || state.UnreadCount < 0 ||
		state.MentionUnreadCount < 0 {
		return errors.New("conversation user state watermarks and counters cannot be negative")
	}
	return nil
}

type Page struct {
	Items      []State
	NextCursor string
}

type cursorPayload struct {
	Pinned         bool   `json:"p"`
	UpdatedAt      string `json:"u"`
	ConversationID string `json:"c"`
}

func EncodeCursor(state State) string {
	payload, err := json.Marshal(cursorPayload{
		Pinned:         state.Pinned,
		UpdatedAt:      state.UpdatedAt.UTC().Format(time.RFC3339Nano),
		ConversationID: state.ConversationId,
	})
	if err != nil {
		return ""
	}
	return base64.RawURLEncoding.EncodeToString(payload)
}

func DecodeCursor(raw string) (State, error) {
	decoded, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(raw))
	if err != nil {
		return State{}, ErrInvalidCursor
	}
	var payload cursorPayload
	if err := json.Unmarshal(decoded, &payload); err != nil {
		return State{}, ErrInvalidCursor
	}
	updatedAt, err := time.Parse(time.RFC3339Nano, payload.UpdatedAt)
	if err != nil || updatedAt.IsZero() || strings.TrimSpace(payload.ConversationID) == "" {
		return State{}, ErrInvalidCursor
	}
	return State{
		Pinned:         payload.Pinned,
		UpdatedAt:      updatedAt.UTC(),
		ConversationId: payload.ConversationID,
	}, nil
}
