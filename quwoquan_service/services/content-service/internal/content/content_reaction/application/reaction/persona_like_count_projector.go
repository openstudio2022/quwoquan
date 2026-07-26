package reaction

import (
	"context"
	"fmt"

	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

// PersonaLikeCountProjector 从 ContentReaction 权威集合精确重算 persona
// 的 active relation 数。事件重放只执行同值 $set，不会重复累加。
type PersonaLikeCountProjector struct {
	counter ActiveActorReactionCounter
	writer  PersonaLikeCountProjectionWriter
}

func NewPersonaLikeCountProjector(
	counter ActiveActorReactionCounter,
	writer PersonaLikeCountProjectionWriter,
) *PersonaLikeCountProjector {
	return &PersonaLikeCountProjector{counter: counter, writer: writer}
}

func (p *PersonaLikeCountProjector) Publish(
	ctx context.Context,
	fact reactionports.OutboxFact,
) error {
	if p == nil || p.counter == nil || p.writer == nil {
		return fmt.Errorf("persona like-count projector is not configured")
	}
	payload, err := decodeReactionStateChangedFact(fact)
	if err != nil {
		return err
	}
	if payload.ActorDimension != string(reactiondomain.ActorDimensionPersona) {
		return nil
	}
	if payload.TargetKind != string(reactiondomain.TargetKindPost) {
		return nil
	}
	actor, err := reactiondomain.NewActor(
		reactiondomain.ActorDimension(payload.ActorDimension),
		payload.ActorID,
	)
	if err != nil {
		return fmt.Errorf("restore ContentReaction projection actor: %w", err)
	}
	count, err := p.counter.CountActiveReactionsForActor(ctx, actor)
	if err != nil {
		return fmt.Errorf("count active persona ContentReaction relations: %w", err)
	}
	if err := p.writer.SetPersonaLikeCount(
		ctx,
		actor.ID,
		count,
		payload.OccurredAt,
	); err != nil {
		return fmt.Errorf("write persona like-count projection: %w", err)
	}
	return nil
}

var _ reactionports.OutboxPublisher = (*PersonaLikeCountProjector)(nil)
