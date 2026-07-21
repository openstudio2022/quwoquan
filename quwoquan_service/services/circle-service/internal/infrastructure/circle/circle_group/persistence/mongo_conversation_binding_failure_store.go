package persistence

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/circle-service/internal/infrastructure/messaging"
)

const conversationBindingFailureRetention = 7 * 24 * time.Hour

type MongoConversationBindingFailureStore struct {
	collection *mongo.Collection
}

var _ messaging.CircleGroupConversationBindingFailureStore = (*MongoConversationBindingFailureStore)(nil)

func NewMongoConversationBindingFailureStore(
	database *mongo.Database,
) *MongoConversationBindingFailureStore {
	return &MongoConversationBindingFailureStore{
		collection: database.Collection("circle_group_conversation_binding_failures"),
	}
}

func (store *MongoConversationBindingFailureStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("ttl_circle_group_conversation_binding_failures").SetExpireAfterSeconds(0)},
		{Keys: bson.D{{Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_circle_group_conversation_binding_failures_updated")},
	})
	return err
}

func (store *MongoConversationBindingFailureStore) RecordCircleGroupConversationBindingFailure(
	ctx context.Context,
	messageID string,
	eventID string,
	errorDigest string,
) (int64, error) {
	now := time.Now().UTC()
	var result struct {
		Attempts int64 `bson:"attempts"`
	}
	err := store.collection.FindOneAndUpdate(
		ctx,
		bson.M{"_id": messageID},
		bson.M{
			"$setOnInsert": bson.M{"eventId": eventID, "createdAt": now},
			"$set": bson.M{
				"errorDigest": errorDigest,
				"updatedAt":   now,
				"expiresAt":   now.Add(conversationBindingFailureRetention),
			},
			"$inc": bson.M{"attempts": int64(1)},
		},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&result)
	if err != nil {
		return 0, err
	}
	return result.Attempts, nil
}

func (store *MongoConversationBindingFailureStore) ClearCircleGroupConversationBindingFailure(
	ctx context.Context,
	messageID string,
) error {
	_, err := store.collection.DeleteOne(ctx, bson.M{"_id": messageID})
	return err
}
