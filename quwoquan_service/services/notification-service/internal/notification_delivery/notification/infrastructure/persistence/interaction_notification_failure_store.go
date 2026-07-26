package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const interactionFailureCollection = "interaction_notification_failures"

// MongoInteractionFailureStore 为互动通知消费保存逐消息失败计数与终态标记；
// 计数达到上限后 source PEL 保持待恢复，TTL 兜底防止残留。
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
	return irreversibleNotificationDigest(
		strings.TrimSpace(stream) + "\x00" + strings.TrimSpace(messageID),
	)
}

func (store *MongoInteractionFailureStore) RecordInteractionFailure(
	ctx context.Context,
	stream string,
	messageID string,
	eventID string,
	errorClass string,
	cause error,
) (int64, error) {
	if cause == nil {
		return 0, errors.New("interaction notification failure cause is required")
	}
	errorClass = strings.TrimSpace(errorClass)
	if errorClass == "" {
		return 0, errors.New(
			"interaction notification failure error class is required",
		)
	}
	var document struct {
		Attempts int64 `bson:"attempts"`
	}
	err := store.failures.FindOneAndUpdate(
		ctx,
		bson.M{"_id": failureDocumentID(stream, messageID)},
		bson.M{
			"$inc": bson.M{"attempts": int64(1)},
			"$set": bson.M{
				"eventDigest": irreversibleNotificationDigest(eventID),
				"errorClass":  errorClass,
				"errorDigest": irreversibleNotificationDigest(cause.Error()),
				"updatedAt":   time.Now().UTC(),
			},
		},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, err
	}
	return document.Attempts, nil
}

func (store *MongoInteractionFailureStore) IsInteractionDeadLettered(
	ctx context.Context,
	stream string,
	messageID string,
) (bool, error) {
	var document struct {
		DeadLetteredAt *time.Time `bson:"deadLetteredAt"`
	}
	err := store.failures.FindOne(
		ctx,
		bson.M{"_id": failureDocumentID(stream, messageID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("read interaction dead-letter state: %w", err)
	}
	return document.DeadLetteredAt != nil &&
		!document.DeadLetteredAt.IsZero(), nil
}

func (store *MongoInteractionFailureStore) MarkInteractionDeadLettered(
	ctx context.Context,
	stream string,
	messageID string,
) error {
	now := time.Now().UTC()
	result, err := store.failures.UpdateOne(
		ctx,
		bson.M{"_id": failureDocumentID(stream, messageID)},
		bson.M{
			"$set": bson.M{
				"deadLetteredAt": now,
				"updatedAt":      now,
			},
		},
	)
	if err != nil {
		return fmt.Errorf("mark interaction dead-letter state: %w", err)
	}
	if result.MatchedCount == 0 {
		return errors.New("interaction notification failure state is missing")
	}
	return nil
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
