package application

import (
	"context"
	"fmt"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

func BackfillMissingGroupAvatars(
	ctx context.Context,
	storage ChatStoragePorts,
	publisher EventPublisher,
	media GroupAvatarAssetizer,
	syncPublisher UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
	limit int,
) error {
	if storage.Conversations == nil {
		return fmt.Errorf("chat conversation store is required")
	}
	convs, err := storage.Conversations.ListGroupConversationsNeedingAvatar(ctx, limit)
	if err != nil {
		return err
	}
	for _, conv := range convs {
		if conv.GroupAvatarVersion <= 0 || conv.GroupAvatarAssetId == "" {
			if fallbackURL := resolveCreatorGroupAvatarFallback(ctx, storage.Members, conv); fallbackURL != "" {
				if conv.AvatarUrl != fallbackURL {
					conv.AvatarUrl = fallbackURL
					_ = storage.Conversations.UpdateConversation(ctx, conv.ID, &conv)
				}
			} else if conv.AvatarUrl == "" {
				if defaultURL := DefaultGroupAvatarURL(); defaultURL != "" {
					conv.AvatarUrl = defaultURL
					_ = storage.Conversations.UpdateConversation(ctx, conv.ID, &conv)
				}
			}
		} else if conv.AvatarUrl == "" {
			if resolvedURL := ResolveGroupAvatarURL(conv); resolvedURL != "" {
				conv.AvatarUrl = resolvedURL
				_ = storage.Conversations.UpdateConversation(ctx, conv.ID, &conv)
			}
		}
		if err := RecomputeGroupAvatar(
			ctx,
			storage,
			publisher,
			media,
			syncPublisher,
			scheduler,
			conv.ID,
			"system:group-avatar-backfill",
		); err != nil {
			return err
		}
	}
	return nil
}

func resolveCreatorGroupAvatarFallback(
	ctx context.Context,
	membersStore MemberStore,
	conv model.Conversation,
) string {
	creatorID := conv.CreatorId
	if creatorID == "" {
		return ""
	}
	members, err := membersStore.ListMembers(
		ctx,
		conv.ID,
		ListMembersQuery{
			Limit: 200,
			Sort:  MemberListSortJoinedAsc,
		},
	)
	if err != nil {
		return ""
	}
	for _, member := range members {
		if member.UserId == creatorID {
			return resolveConversationAvatarURLValue(member.AvatarUrl, member.AvatarVersion)
		}
	}
	for _, member := range members {
		if member.Role == "owner" {
			return resolveConversationAvatarURLValue(member.AvatarUrl, member.AvatarVersion)
		}
	}
	return ""
}
