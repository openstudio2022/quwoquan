package local_contract

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
			"DissolveConversation",
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
			"ResolveAssistantDeliveryMembership",
		},
		"message": {
			"SendMessage",
			"RecallMessage",
			"ListMessages",
			"ListAssistantGroundingMessages",
			"SendAssistantDeliveryMessage",
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
		if scope, ok := map[string]string{
			"chat.conversation_membership.ResolveAssistantDeliveryMembership": "chat.assistant_delivery_membership.read",
			"chat.message.ListAssistantGroundingMessages":                     "chat.assistant_grounding.read",
			"chat.message.SendAssistantDeliveryMessage":                       "chat.assistant_delivery_message.send",
		}[descriptor.CanonicalOperationID]; ok {
			if descriptor.Principal != "service" {
				t.Errorf(
					"%s principal = %q, want service",
					descriptor.CanonicalOperationID,
					descriptor.Principal,
				)
			}
			if len(descriptor.Scopes) != 1 || descriptor.Scopes[0] != scope {
				t.Errorf(
					"%s scopes = %v, want [%s]",
					descriptor.CanonicalOperationID,
					descriptor.Scopes,
					scope,
				)
			}
		}
		delete(expected, descriptor.CanonicalOperationID)
	}
	for operationID := range expected {
		t.Errorf("generated operation security descriptor missing %s", operationID)
	}
}
