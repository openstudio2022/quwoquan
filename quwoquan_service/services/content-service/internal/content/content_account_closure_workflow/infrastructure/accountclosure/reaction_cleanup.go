package accountclosure

import (
	"context"
	"fmt"

	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

type ContentReactionLifecycleCleanup struct {
	cleanup reactionapp.LifecycleCleanupPort
}

func NewContentReactionLifecycleCleanup(cleanup reactionapp.LifecycleCleanupPort) *ContentReactionLifecycleCleanup {
	return &ContentReactionLifecycleCleanup{cleanup: cleanup}
}

func (cleanup *ContentReactionLifecycleCleanup) CleanupClosedAccountReactions(ctx context.Context, event UserAccountClosedEvent, targets []ReactionCleanupTarget) error {
	if cleanup == nil || cleanup.cleanup == nil {
		return fmt.Errorf("closed-account ContentReaction cleanup is not configured")
	}
	for _, targetWork := range targets {
		target, err := reactiondomain.NewTarget(reactiondomain.TargetKind(targetWork.Kind), targetWork.ID)
		if err != nil {
			return err
		}
		if err := cleanup.cleanup.CleanupTarget(ctx, target, reactionapp.LifecycleCleanupAuthorization{
			Source: "UserAccountClosed", SourceEventID: event.EventID, SourceVersion: targetWork.SourceVersion,
			Tombstone: fmt.Sprintf("account-target:%s:%s:v%d", targetWork.Kind, targetWork.ID, targetWork.SourceVersion), OccurredAt: event.OccurredAt,
		}); err != nil {
			return err
		}
	}
	for _, personaID := range event.Payload.PersonaIDs {
		actor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, personaID)
		if err != nil {
			return err
		}
		if err := cleanup.cleanup.CleanupActor(ctx, actor, reactionapp.LifecycleCleanupAuthorization{
			Source: "UserAccountClosed", SourceEventID: event.EventID, SourceVersion: event.AccountVersion,
			Tombstone: "account:" + event.Digest(), OccurredAt: event.OccurredAt,
		}); err != nil {
			return err
		}
	}
	return nil
}

var _ ReactionLifecycleCleanup = (*ContentReactionLifecycleCleanup)(nil)
