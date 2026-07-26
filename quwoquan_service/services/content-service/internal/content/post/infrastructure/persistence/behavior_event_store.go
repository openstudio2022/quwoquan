package persistence

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"quwoquan_service/services/content-service/internal/content/post/application/ports"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	behaviorEventsCollection = "rm_behavior_events"
	entityWishlistCollection = "entity_wishlist_events"
	behaviorEventTTLDays     = 30
)

type BehaviorEventStore = ports.BehaviorEventStore
type RawBehaviorEvent = ports.RawBehaviorEvent
type WishlistEvent = ports.WishlistEvent

// MongoBehaviorEventStore persists raw behavior events to MongoDB with TTL.
type MongoBehaviorEventStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

// NewMongoBehaviorEventStore creates a store and ensures TTL + analytics indexes.
func NewMongoBehaviorEventStore(db *mongo.Database, logger *slog.Logger) *MongoBehaviorEventStore {
	s := &MongoBehaviorEventStore{
		coll:   db.Collection(behaviorEventsCollection),
		logger: logger,
	}
	s.ensureIndexes()
	return s
}

func (s *MongoBehaviorEventStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	ttl := int32(behaviorEventTTLDays * 24 * 60 * 60)

	indexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "createdAt", Value: 1}},
			Options: options.Index().SetExpireAfterSeconds(ttl),
		},
		{
			Keys: bson.D{{Key: "userId", Value: 1}, {Key: "action", Value: 1}, {Key: "createdAt", Value: -1}},
		},
		{
			Keys: bson.D{{Key: "contentId", Value: 1}, {Key: "createdAt", Value: -1}},
		},
		{
			Keys: bson.D{{Key: "feedRequestId", Value: 1}, {Key: "channelId", Value: 1}, {Key: "recallPath", Value: 1}, {Key: "createdAt", Value: -1}},
		},
	}

	for _, idx := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, idx); err != nil {
			s.warnIndexFailure(err)
		}
	}
	if err := s.ensureClientEventIdIndex(ctx); err != nil {
		s.warnIndexFailure(err)
	}
}

func (s *MongoBehaviorEventStore) ensureClientEventIdIndex(ctx context.Context) error {
	const indexName = "uq_behavior_events_user_client_event"
	_, err := s.coll.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "userId", Value: 1}, {Key: "clientEventId", Value: 1}},
		Options: options.Index().
			SetName(indexName).
			SetUnique(true).
			SetPartialFilterExpression(bson.M{
				"clientEventId": bson.M{"$type": "string", "$gt": ""},
			}),
	})
	if err != nil {
		return fmt.Errorf("create behavior event idempotency index: %w", err)
	}
	return nil
}

func (s *MongoBehaviorEventStore) warnIndexFailure(err error) {
	if s.logger != nil {
		s.logger.Warn("behavior_event_store: index creation failed", slog.String("error", err.Error()))
	}
}

func (s *MongoBehaviorEventStore) InsertBatch(ctx context.Context, events []RawBehaviorEvent) error {
	if len(events) == 0 {
		return nil
	}

	docs := make([]interface{}, len(events))
	for i := range events {
		docs[i] = events[i]
	}

	// unordered + 吞重复键：userId+clientEventId 唯一索引承担幂等（端侧重报、
	// N0-3 权威信号 outbox 重放都会命中），其余文档不受重复文档影响继续写入。
	_, err := s.coll.InsertMany(ctx, docs, options.InsertMany().SetOrdered(false))
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return nil
		}
		s.logger.Error("behavior_event_store: insert failed",
			slog.String("error", err.Error()),
			slog.Int("count", len(events)),
		)
	}
	return err
}

// ListUserFootprint 读取用户最近行为事件（createdAt 倒序），复用
// userId+action+createdAt 复合索引；不投影聚合，去重与展示语义由应用层决定。
func (s *MongoBehaviorEventStore) ListUserFootprint(ctx context.Context, userID string, actions []string, before time.Time, limit int) ([]RawBehaviorEvent, error) {
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	filter := bson.M{"userId": userID}
	if len(actions) > 0 {
		filter["action"] = bson.M{"$in": actions}
	}
	if !before.IsZero() {
		filter["createdAt"] = bson.M{"$lt": before}
	}
	cursor, err := s.coll.Find(ctx, filter,
		options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var out []RawBehaviorEvent
	if err := cursor.All(ctx, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// MongoWishlistEventStore persists explicit want-to-go intent facts consumed by
// MongoIntersectionSource.coWishlistedEntityReason.
type MongoWishlistEventStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewMongoWishlistEventStore(db *mongo.Database, logger *slog.Logger) *MongoWishlistEventStore {
	s := &MongoWishlistEventStore{
		coll:   db.Collection(entityWishlistCollection),
		logger: logger,
	}
	s.ensureIndexes()
	return s
}

func (s *MongoWishlistEventStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	indexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "userId", Value: 1}, {Key: "entityId", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "entityId", Value: 1}, {Key: "status", Value: 1}, {Key: "updatedAt", Value: -1}},
		},
	}
	for _, idx := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, idx); err != nil {
			if s.logger != nil {
				s.logger.Warn("wishlist_event_store: index creation failed", slog.String("error", err.Error()))
			}
		}
	}
}

func (s *MongoWishlistEventStore) UpsertWishlistEvent(ctx context.Context, event WishlistEvent) error {
	if event.UserID == "" || event.EntityID == "" {
		return nil
	}
	now := event.UpdatedAt
	if now.IsZero() {
		now = time.Now().UTC()
	}
	createdAt := event.CreatedAt
	if createdAt.IsZero() {
		createdAt = now
	}
	status := event.Status
	if status == "" {
		status = "active"
	}
	update := bson.M{
		"$set": bson.M{
			"userId":         event.UserID,
			"entityId":       event.EntityID,
			"objectType":     event.ObjectType,
			"displayName":    event.DisplayName,
			"status":         status,
			"sourceSurface":  event.SourceSurface,
			"referralSource": event.ReferralSource,
			"feedRequestId":  event.FeedRequestID,
			"sessionId":      event.SessionID,
			"clientEventId":  event.ClientEventID,
			"updatedAt":      now,
		},
		"$setOnInsert": bson.M{"createdAt": createdAt},
	}
	if _, err := s.coll.UpdateOne(
		ctx,
		bson.M{"userId": event.UserID, "entityId": event.EntityID},
		update,
		options.UpdateOne().SetUpsert(true),
	); err != nil {
		if s.logger != nil {
			s.logger.Error("wishlist_event_store: upsert failed",
				slog.String("error", err.Error()),
				slog.String("userId", event.UserID),
				slog.String("entityId", event.EntityID),
			)
		}
		return err
	}
	return nil
}

// IsWishlisted 返回当前用户对指定 canonical object 的有效显式意图。
func (s *MongoWishlistEventStore) IsWishlisted(
	ctx context.Context,
	userID string,
	objectID string,
	objectKind string,
) (bool, error) {
	count, err := s.coll.CountDocuments(ctx, bson.M{
		"userId":     userID,
		"entityId":   objectID,
		"objectType": objectKind,
		"status":     "active",
	})
	if err != nil {
		if s.logger != nil {
			s.logger.Error("wishlist_event_store: state read failed",
				slog.String("error", err.Error()),
				slog.String("userId", userID),
				slog.String("entityId", objectID),
				slog.String("objectType", objectKind),
			)
		}
		return false, err
	}
	return count > 0, nil
}
