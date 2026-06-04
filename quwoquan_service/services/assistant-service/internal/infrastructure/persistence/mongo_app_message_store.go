package persistence

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

// MongoAppMessageStore persists user-facing app messages (including proactive
// personalization attribution) so that proactive consumption evidence survives
// restarts and is auditable by the content-flywheel data-plane verifier.
type MongoAppMessageStore struct {
	coll *mongo.Collection
}

func NewMongoAppMessageStore(db *mongo.Database) *MongoAppMessageStore {
	return &MongoAppMessageStore{coll: db.Collection("app_messages")}
}

func (s *MongoAppMessageStore) EnsureIndexes(ctx context.Context) error {
	indexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_app_messages_user_created")},
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "read", Value: 1}}, Options: options.Index().SetName("idx_app_messages_user_read")},
	}
	if _, err := s.coll.Indexes().CreateMany(ctx, indexes); err != nil {
		return fmt.Errorf("create app message indexes: %w", err)
	}
	return nil
}

func (s *MongoAppMessageStore) CreateAppMessage(ctx context.Context, message assistant.AppMessage) (assistant.AppMessage, error) {
	if _, err := s.coll.InsertOne(ctx, message); err != nil {
		return assistant.AppMessage{}, rterr.NewUnavailable(rterr.ModuleAssistant, "写入应用消息失败", err.Error())
	}
	return message, nil
}

func (s *MongoAppMessageStore) GetAppMessage(ctx context.Context, userID, messageID string) (assistant.AppMessage, error) {
	var item assistant.AppMessage
	err := s.coll.FindOne(ctx, bson.M{"_id": messageID, "userId": userID}).Decode(&item)
	if err != nil {
		return assistant.AppMessage{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "消息不存在", "app message not found")
	}
	return item, nil
}

func (s *MongoAppMessageStore) ListAppMessages(ctx context.Context, userID string, limit int, _ string) ([]assistant.AppMessage, error) {
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	cur, err := s.coll.Find(
		ctx,
		bson.M{"userId": userID},
		options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "读取应用消息失败", err.Error())
	}
	defer cur.Close(ctx)
	items := []assistant.AppMessage{}
	if err := cur.All(ctx, &items); err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "解析应用消息失败", err.Error())
	}
	return items, nil
}

func (s *MongoAppMessageStore) AckAppMessage(ctx context.Context, userID, messageID string, ackedAt time.Time) (assistant.AppMessage, error) {
	var item assistant.AppMessage
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{"_id": messageID, "userId": userID},
		bson.M{"$set": bson.M{"ackedAt": ackedAt}},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&item)
	if err != nil {
		return assistant.AppMessage{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "消息不存在", "app message not found")
	}
	return item, nil
}

func (s *MongoAppMessageStore) ReadAppMessage(ctx context.Context, userID, messageID string, readAt time.Time) (assistant.AppMessage, error) {
	var item assistant.AppMessage
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{"_id": messageID, "userId": userID},
		bson.M{"$set": bson.M{"read": true, "readAt": readAt}},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&item)
	if err != nil {
		return assistant.AppMessage{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "消息不存在", "app message not found")
	}
	return item, nil
}

func (s *MongoAppMessageStore) UnreadAppMessageCount(ctx context.Context, userID string) (int, error) {
	count, err := s.coll.CountDocuments(ctx, bson.M{"userId": userID, "read": false})
	if err != nil {
		return 0, rterr.NewUnavailable(rterr.ModuleAssistant, "统计未读失败", err.Error())
	}
	return int(count), nil
}
