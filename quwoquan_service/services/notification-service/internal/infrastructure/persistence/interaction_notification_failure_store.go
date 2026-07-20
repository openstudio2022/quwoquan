package persistence

import (
	"context"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const interactionFailureCollection = "interaction_notification_failures"

// MongoInteractionFailureStore 为互动通知消费保存逐消息失败计数；
// 计数达到上限后消息进入 DLQ 并清除记录。TTL 兜底防止残留。
type MongoInteractionFailureStore struct {
	failures *mongo.Collection
}

func NewMongoInteractionFailureStore(database *mongo.Database) *MongoInteractionFailureStore {
	if database == nil {
		panic("interaction failure store requires database")
	}
	return &MongoInteractionFailureStore{
		failures: database.Collection(interactionFailureCollection),
	}
}

func (store *MongoInteractionFailureStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.failures.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "updatedAt", Value: 1}},
			Options: options.Index().
				SetName("idx_interaction_notification_failures_ttl").
				SetExpireAfterSeconds(int32((7 * 24 * time.Hour).Seconds())),
		},
	})
	return err
}

func failureDocumentID(stream, messageID string) string {
	return strings.TrimSpace(stream) + "\x00" + strings.TrimSpace(messageID)
}

func (store *MongoInteractionFailureStore) RecordInteractionFailure(
	ctx context.Context,
	stream string,
	messageID string,
	eventID string,
	cause error,
) (int64, error) {
	var document struct {
		Attempts int64 `bson:"attempts"`
	}
	err := store.failures.FindOneAndUpdate(
		ctx,
		bson.M{"_id": failureDocumentID(stream, messageID)},
		bson.M{
			"$inc": bson.M{"attempts": int64(1)},
			"$set": bson.M{
				"stream":    strings.TrimSpace(stream),
				"eventId":   strings.TrimSpace(eventID),
				"lastError": cause.Error(),
				"updatedAt": time.Now().UTC(),
			},
		},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, err
	}
	return document.Attempts, nil
}

func (store *MongoInteractionFailureStore) ClearInteractionFailure(
	ctx context.Context,
	stream string,
	messageID string,
) error {
	_, err := store.failures.DeleteOne(
		ctx,
		bson.M{"_id": failureDocumentID(stream, messageID)},
	)
	return err
}
