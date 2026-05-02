package application

import (
	"context"
	"fmt"

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
		if conv.AvatarUrl == "" {
			if defaultURL := DefaultGroupAvatarURL(); defaultURL != "" {
				conv.AvatarUrl = defaultURL
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
