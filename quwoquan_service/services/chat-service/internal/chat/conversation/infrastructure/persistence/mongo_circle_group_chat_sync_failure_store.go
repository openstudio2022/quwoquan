package persistence

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
)

const circleGroupChatSyncFailureRetention = 7 * 24 * time.Hour

// MongoCircleGroupChatSyncFailureStore persists retry counters independently
// from Redis pending state so a process restart cannot reset poison-message
// attempts before the message is moved to its retained DLQ.
type MongoCircleGroupChatSyncFailureStore struct {
	collection *mongo.Collection
}

var _ mq.CircleGroupChatSyncFailureStore = (*MongoCircleGroupChatSyncFailureStore)(nil)

func NewMongoCircleGroupChatSyncFailureStore(
	db *mongo.Database,
) *MongoCircleGroupChatSyncFailureStore {
	return &MongoCircleGroupChatSyncFailureStore{
		collection: db.Collection("circle_group_chat_sync_failures"),
	}
}

func (s *MongoCircleGroupChatSyncFailureStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("ttl_circle_group_chat_sync_failures").SetExpireAfterSeconds(0)},
		{Keys: bson.D{{Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_circle_group_chat_sync_failures_updated")},
	})
	return err
}

func (s *MongoCircleGroupChatSyncFailureStore) RecordCircleGroupChatSyncFailure(
	ctx context.Context,
	messageKey string,
	eventID string,
	errorDigest string,
) (int64, error) {
	now := time.Now().UTC()
	var document struct {
		Attempts int64 `bson:"attempts"`
	}
	err := s.collection.FindOneAndUpdate(
		ctx,
		bson.M{"_id": messageKey},
		bson.M{
			"$setOnInsert": bson.M{
				"eventId":   eventID,
				"createdAt": now,
			},
			"$set": bson.M{
				"errorDigest": errorDigest,
				"updatedAt":   now,
				"expiresAt":   now.Add(circleGroupChatSyncFailureRetention),
			},
			"$inc": bson.M{"attempts": int64(1)},
		},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, err
	}
	return document.Attempts, nil
}

func (s *MongoCircleGroupChatSyncFailureStore) ClearCircleGroupChatSyncFailure(
	ctx context.Context,
	messageKey string,
) error {
	_, err := s.collection.DeleteOne(ctx, bson.M{"_id": messageKey})
	return err
}
