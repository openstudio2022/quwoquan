// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package local_contract

import (
	"testing"
	"time"

	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
)

func TestConversationMembershipOwnsClosedRoleAndMemberTypeInvariants(t *testing.T) {
	joinedAt := time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC)
	persona := membershipmodel.Member{
		ID: "membership-1", ConversationId: "conversation-1", UserId: "persona-1",
		MemberType: "user", Role: "owner", JoinedAt: joinedAt,
	}
	if err := persona.Validate(); err != nil {
		t.Fatalf("valid persona membership rejected: %v", err)
	}
	assistant := membershipmodel.Member{
		ID: "membership-2", ConversationId: "conversation-1", UserId: "assistant",
		MemberType: "assistant", Role: "member", JoinedAt: joinedAt,
	}
	if err := assistant.Validate(); err != nil {
		t.Fatalf("valid assistant membership rejected: %v", err)
	}
	assistant.Role = "admin"
	if err := assistant.Validate(); err == nil {
		t.Fatal("assistant membership must never become an admin")
	}
	persona.MemberType = "legacy_user"
	if err := persona.Validate(); err == nil {
		t.Fatal("non-canonical memberType must fail")
	}
}

func TestConversationMembershipCursorIsSingleOpaqueEncoding(t *testing.T) {
	joinedAt := time.Date(2026, 8, 2, 12, 0, 0, 123, time.UTC)
	if cursor := membershipmodel.EncodeJoinedCursor(joinedAt, "membership-1"); cursor == "" {
		t.Fatal("joined cursor must be opaque and non-empty")
	}
	if cursor := membershipmodel.EncodeDisplayNameCursor("Alice", "persona-1"); cursor == "" {
		t.Fatal("display-name cursor must be opaque and non-empty")
	}
	if got := membershipmodel.NormalizeListSort("V2"); got != membershipmodel.ListSortJoinedAsc {
		t.Fatalf("versioned alternate sort must not create a second track: %q", got)
	}
}
