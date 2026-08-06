// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: add-members-local
// readiness_case: remove-member-local
// readiness_case: leave-conversation-local
// readiness_case: resolve-assistant-delivery-membership-local
// readiness_case: invite-assistant-local
// readiness_case: remove-assistant-local
// readiness_case: transfer-ownership-local
// readiness_case: update-group-admins-local
// readiness_case: list-members-local
package local_contract

import (
	"context"
	"testing"
	"time"

	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
)

func TestConversationMembershipUseCasesExecuteEveryHTTPApplicationFacet(t *testing.T) {
	backend := &membershipOperationBackend{calls: map[string]int{}}
	useCases := membershipapp.NewUseCases(backend)
	ctx := context.Background()

	members, err := useCases.List(ctx, membershipapp.ListMembersRequest{
		ConversationId: "conversation-1", ViewerId: "persona-owner", Limit: 20,
	})
	if err != nil || len(members) != 1 || members[0].UserId != "persona-member" {
		t.Fatalf("ListMembers result=%+v err=%v", members, err)
	}
	membership, err := useCases.ResolveAssistantDeliveryMembership(
		ctx, "conversation-1", "persona-owner", "assistant-member",
	)
	if err != nil || !membership.CreatorMember || !membership.AssistantMember {
		t.Fatalf("ResolveAssistantDeliveryMembership result=%+v err=%v", membership, err)
	}
	commands := []struct {
		name string
		call func() error
	}{
		{"AddMembers", func() error {
			return useCases.Add(ctx, membershipapp.AddMembersRequest{ConversationId: "conversation-1", InvitedBy: "persona-owner", UserIds: []string{"persona-member"}})
		}},
		{"RemoveMember", func() error {
			return useCases.Remove(ctx, membershipapp.RemoveMemberRequest{ConversationId: "conversation-1", OperatorId: "persona-owner", UserId: "persona-member"})
		}},
		{"LeaveConversation", func() error {
			return useCases.Leave(ctx, membershipapp.LeaveConversationRequest{ConversationId: "conversation-1", UserId: "persona-member"})
		}},
		{"InviteAssistant", func() error {
			return useCases.InviteAssistant(ctx, membershipapp.InviteAssistantRequest{ConversationId: "conversation-1", InvitedBy: "persona-owner", InvitedByAccountID: "account-owner"})
		}},
		{"RemoveAssistant", func() error {
			return useCases.RemoveAssistant(ctx, membershipapp.RemoveAssistantRequest{ConversationId: "conversation-1", RemovedBy: "persona-owner", RemovedByAccountID: "account-owner"})
		}},
		{"TransferOwnership", func() error {
			return useCases.TransferOwnership(ctx, membershipapp.TransferOwnershipRequest{ConversationId: "conversation-1", OperatorId: "persona-owner", NewOwnerId: "persona-member"})
		}},
		{"UpdateGroupAdmins", func() error {
			return useCases.UpdateAdmins(ctx, membershipapp.UpdateGroupAdminsRequest{ConversationId: "conversation-1", OperatorId: "persona-owner", AdminIds: []string{"persona-member"}})
		}},
	}
	for _, command := range commands {
		if err := command.call(); err != nil {
			t.Fatalf("%s: %v", command.name, err)
		}
	}
	for _, name := range []string{
		"ListMembers", "ResolveAssistantDeliveryMembership", "AddMembers", "RemoveMember",
		"LeaveConversation", "InviteAssistant", "RemoveAssistant", "TransferOwnership", "UpdateGroupAdmins",
	} {
		if backend.calls[name] != 1 {
			t.Fatalf("%s call count=%d want=1", name, backend.calls[name])
		}
	}
}

type membershipOperationBackend struct {
	calls map[string]int
}

func (backend *membershipOperationBackend) record(name string) { backend.calls[name]++ }

func (backend *membershipOperationBackend) ListMembers(
	context.Context,
	membershipapp.ListMembersRequest,
) ([]membershipmodel.Member, error) {
	backend.record("ListMembers")
	return []membershipmodel.Member{{
		ID: "membership-1", ConversationId: "conversation-1", UserId: "persona-member",
		MemberType: "user", Role: "member", JoinedAt: time.Date(2026, 8, 6, 0, 0, 0, 0, time.UTC),
	}}, nil
}

func (backend *membershipOperationBackend) ResolveAssistantDeliveryMembership(
	context.Context, string, string, string,
) (membershipapp.AssistantDeliveryMembershipView, error) {
	backend.record("ResolveAssistantDeliveryMembership")
	return membershipapp.AssistantDeliveryMembershipView{CreatorMember: true, AssistantMember: true}, nil
}

func (backend *membershipOperationBackend) AddMembers(context.Context, membershipapp.AddMembersRequest) error {
	backend.record("AddMembers")
	return nil
}

func (backend *membershipOperationBackend) RemoveMember(context.Context, membershipapp.RemoveMemberRequest) error {
	backend.record("RemoveMember")
	return nil
}

func (backend *membershipOperationBackend) LeaveConversation(context.Context, membershipapp.LeaveConversationRequest) error {
	backend.record("LeaveConversation")
	return nil
}

func (backend *membershipOperationBackend) InviteAssistant(context.Context, membershipapp.InviteAssistantRequest) error {
	backend.record("InviteAssistant")
	return nil
}

func (backend *membershipOperationBackend) RemoveAssistant(context.Context, membershipapp.RemoveAssistantRequest) error {
	backend.record("RemoveAssistant")
	return nil
}

func (backend *membershipOperationBackend) TransferOwnership(context.Context, membershipapp.TransferOwnershipRequest) error {
	backend.record("TransferOwnership")
	return nil
}

func (backend *membershipOperationBackend) UpdateGroupAdmins(context.Context, membershipapp.UpdateGroupAdminsRequest) error {
	backend.record("UpdateGroupAdmins")
	return nil
}
