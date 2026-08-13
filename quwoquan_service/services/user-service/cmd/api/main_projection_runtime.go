package bootstrap

import (
	"context"
	"time"

	"quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/mq"
	followingevent "quwoquan_service/services/user-service/internal/profile_projection/following_subject/adapters/inbound/event"
	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
	visitmodel "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/model"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	sfmodel "quwoquan_service/services/user-service/internal/relationship/subject_follow/domain/model"
)

// followedSubjectVisitFanout 消费 FollowedSubjectVisited outbox，把访问水位
// 应用到 following_subjects 投影。投影 upsert 以 $max/清零实现，因此至少一次
// 投递是安全的；投影失败不会标记事件已投递，下一轮 relay 会重放。
type followedSubjectVisitFanout struct {
	projection visitProjectionApplier
}

type visitProjectionApplier interface {
	ApplyVisit(
		ctx context.Context,
		personaID, subjectType, subjectID string,
		visitedAt time.Time,
	) error
}

func (f *followedSubjectVisitFanout) PublishFollowedSubjectVisited(
	ctx context.Context,
	event visitmodel.OutboxEvent,
) error {
	payload := event.Payload
	return f.projection.ApplyVisit(
		ctx,
		payload.PersonaID,
		payload.SubjectType,
		payload.SubjectID,
		payload.LastVisitedAt,
	)
}

// subjectFollowFanout 把已提交的 SubjectFollow 事实先追加到 Redis Stream，
// 再 upsert following_subjects 投影；任一失败都不推进 outbox checkpoint，
// 幂等消费保证至少一次投递下收敛。
type subjectFollowFanout struct {
	events    *mq.EventPublisher
	projector *followingevent.Handler
}

func (f *subjectFollowFanout) PublishSubjectFollow(ctx context.Context, event sfmodel.OutboxEvent) error {
	if err := f.events.PublishSubjectFollow(ctx, event); err != nil {
		return err
	}
	if f.projector == nil {
		return nil
	}
	payload := event.Payload
	return f.projector.Apply(ctx, followingapp.FollowChangedEvent{
		EventID: event.EventID, ViewerPersonaID: payload.PersonaID,
		SubjectType: payload.SubjectType, SubjectID: payload.SubjectID,
		Following:  payload.State == sfmodel.StateFollowing,
		OccurredAt: payload.OccurredAt, SourceVersion: payload.Version,
	})
}

type personaRelationshipCounterProjector interface {
	Apply(context.Context, relmodel.OutboxEvent) error
}

// personaRelationshipFanout 在既有 Redis 发布之上组合 following_subjects
// 与 owner follower/following 计数投影。任一投影失败都不推进 outbox
// checkpoint；计数投影以 eventId 幂等，following_subjects 以对象版本幂等。
type personaRelationshipFanout struct {
	events    *mq.EventPublisher
	projector *followingevent.Handler
	counters  personaRelationshipCounterProjector
}

func (f *personaRelationshipFanout) PublishPersonaRelationship(ctx context.Context, event relmodel.OutboxEvent) error {
	if err := f.events.PublishPersonaRelationship(ctx, event); err != nil {
		return err
	}
	if f.counters != nil {
		if err := f.counters.Apply(ctx, event); err != nil {
			return err
		}
	}
	if f.projector == nil {
		return nil
	}
	payload := event.Payload
	return f.projector.Apply(ctx, followingapp.FollowChangedEvent{
		EventID: event.EventID, ViewerPersonaID: payload.SourcePersonaID,
		SubjectType: "persona", SubjectID: payload.TargetPersonaID,
		Following: payload.Following, OccurredAt: payload.OccurredAt,
		SourceVersion: payload.Version,
	})
}
