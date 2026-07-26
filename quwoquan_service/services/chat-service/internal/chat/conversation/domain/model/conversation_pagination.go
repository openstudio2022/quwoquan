package model

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

var ErrInvalidInboxCursor = errors.New("invalid inbox cursor")

// ConversationUserStatePage is the stable keyset page for inbox-sorted
// ConversationUserState records. Its encoded cursor carries every persisted
// sort key, preventing a bare conversation identifier from being mistaken for
// a continuation of the pinned/updatedAt ordering.
type ConversationUserStatePage struct {
	Items      []ConversationUserState
	NextCursor string
}

// ConversationPage joins inbox-ordered user state to active conversation
// aggregates without losing the continuation token of the source reader.
type ConversationPage struct {
	Items      []Conversation
	NextCursor string
}

type inboxCursorPayload struct {
	Pinned         bool   `json:"p"`
	UpdatedAt      string `json:"u"`
	ConversationID string `json:"c"`
}

// EncodeInboxCursor produces the only cursor format accepted by the
// pinned/updatedAt/conversationId inbox reader.
func EncodeInboxCursor(state ConversationUserState) string {
	payload, err := json.Marshal(inboxCursorPayload{
		Pinned:         state.Pinned,
		UpdatedAt:      state.UpdatedAt.UTC().Format(time.RFC3339Nano),
		ConversationID: state.ConversationId,
	})
	if err != nil {
		return ""
	}
	return base64.RawURLEncoding.EncodeToString(payload)
}

// DecodeInboxCursor validates the keyset token before it reaches the
// persistence adapter. The reader therefore never applies an identifier-only
// predicate to a list sorted by pinned and updatedAt.
func DecodeInboxCursor(raw string) (ConversationUserState, error) {
	decoded, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(raw))
	if err != nil {
		return ConversationUserState{}, ErrInvalidInboxCursor
	}
	var payload inboxCursorPayload
	if err := json.Unmarshal(decoded, &payload); err != nil {
		return ConversationUserState{}, ErrInvalidInboxCursor
	}
	updatedAt, err := time.Parse(time.RFC3339Nano, payload.UpdatedAt)
	if err != nil || updatedAt.IsZero() || strings.TrimSpace(payload.ConversationID) == "" {
		return ConversationUserState{}, ErrInvalidInboxCursor
	}
	return ConversationUserState{
		Pinned:         payload.Pinned,
		UpdatedAt:      updatedAt.UTC(),
		ConversationId: payload.ConversationID,
	}, nil
}
