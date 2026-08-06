// spec_ref: specs/feature-tree/runtime/runtime-media/group-avatar-server-precompose-and-unified-sync-contract/spec.md#gwt-001
// readiness_case: consume-user-avatar-updated-local
package local_contract

import (
	"context"
	"testing"

	. "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

func TestUserAvatarUpdatedConsumerRefreshesTheOwnedConversationProjection(t *testing.T) {
	states := &memoryUserStateStore{state: &model.ConversationUserState{
		UserId:         "user-1",
		ConversationId: "conversation-1",
	}}
	conversations := &userAvatarConversationStore{conversation: model.Conversation{
		ID:     "conversation-1",
		Type:   "group",
		Status: model.ConversationStatusActive,
	}}
	members := &userAvatarMemberStore{members: []model.ConversationMember{
		{ConversationId: "conversation-1", UserId: "user-1", AvatarVersion: 1},
		{ConversationId: "conversation-1", UserId: "user-2", AvatarVersion: 1},
	}}
	scheduler := &userAvatarScheduler{}

	err := HandleUserAvatarUpdated(
		context.Background(),
		ChatStoragePorts{
			Transactions:  passthroughTransactionRunner{},
			Conversations: conversations,
			Members:       members,
			UserStates:    states,
		},
		nil,
		nil,
		nil,
		scheduler,
		UserAvatarUpdatedPayload{
			UserID:        "user-1",
			AvatarURL:     "media/avatar/s/archived-avatar/user/user-1/v2/avatar.png",
			AvatarAssetID: "avatar-asset-2",
			AvatarVersion: 2,
		},
	)
	if err != nil {
		t.Fatalf("consume UserAvatarUpdated: %v", err)
	}
	if members.updatedUserID != "user-1" || members.updatedVersion != 2 ||
		members.updatedAssetID != "avatar-asset-2" {
		t.Fatalf("member avatar projection not updated: %+v", members)
	}
	if scheduler.task.ConversationID != "conversation-1" ||
		scheduler.task.Trigger != "user.avatar.updated" {
		t.Fatalf("group avatar recompute not enqueued: %+v", scheduler.task)
	}
}

type userAvatarConversationStore struct {
	ConversationStore
	conversation model.Conversation
}

func (s *userAvatarConversationStore) FindConversationByID(
	_ context.Context,
	id string,
) (*model.Conversation, error) {
	if id != s.conversation.ID {
		return nil, nil
	}
	copy := s.conversation
	return &copy, nil
}

type userAvatarMemberStore struct {
	MemberStore
	members        []model.ConversationMember
	updatedUserID  string
	updatedAssetID string
	updatedVersion int64
}

func (s *userAvatarMemberStore) ListMembers(
	context.Context,
	string,
	ListMembersQuery,
) ([]model.ConversationMember, error) {
	return append([]model.ConversationMember(nil), s.members...), nil
}

func (s *userAvatarMemberStore) UpdateMemberAvatarSnapshot(
	_ context.Context,
	_ string,
	userID string,
	_ string,
	assetID string,
	version int64,
) error {
	s.updatedUserID = userID
	s.updatedAssetID = assetID
	s.updatedVersion = version
	return nil
}

type userAvatarScheduler struct {
	task GroupAvatarRecomputeTask
}

func (s *userAvatarScheduler) EnqueueRecompute(
	_ context.Context,
	task GroupAvatarRecomputeTask,
) error {
	s.task = task
	return nil
}

func (*userAvatarScheduler) EnqueueConversationAvatarPatch(
	context.Context,
	ConversationAvatarPatchTask,
) error {
	return nil
}
