package main

import (
	"context"
	"log"
	"os"
	"strings"

	"go.mongodb.org/mongo-driver/v2/mongo"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	"quwoquan_service/services/user-service/internal/adapters/mq"
	followingapp "quwoquan_service/services/user-service/internal/application/relationship/following_subject"
	relmodel "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/model"
	sfmodel "quwoquan_service/services/user-service/internal/domain/relationship/subject_follow/model"
)

// resolveObjectTagIndexCollection 解析 tag 域共享派生读模型 object_tag_index 的
// 写入目标。优先 TAG_MONGO_URI/TAG_MONGO_DATABASE（与 tag-service 读侧同源）；
// 未配置时回退本服务 Mongo 并 WARN（存量环境渐进收敛，避免静默漂移）。
func resolveObjectTagIndexCollection(ctx context.Context, fallback *mongo.Database) *mongo.Collection {
	tagURI := strings.TrimSpace(os.Getenv("TAG_MONGO_URI"))
	tagDatabase := strings.TrimSpace(os.Getenv("TAG_MONGO_DATABASE"))
	if tagDatabase == "" {
		tagDatabase = "quwoquan_tag"
	}
	if tagURI != "" {
		client := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: tagURI}, "user-service-tagindex")
		return client.Database(tagDatabase).Collection("object_tag_index")
	}
	if fallback == nil {
		return nil
	}
	log.Printf("user-service WARN: TAG_MONGO_URI unset; object_tag_index projector falls back to the service database (tag-service readers may not see these writes)")
	return fallback.Collection("object_tag_index")
}

// subjectFollowFanout 把已提交的 SubjectFollow 事实先追加到 Redis Stream，
// 再 upsert following_subjects 投影；任一失败都不推进 outbox checkpoint，
// 幂等消费保证至少一次投递下收敛。
type subjectFollowFanout struct {
	events    *mq.EventPublisher
	projector *followingapp.Projector
}

func (f *subjectFollowFanout) PublishSubjectFollow(ctx context.Context, event sfmodel.OutboxEvent) error {
	if err := f.events.PublishSubjectFollow(ctx, event); err != nil {
		return err
	}
	if f.projector == nil {
		return nil
	}
	return f.projector.ApplySubjectFollow(ctx, event)
}

type personaRelationshipCounterProjector interface {
	Apply(context.Context, relmodel.OutboxEvent) error
}

// personaRelationshipFanout 在既有 Redis 发布之上组合 following_subjects
// 与 owner follower/following 计数投影。任一投影失败都不推进 outbox
// checkpoint；计数投影以 eventId 幂等，following_subjects 以对象版本幂等。
type personaRelationshipFanout struct {
	events    *mq.EventPublisher
	projector *followingapp.Projector
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
	return f.projector.ApplyPersonaRelationship(ctx, event)
}
