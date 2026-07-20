package main

import (
	"testing"

	"quwoquan_service/generated/operationsecurity"
)

func TestChatCoreObjectOperationsAreCommerciallyExecutable(t *testing.T) {
	t.Parallel()

	expected := map[string]struct{}{}
	for object, operations := range map[string][]string{
		"conversation": {
			"ListConversations",
			"ListConversationTimestamps",
			"CreateConversation",
			"BatchGetConversations",
			"GetConversation",
			"UpdateConversationTitle",
			"UpdateAnnouncement",
			"UpdateGroupGovernanceSettings",
			"GetReceipts",
			"DissolveConversation",
			"ListInbox",
			"ListMessageHome",
			"ListContacts",
			"ListContactHome",
			"GetGroupHome",
			"ListGroupCandidates",
			"ListSelectableGroupConversations",
			"ListSelectableGroupContactMembers",
		},
		"conversation_membership": {
			"AddMembers",
			"RemoveMember",
			"LeaveConversation",
			"InviteAssistant",
			"RemoveAssistant",
			"TransferOwnership",
			"UpdateGroupAdmins",
			"ListMembers",
		},
		"message": {
			"SendMessage",
			"RecallMessage",
			"ListMessages",
			"SyncMessages",
		},
		"conversation_user_state": {
			"MarkAsRead",
			"UpdateConversationSettings",
		},
	} {
		for _, operation := range operations {
			expected["chat."+object+"."+operation] = struct{}{}
		}
	}

	for _, descriptor := range operationsecurity.ForDomain("chat") {
		if _, ok := expected[descriptor.CanonicalOperationID]; !ok {
			continue
		}
		if descriptor.CommercialStatus != "ready" {
			t.Errorf(
				"%s commercial status = %q, want ready",
				descriptor.CanonicalOperationID,
				descriptor.CommercialStatus,
			)
		}
		if descriptor.AuthMode != "required" {
			t.Errorf(
				"%s auth mode = %q, want required",
				descriptor.CanonicalOperationID,
				descriptor.AuthMode,
			)
		}
		delete(expected, descriptor.CanonicalOperationID)
	}
	for operationID := range expected {
		t.Errorf("generated operation security descriptor missing %s", operationID)
	}
}
