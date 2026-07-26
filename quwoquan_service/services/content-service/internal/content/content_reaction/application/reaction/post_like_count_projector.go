package reaction

import (
	"context"
	"fmt"
	"strings"

	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

// ActiveReactionCountProjector 以权威 ContentReaction 集合重算按 Post
// 维度的 likeCount；Post 与 DiscoveryFeed 分别使用独立 relay/checkpoint。
type ActiveReactionCountProjector struct {
	counter ActiveReactionCounter
	writer  LikeCountProjectionWriter
}

func NewActiveReactionCountProjector(
	counter ActiveReactionCounter,
	writer LikeCountProjectionWriter,
) *ActiveReactionCountProjector {
	return &ActiveReactionCountProjector{counter: counter, writer: writer}
}

func (p *ActiveReactionCountProjector) Publish(
	ctx context.Context,
	fact reactionports.OutboxFact,
) error {
	if p == nil || p.counter == nil || p.writer == nil {
		return fmt.Errorf("Post like-count projector is not configured")
	}
	payload, err := decodeReactionStateChangedFact(fact)
	if err != nil {
		return err
	}
	if payload.TargetKind != string(reactiondomain.TargetKindPost) {
		return nil
	}
	postID := strings.TrimSpace(payload.TargetID)
	count, err := p.counter.CountActiveReactions(ctx, postID)
	if err != nil {
		return fmt.Errorf("count active ContentReaction relations: %w", err)
	}
	updated, err := p.writer.SetLikeCount(ctx, postID, count)
	if err != nil {
		return fmt.Errorf("write ContentReaction like-count projection: %w", err)
	}
	if !updated {
		return fmt.Errorf("ContentReaction like-count target %q is missing", postID)
	}
	return nil
}

var _ reactionports.OutboxPublisher = (*ActiveReactionCountProjector)(nil)
