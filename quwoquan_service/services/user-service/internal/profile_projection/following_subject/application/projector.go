// Package following_subject 承载 FollowingSubject 投影：projector 是唯一
// writer，query facade 是 named reader。投影订阅 PersonaFollowStateChanged
// 与 SubjectFollowStateChanged（circle 域事件随 B4 批次接入）。
package following_subject

import (
	"context"
	"fmt"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	sfmodel "quwoquan_service/services/user-service/internal/relationship/subject_follow/domain/model"
)

// Projector 把已提交的关注事实投影为关注频道行。它被组合进两个 outbox
// relay 的 publisher 链：投影失败会使 relay 不推进 checkpoint 并重试，
// 幂等 upsert（sourceVersion 单调）保证至少一次投递下的收敛。
type Projector struct {
	store ProjectionStore
}

func NewProjector(store ProjectionStore) *Projector {
	if store == nil {
		panic("following subject projection store is required")
	}
	return &Projector{store: store}
}

// ApplyPersonaRelationship 消费 PersonaFollowStateChanged：source persona
// 关注/取关 target user。
func (p *Projector) ApplyPersonaRelationship(ctx context.Context, event relmodel.OutboxEvent) error {
	payload := event.Payload
	if payload.SourcePersonaID == "" || payload.TargetPersonaID == "" {
		return fmt.Errorf("following subject projector: invalid persona relationship event %s", event.EventID)
	}
	if payload.Following {
		return p.store.UpsertFollow(
			ctx,
			payload.SourcePersonaID,
			"user",
			payload.TargetPersonaID,
			payload.OccurredAt,
			payload.Version,
		)
	}
	return p.store.RemoveFollow(
		ctx,
		payload.SourcePersonaID,
		"user",
		payload.TargetPersonaID,
		payload.Version,
	)
}

// ApplySubjectFollow 消费 SubjectFollowStateChanged：persona 关注/取关
// homepage / circle / location 主体。
func (p *Projector) ApplySubjectFollow(ctx context.Context, event sfmodel.OutboxEvent) error {
	payload := event.Payload
	if payload.PersonaID == "" || payload.SubjectID == "" {
		return fmt.Errorf("following subject projector: invalid subject follow event %s", event.EventID)
	}
	if payload.State == sfmodel.StateFollowing {
		return p.store.UpsertFollow(
			ctx,
			payload.PersonaID,
			payload.SubjectType,
			payload.SubjectID,
			payload.OccurredAt,
			payload.Version,
		)
	}
	return p.store.RemoveFollow(
		ctx,
		payload.PersonaID,
		payload.SubjectType,
		payload.SubjectID,
		payload.Version,
	)
}
