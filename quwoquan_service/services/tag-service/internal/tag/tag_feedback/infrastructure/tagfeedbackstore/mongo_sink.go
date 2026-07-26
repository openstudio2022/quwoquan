// Package tagfeedbackstore 是 TagFeedback 的 Mongo append sink。
package tagfeedbackstore

import (
	"context"
	"errors"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/tag-service/internal/tag/tag_feedback/domain/tagfeedback/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback/domain/tagfeedback/ports"
)

const feedbackCollection = "tag_feedback"

type Sink struct {
	feedback *mongo.Collection
}

func NewSink(db *mongo.Database) *Sink {
	return &Sink{feedback: db.Collection(feedbackCollection)}
}

// EnsureIndexes 建立 storage.yaml 声明的唯一与查询索引。
func (s *Sink) EnsureIndexes(ctx context.Context) error {
	_, err := s.feedback.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "actorId", Value: 1}, {Key: "idempotencyKey", Value: 1}},
			Options: options.Index().SetName("idx_tag_feedback_actor_idempotency").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "tagRef", Value: 1}, {Key: "recordedAt", Value: -1}},
			Options: options.Index().SetName("idx_tag_feedback_tag_recorded"),
		},
		{
			Keys: bson.D{
				{Key: "eventPublishedAt", Value: 1},
				{Key: "recordedAt", Value: 1},
			},
			Options: options.Index().
				SetName("idx_tag_feedback_pending_event"),
		},
	})
	return err
}

// Append 追加事实；同 (actorId, idempotencyKey) 已存在时：
// payload 一致 → 重放返回已有事实；payload 不一致 → 幂等冲突。
func (s *Sink) Append(ctx context.Context, feedback model.Feedback) (model.Feedback, bool, error) {
	_, err := s.feedback.InsertOne(ctx, feedback)
	if err == nil {
		return feedback, false, nil
	}
	if !mongo.IsDuplicateKeyError(err) {
		return model.Feedback{}, false, err
	}
	var existing model.Feedback
	findErr := s.feedback.FindOne(ctx, bson.M{
		"actorId":        feedback.ActorID,
		"idempotencyKey": feedback.IdempotencyKey,
	}).Decode(&existing)
	if errors.Is(findErr, mongo.ErrNoDocuments) {
		return model.Feedback{}, false, err
	}
	if findErr != nil {
		return model.Feedback{}, false, findErr
	}
	if existing.ActorKind != feedback.ActorKind ||
		existing.TagRef != feedback.TagRef ||
		existing.Action != feedback.Action ||
		existing.Context != feedback.Context {
		return model.Feedback{}, false, model.ErrIdempotencyConflict
	}
	return existing, true, nil
}

var _ ports.Sink = (*Sink)(nil)
