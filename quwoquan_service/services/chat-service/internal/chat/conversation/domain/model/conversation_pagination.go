package model

import (
	userstatemodel "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/domain/model"
)

var ErrInvalidInboxCursor = userstatemodel.ErrInvalidCursor

// ConversationUserStatePage is the stable keyset page for inbox-sorted
// ConversationUserState records. Its encoded cursor carries every persisted
// sort key, preventing a bare conversation identifier from being mistaken for
// a continuation of the pinned/updatedAt ordering.
type ConversationUserStatePage = userstatemodel.Page

// ConversationPage joins inbox-ordered user state to active conversation
// aggregates without losing the continuation token of the source reader.
type ConversationPage struct {
	Items      []Conversation
	NextCursor string
}

// EncodeInboxCursor produces the only cursor format accepted by the
// pinned/updatedAt/conversationId inbox reader.
func EncodeInboxCursor(state ConversationUserState) string {
	return userstatemodel.EncodeCursor(state)
}

// DecodeInboxCursor validates the keyset token before it reaches the
// persistence adapter. The reader therefore never applies an identifier-only
// predicate to a list sorted by pinned and updatedAt.
func DecodeInboxCursor(raw string) (ConversationUserState, error) {
	return userstatemodel.DecodeCursor(raw)
}
