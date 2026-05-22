package application

import (
	"context"
	"fmt"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

func BackfillMissingGroupAvatars(
	ctx context.Context,
	repo persistence.ChatRepository,
	publisher EventPublisher,
	media GroupAvatarAssetizer,
	syncPublisher UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
	limit int,
) error {
	if repo == nil {
		return fmt.Errorf("chat repository is required")
	}
	convs, err := repo.ListGroupConversationsNeedingAvatar(ctx, limit)
	if err != nil {
		return err
	}
	for _, conv := range convs {
		if conv.GroupAvatarVersion <= 0 || conv.GroupAvatarAssetId == "" {
			if fallbackURL := resolveCreatorGroupAvatarFallback(ctx, repo, conv); fallbackURL != "" {
				if conv.AvatarUrl != fallbackURL {
					conv.AvatarUrl = fallbackURL
					_ = repo.UpdateConversation(ctx, conv.ID, &conv)
				}
			} else if conv.AvatarUrl == "" {
				if defaultURL := DefaultGroupAvatarURL(); defaultURL != "" {
					conv.AvatarUrl = defaultURL
					_ = repo.UpdateConversation(ctx, conv.ID, &conv)
				}
			}
		} else if conv.AvatarUrl == "" {
			if resolvedURL := ResolveGroupAvatarURL(conv); resolvedURL != "" {
				conv.AvatarUrl = resolvedURL
				_ = repo.UpdateConversation(ctx, conv.ID, &conv)
			}
		}
		if err := RecomputeGroupAvatar(
			ctx,
			repo,
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
	repo persistence.ChatRepository,
	conv model.Conversation,
) string {
	creatorID := conv.CreatorId
	if creatorID == "" {
		return ""
	}
	members, err := repo.ListMembers(
		ctx,
		conv.ID,
		200,
		"",
		"",
		persistence.SortMembersJoinedAsc,
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
