package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// Homepage 事件消费者 checkpoint 的持久化：游标绑定 outbox 事件的 occurredAt，
// 旧的非时序 checkpoint 视为空游标触发一次幂等重放。
func (s *MongoHomepageStore) LoadCheckpoint(ctx context.Context, consumer string) (string, error) {
	var document checkpointDocument
	err := s.checkpoints.FindOne(ctx, bson.M{"_id": strings.TrimSpace(consumer)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	if err == nil && (document.CursorOccurredAt == nil || document.CursorOccurredAt.IsZero()) {
		// 旧 checkpoint 只保存非时序 EventID，无法证明未跳过更小哈希。
		// 返回空游标触发一次完整、幂等重放；下一次 SaveCheckpoint 会升级它。
		return "", nil
	}
	return document.Checkpoint, err
}

func (s *MongoHomepageStore) SaveCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	checkpoint = strings.TrimSpace(checkpoint)
	var checkpointEvent outboxDocument
	if err := s.outbox.FindOne(ctx, bson.M{"_id": checkpoint}).Decode(&checkpointEvent); err != nil {
		return err
	}
	cursorOccurredAt := checkpointEvent.OccurredAt.UTC()
	_, err := s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(consumer)},
		bson.M{"$set": bson.M{
			"checkpoint":       checkpoint,
			"cursorOccurredAt": cursorOccurredAt,
			"updatedAt":        time.Now().UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}
