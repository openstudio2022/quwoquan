package application

import (
	"context"
	"strings"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

const userAvatarRefreshBatchSize = 200

type UserAvatarUpdatedPayload struct {
	UserID        string
	AvatarURL     string
	AvatarAssetID string
	AvatarVersion int64
}

func HandleUserAvatarUpdated(
	ctx context.Context,
	repo persistence.ChatRepository,
	publisher EventPublisher,
	media GroupAvatarAssetizer,
	syncPublisher UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
	payload UserAvatarUpdatedPayload,
) error {
	userID := strings.TrimSpace(payload.UserID)
	if userID == "" || repo == nil {
		return nil
	}

	cursor := ""
	seen := map[string]struct{}{}
	for {
		states, err := repo.ListUserStates(ctx, userID, userAvatarRefreshBatchSize, cursor)
		if err != nil {
			return err
		}
		if len(states) == 0 {
			return nil
		}
		for _, state := range states {
			conversationID := strings.TrimSpace(state.ConversationId)
			if conversationID == "" {
				continue
			}
			if _, ok := seen[conversationID]; ok {
				continue
			}
			seen[conversationID] = struct{}{}
			if err := refreshUserAvatarInConversation(
				ctx,
				repo,
				publisher,
				media,
				syncPublisher,
				scheduler,
				conversationID,
				payload,
			); err != nil {
				return err
			}
		}
		if len(states) < userAvatarRefreshBatchSize {
			return nil
		}
		nextCursor := strings.TrimSpace(states[len(states)-1].ConversationId)
		if nextCursor == "" || nextCursor == cursor {
			return nil
		}
		cursor = nextCursor
	}
}

func refreshUserAvatarInConversation(
	ctx context.Context,
	repo persistence.ChatRepository,
	publisher EventPublisher,
	media GroupAvatarAssetizer,
	syncPublisher UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
	conversationID string,
	payload UserAvatarUpdatedPayload,
) error {
	conv, err := repo.FindConversationByID(ctx, conversationID)
	if err != nil || conv == nil {
		return nil
	}
	if conv.Type != "group" && conv.Type != "circle" {
		return nil
	}

	members, err := repo.ListMembers(
		ctx,
		conversationID,
		16,
		"",
		"",
		persistence.SortMembersJoinedAsc,
	)
	if err != nil {
		return err
	}
	topNine := selectTopAvatarMembers(members)
	if !topNineContainsUser(topNine, payload.UserID) {
		return nil
	}

	if err := repo.UpdateMemberAvatarSnapshot(
		ctx,
		conversationID,
		payload.UserID,
		strings.TrimSpace(payload.AvatarURL),
		strings.TrimSpace(payload.AvatarAssetID),
		payload.AvatarVersion,
	); err != nil {
		return err
	}

	if scheduler != nil {
		return scheduler.EnqueueRecompute(ctx, GroupAvatarRecomputeTask{
			ConversationID: conversationID,
			ActorID:        payload.UserID,
			Trigger:        "user.avatar.updated",
		})
	}
	return RecomputeGroupAvatar(ctx, repo, publisher, media, syncPublisher, nil, conversationID, payload.UserID)
}

func topNineContainsUser(members []model.ConversationMember, userID string) bool {
	target := strings.TrimSpace(userID)
	for _, member := range members {
		if strings.TrimSpace(member.UserId) == target {
			return true
		}
	}
	return false
}
