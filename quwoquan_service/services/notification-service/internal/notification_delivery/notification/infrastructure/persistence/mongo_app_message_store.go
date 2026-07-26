package persistence

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
	generated "quwoquan_service/services/notification-service/generated/notification_delivery/notification"
)

const appMessageRetention = 90 * 24 * time.Hour

type MongoAppMessageStore struct {
	db   *mongo.Database
	coll *mongo.Collection
}

type inboxCursor struct {
	CreatedAt time.Time `json:"createdAt"`
	MessageID string    `json:"messageId"`
}

var _ notification.AppMessageAggregateStore = (*MongoAppMessageStore)(nil)
var _ application.AppMessageInboxReader = (*MongoAppMessageStore)(nil)
var _ application.AppMessageDetailReader = (*MongoAppMessageStore)(nil)
var _ application.AppMessageUnreadCountReader = (*MongoAppMessageStore)(nil)
var _ application.AppMessageTransactionBoundary = (*MongoAppMessageStore)(nil)

func NewMongoAppMessageStore(db *mongo.Database) *MongoAppMessageStore {
	return &MongoAppMessageStore{db: db, coll: db.Collection("app_messages")}
}

func (s *MongoAppMessageStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.coll.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "idempotencyKey", Value: 1}},
			Options: options.Index().SetName("uq_app_messages_idempotency").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "userId", Value: 1}, {Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}},
			Options: options.Index().SetName("idx_app_messages_owner_created"),
		},
		{
			Keys:    bson.D{{Key: "userId", Value: 1}, {Key: "read", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_app_messages_owner_read"),
		},
		{
			Keys:    bson.D{{Key: "createdAt", Value: 1}},
			Options: options.Index().SetName("ttl_app_messages_created").SetExpireAfterSeconds(int32(appMessageRetention.Seconds())),
		},
	})
	if err != nil {
		return fmt.Errorf("ensure app message indexes: %w", err)
	}
	return nil
}

func (s *MongoAppMessageStore) RunInTransaction(
	ctx context.Context,
	fn func(context.Context) error,
) error {
	if mongo.SessionFromContext(ctx) != nil {
		return fn(ctx)
	}
	session, err := s.db.Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		return nil, fn(txCtx)
	})
	return err
}

func (s *MongoAppMessageStore) Create(
	ctx context.Context,
	message notification.AppMessage,
) (notification.AppMessage, bool, error) {
	_, err := s.coll.InsertOne(ctx, message)
	if err == nil {
		return message, true, nil
	}
	if mongo.IsDuplicateKeyError(err) {
		existing, ok, findErr := s.FindByIdempotencyKey(ctx, message.IdempotencyKey)
		if findErr != nil {
			return notification.AppMessage{}, false, findErr
		}
		if ok {
			return existing, false, nil
		}
	}
	return notification.AppMessage{}, false, err
}

func (s *MongoAppMessageStore) FindByIdempotencyKey(
	ctx context.Context,
	key string,
) (notification.AppMessage, bool, error) {
	key = strings.TrimSpace(key)
	if key == "" {
		return notification.AppMessage{}, false, nil
	}
	var message notification.AppMessage
	err := s.coll.FindOne(ctx, bson.M{"idempotencyKey": key}).Decode(&message)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return notification.AppMessage{}, false, nil
	}
	if err != nil {
		return notification.AppMessage{}, false, err
	}
	return message, true, nil
}

func (s *MongoAppMessageStore) Get(
	ctx context.Context,
	userID, messageID string,
) (notification.AppMessage, error) {
	var message notification.AppMessage
	err := s.coll.FindOne(ctx, bson.M{"_id": messageID, "userId": userID}).Decode(&message)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return notification.AppMessage{}, generated.AppErrorFromAppMessageNotFound("message does not exist for owner")
	}
	if err != nil {
		return notification.AppMessage{}, generated.AppErrorFromStorageReadFailed(err.Error())
	}
	return message, nil
}

func (s *MongoAppMessageStore) ListInbox(
	ctx context.Context,
	query application.AppMessageInboxQuery,
) (notification.AppMessageInboxSlice, error) {
	filter := bson.M{"userId": query.UserID}
	if query.MessageType != "" {
		filter["messageType"] = query.MessageType
	}
	if query.Read != nil {
		filter["read"] = *query.Read
	}
	if query.Cursor != "" {
		cursor, err := decodeInboxCursor(query.Cursor)
		if err != nil {
			return notification.AppMessageInboxSlice{}, generated.AppErrorFromInvalidArgument(err.Error())
		}
		filter["$or"] = bson.A{
			bson.M{"createdAt": bson.M{"$lt": cursor.CreatedAt}},
			bson.M{"createdAt": cursor.CreatedAt, "_id": bson.M{"$lt": cursor.MessageID}},
		}
	}
	cursor, err := s.coll.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(query.Limit+1)),
	)
	if err != nil {
		return notification.AppMessageInboxSlice{}, generated.AppErrorFromStorageReadFailed(err.Error())
	}
	defer cursor.Close(ctx)
	items := make([]notification.AppMessage, 0, query.Limit+1)
	if err := cursor.All(ctx, &items); err != nil {
		return notification.AppMessageInboxSlice{}, generated.AppErrorFromStorageReadFailed(err.Error())
	}
	nextCursor := ""
	if len(items) > query.Limit {
		last := items[query.Limit-1]
		nextCursor, err = encodeInboxCursor(inboxCursor{CreatedAt: last.CreatedAt, MessageID: last.MessageID})
		if err != nil {
			return notification.AppMessageInboxSlice{}, generated.AppErrorFromStorageReadFailed(err.Error())
		}
		items = items[:query.Limit]
	}
	return notification.AppMessageInboxSlice{Items: items, NextCursor: nextCursor}, nil
}

func (s *MongoAppMessageStore) Acknowledge(
	ctx context.Context,
	userID, messageID string,
	at time.Time,
) (notification.AppMessage, error) {
	return s.updateState(ctx, userID, messageID, mongo.Pipeline{
		bson.D{{Key: "$set", Value: bson.D{{
			Key:   "ackedAt",
			Value: bson.D{{Key: "$ifNull", Value: bson.A{"$ackedAt", at.UTC()}}},
		}}}},
	})
}

func (s *MongoAppMessageStore) MarkRead(
	ctx context.Context,
	userID, messageID string,
	at time.Time,
) (notification.AppMessage, error) {
	return s.updateState(ctx, userID, messageID, mongo.Pipeline{
		bson.D{{Key: "$set", Value: bson.D{
			{Key: "read", Value: true},
			{Key: "readAt", Value: bson.D{{Key: "$ifNull", Value: bson.A{"$readAt", at.UTC()}}}},
		}}},
	})
}

func (s *MongoAppMessageStore) CountUnread(ctx context.Context, userID string) (int64, error) {
	count, err := s.coll.CountDocuments(ctx, bson.M{"userId": userID, "read": false})
	if err != nil {
		return 0, generated.AppErrorFromStorageReadFailed(err.Error())
	}
	return count, nil
}

func (s *MongoAppMessageStore) updateState(
	ctx context.Context,
	userID, messageID string,
	update mongo.Pipeline,
) (notification.AppMessage, error) {
	var message notification.AppMessage
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{"_id": messageID, "userId": userID},
		update,
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&message)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return notification.AppMessage{}, generated.AppErrorFromAppMessageNotFound("message does not exist for owner")
	}
	if err != nil {
		return notification.AppMessage{}, generated.AppErrorFromStorageWriteFailed(err.Error())
	}
	return message, nil
}

func encodeInboxCursor(cursor inboxCursor) (string, error) {
	payload, err := json.Marshal(cursor)
	if err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(payload), nil
}

func decodeInboxCursor(raw string) (inboxCursor, error) {
	payload, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(raw))
	if err != nil {
		return inboxCursor{}, fmt.Errorf("cursor is not valid base64url")
	}
	var cursor inboxCursor
	if err := json.Unmarshal(payload, &cursor); err != nil {
		return inboxCursor{}, fmt.Errorf("cursor payload is invalid")
	}
	if cursor.CreatedAt.IsZero() || strings.TrimSpace(cursor.MessageID) == "" {
		return inboxCursor{}, fmt.Errorf("cursor is incomplete")
	}
	return cursor, nil
}
