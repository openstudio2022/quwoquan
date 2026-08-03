package application

import (
	"context"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
)

type ListMembersRequest struct {
	ConversationId string
	ViewerId       string
	Cursor         string
	Limit          int
	Role           string
	Query          string
	Sort           string
}

type AssistantDeliveryMembershipView struct {
	CreatorMember   bool `json:"creatorMember"`
	AssistantMember bool `json:"assistantMember"`
}

type AddMembersRequest struct {
	ConversationId string
	UserIds        []string
	InvitedBy      string
}

type RemoveMemberRequest struct {
	ConversationId string
	UserId         string
	OperatorId     string
}

type LeaveConversationRequest struct {
	ConversationId string
	UserId         string
}

type InviteAssistantRequest struct {
	ConversationId     string
	InvitedBy          string
	InvitedByAccountID string
}

type RemoveAssistantRequest struct {
	ConversationId     string
	RemovedBy          string
	RemovedByAccountID string
}

type TransferOwnershipRequest struct {
	ConversationId string
	OperatorId     string
	NewOwnerId     string
}

type UpdateGroupAdminsRequest struct {
	ConversationId string
	OperatorId     string
	AdminIds       []string
}

type Backend interface {
	ListMembers(context.Context, ListMembersRequest) ([]membershipmodel.Member, error)
	ResolveAssistantDeliveryMembership(
		context.Context,
		string,
		string,
		string,
	) (AssistantDeliveryMembershipView, error)
	AddMembers(context.Context, AddMembersRequest) error
	RemoveMember(context.Context, RemoveMemberRequest) error
	LeaveConversation(context.Context, LeaveConversationRequest) error
	InviteAssistant(context.Context, InviteAssistantRequest) error
	RemoveAssistant(context.Context, RemoveAssistantRequest) error
	TransferOwnership(context.Context, TransferOwnershipRequest) error
	UpdateGroupAdmins(context.Context, UpdateGroupAdminsRequest) error
}

type UseCases struct{ backend Backend }

func NewUseCases(backend Backend) *UseCases {
	if backend == nil {
		panic("conversation membership backend is required")
	}
	return &UseCases{backend: backend}
}

func (s *UseCases) List(ctx context.Context, req ListMembersRequest) ([]membershipmodel.Member, error) {
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
) (AssistantDeliveryMembershipView, error) {
	return s.backend.ResolveAssistantDeliveryMembership(
		ctx,
		conversationID,
		creatorPersonaID,
		assistantMemberID,
	)
}
func (s *UseCases) Add(ctx context.Context, req AddMembersRequest) error {
	return s.backend.AddMembers(ctx, req)
}
func (s *UseCases) Remove(ctx context.Context, req RemoveMemberRequest) error {
	return s.backend.RemoveMember(ctx, req)
}
func (s *UseCases) Leave(ctx context.Context, req LeaveConversationRequest) error {
	return s.backend.LeaveConversation(ctx, req)
}
func (s *UseCases) InviteAssistant(ctx context.Context, req InviteAssistantRequest) error {
	return s.backend.InviteAssistant(ctx, req)
}
func (s *UseCases) RemoveAssistant(ctx context.Context, req RemoveAssistantRequest) error {
	return s.backend.RemoveAssistant(ctx, req)
}
func (s *UseCases) TransferOwnership(ctx context.Context, req TransferOwnershipRequest) error {
	return s.backend.TransferOwnership(ctx, req)
}
func (s *UseCases) UpdateAdmins(ctx context.Context, req UpdateGroupAdminsRequest) error {
	return s.backend.UpdateGroupAdmins(ctx, req)
}
