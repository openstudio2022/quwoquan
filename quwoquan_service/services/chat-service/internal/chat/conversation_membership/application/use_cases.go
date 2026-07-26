package application

import (
	"context"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

type Backend interface {
	ListMembers(context.Context, conversationapp.ListMembersRequest) ([]conversationmodel.ConversationMember, error)
	ResolveAssistantDeliveryMembership(
		context.Context,
		string,
		string,
		string,
		string,
	) (conversationapp.AssistantDeliveryMembershipView, error)
	AddMembers(context.Context, conversationapp.AddMembersRequest) error
	RemoveMember(context.Context, conversationapp.RemoveMemberRequest) error
	LeaveConversation(context.Context, conversationapp.LeaveConversationRequest) error
	InviteAssistant(context.Context, conversationapp.InviteAssistantRequest) error
	RemoveAssistant(context.Context, conversationapp.RemoveAssistantRequest) error
	TransferOwnership(context.Context, conversationapp.TransferOwnershipRequest) error
	UpdateGroupAdmins(context.Context, conversationapp.UpdateGroupAdminsRequest) error
}

type UseCases struct{ backend Backend }

func NewUseCases(backend Backend) *UseCases {
	if backend == nil {
		panic("conversation membership backend is required")
	}
	return &UseCases{backend: backend}
}

func (s *UseCases) List(ctx context.Context, req conversationapp.ListMembersRequest) ([]conversationmodel.ConversationMember, error) {
	if strings.TrimSpace(req.ConversationId) == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleChat, "conversationId 不能为空", "missing conversationId")
	}
	return s.backend.ListMembers(ctx, req)
}
func (s *UseCases) ResolveAssistantDeliveryMembership(
	ctx context.Context,
	conversationID string,
	creatorPersonaID string,
	assistantMemberID string,
	assistantSkillID string,
) (conversationapp.AssistantDeliveryMembershipView, error) {
	return s.backend.ResolveAssistantDeliveryMembership(
		ctx,
		conversationID,
		creatorPersonaID,
		assistantMemberID,
		assistantSkillID,
	)
}
func (s *UseCases) Add(ctx context.Context, req conversationapp.AddMembersRequest) error {
	return s.backend.AddMembers(ctx, req)
}
func (s *UseCases) Remove(ctx context.Context, req conversationapp.RemoveMemberRequest) error {
	return s.backend.RemoveMember(ctx, req)
}
func (s *UseCases) Leave(ctx context.Context, req conversationapp.LeaveConversationRequest) error {
	return s.backend.LeaveConversation(ctx, req)
}
func (s *UseCases) InviteAssistant(ctx context.Context, req conversationapp.InviteAssistantRequest) error {
	return s.backend.InviteAssistant(ctx, req)
}
func (s *UseCases) RemoveAssistant(ctx context.Context, req conversationapp.RemoveAssistantRequest) error {
	return s.backend.RemoveAssistant(ctx, req)
}
func (s *UseCases) TransferOwnership(ctx context.Context, req conversationapp.TransferOwnershipRequest) error {
	return s.backend.TransferOwnership(ctx, req)
}
func (s *UseCases) UpdateAdmins(ctx context.Context, req conversationapp.UpdateGroupAdminsRequest) error {
	return s.backend.UpdateGroupAdmins(ctx, req)
}
