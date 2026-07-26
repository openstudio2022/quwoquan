package persistence

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

// MongoGrowthStore 持久化 user_activity_daily 聚合与 actor 首见事实。
// 集合：ops_user_activity_daily（_id=date）、ops_actor_first_seen（_id=actorHash）。
type MongoGrowthStore struct {
	daily     *mongo.Collection
	firstSeen *mongo.Collection
}

func NewMongoGrowthStore(db *mongo.Database) *MongoGrowthStore {
	return &MongoGrowthStore{
		daily:     db.Collection("ops_user_activity_daily"),
		firstSeen: db.Collection("ops_actor_first_seen"),
	}
}

func (s *MongoGrowthStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.firstSeen.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "firstSeenDate", Value: 1}},
		Options: options.Index().SetName("idx_actor_first_seen_date"),
	})
	if err != nil {
		return fmt.Errorf("create growth indexes: %w", err)
	}
	return nil
}

func (s *MongoGrowthStore) UpsertDailyActivity(ctx context.Context, activity application.DailyActivity) error {
	filter := bson.D{{Key: "_id", Value: activity.Date}}
	update := bson.D{{Key: "$set", Value: bson.D{
		{Key: "actorHashes", Value: activity.ActorHashes},
		{Key: "dau", Value: activity.DAU},
		{Key: "pv", Value: activity.PV},
		{Key: "sessionCount", Value: activity.SessionCount},
		{Key: "newActors", Value: activity.NewActors},
		{Key: "updatedAt", Value: activity.UpdatedAt},
	}}}
	_, err := s.daily.UpdateOne(ctx, filter, update, options.UpdateOne().SetUpsert(true))
	if err != nil {
		return fmt.Errorf("upsert daily activity %s: %w", activity.Date, err)
	}
	return nil
}

func (s *MongoGrowthStore) ListDailyActivity(ctx context.Context, fromDate, toDate string) ([]application.DailyActivity, error) {
	cursor, err := s.daily.Find(ctx, bson.D{{Key: "_id", Value: bson.D{
		{Key: "$gte", Value: fromDate},
		{Key: "$lte", Value: toDate},
	}}})
	if err != nil {
		return nil, fmt.Errorf("list daily activity: %w", err)
	}
	defer cursor.Close(ctx)
	items := make([]application.DailyActivity, 0)
	for cursor.Next(ctx) {
		var item application.DailyActivity
		if err := cursor.Decode(&item); err != nil {
			return nil, fmt.Errorf("decode daily activity: %w", err)
		}
		items = append(items, item)
	}
	return items, cursor.Err()
}

func (s *MongoGrowthStore) EnsureActorFirstSeen(ctx context.Context, date string, actorHashes []string) error {
	if len(actorHashes) == 0 {
		return nil
	}
	models := make([]mongo.WriteModel, 0, len(actorHashes))
	for _, actorHash := range actorHashes {
		models = append(models, mongo.NewUpdateOneModel().
			SetFilter(bson.D{{Key: "_id", Value: actorHash}}).
			SetUpdate(bson.D{{Key: "$setOnInsert", Value: bson.D{
				{Key: "firstSeenDate", Value: date},
				{Key: "firstSeenAt", Value: time.Now().UTC()},
			}}}).
			SetUpsert(true))
	}
	if _, err := s.firstSeen.BulkWrite(ctx, models, options.BulkWrite().SetOrdered(false)); err != nil {
		return fmt.Errorf("ensure actor first seen: %w", err)
	}
	return nil
}

func (s *MongoGrowthStore) ListActorFirstSeen(ctx context.Context, date string) ([]string, error) {
	cursor, err := s.firstSeen.Find(ctx, bson.D{{Key: "firstSeenDate", Value: date}})
	if err != nil {
		return nil, fmt.Errorf("list actor first seen: %w", err)
	}
	defer cursor.Close(ctx)
	actors := make([]string, 0)
	for cursor.Next(ctx) {
		var doc struct {
			ActorHash string `bson:"_id"`
		}
		if err := cursor.Decode(&doc); err != nil {
			return nil, fmt.Errorf("decode actor first seen: %w", err)
		}
		actors = append(actors, doc.ActorHash)
	}
	return actors, cursor.Err()
}

var _ application.GrowthStore = (*MongoGrowthStore)(nil)
