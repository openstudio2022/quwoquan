package model

import (
	"testing"
	"time"
)

func TestInboxCursorRoundTripPreservesEverySortKey(t *testing.T) {
	t.Parallel()

	state := ConversationUserState{
		Pinned:         true,
		UpdatedAt:      time.Date(2026, time.July, 21, 6, 12, 0, 123456789, time.UTC),
		ConversationId: "conversation_123",
	}

	decoded, err := DecodeInboxCursor(EncodeInboxCursor(state))
	if err != nil {
		t.Fatalf("DecodeInboxCursor returned error: %v", err)
	}
	if decoded.Pinned != state.Pinned ||
		!decoded.UpdatedAt.Equal(state.UpdatedAt) ||
		decoded.ConversationId != state.ConversationId {
		t.Fatalf("cursor round trip lost sort key: got %#v want %#v", decoded, state)
	}
}

func TestDecodeInboxCursorRejectsMalformedOrIncompleteValues(t *testing.T) {
	t.Parallel()

	for _, raw := range []string{"", "not-base64", "e30"} {
		if _, err := DecodeInboxCursor(raw); err != ErrInvalidInboxCursor {
			t.Fatalf("DecodeInboxCursor(%q) error = %v, want ErrInvalidInboxCursor", raw, err)
		}
	}
}
