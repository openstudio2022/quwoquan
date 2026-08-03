// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package local_contract

import (
	"testing"
	"time"

	userstatemodel "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/domain/model"
)

func TestConversationUserStateOwnsIdentityCountersAndSingleCursor(t *testing.T) {
	state := userstatemodel.State{
		ID: "state-1", UserId: "persona-1", ConversationId: "conversation-1",
		ReadSeq: 5, InboxProjectedSeq: 8, UnreadCount: 3,
		UpdatedAt: time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC),
	}
	if err := state.ValidateIdentity(); err != nil {
		t.Fatalf("valid state rejected: %v", err)
	}
	cursor := userstatemodel.EncodeCursor(state)
	decoded, err := userstatemodel.DecodeCursor(cursor)
	if err != nil || decoded.ConversationId != state.ConversationId ||
		decoded.UpdatedAt != state.UpdatedAt || decoded.Pinned != state.Pinned {
		t.Fatalf("single cursor round-trip failed: decoded=%+v err=%v", decoded, err)
	}
	state.UnreadCount = -1
	if err := state.ValidateIdentity(); err == nil {
		t.Fatal("negative unread count must violate the aggregate invariant")
	}
}
